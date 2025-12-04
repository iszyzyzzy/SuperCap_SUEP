
import can
import struct
import threading
import time
import argparse
from collections import deque
import platform
from datetime import datetime

# --- Rich TUI ---
from rich.live import Live
from rich.panel import Panel
from rich.layout import Layout
from rich.text import Text
from rich.console import Console, Group
from rich.table import Table

# --- Non-blocking keyboard input ---
try:
    if platform.system() == "Windows":
        import msvcrt
    else:
        import sys
        import termios
        import atexit
        from select import select
except ImportError:
    msvcrt = None
    termios = None


# --- CAN IDs ---
CAN_ID_HOST_COMMAND = 0x061
CAN_ID_FEEDBACK_OLD = 0x051
CAN_ID_FEEDBACK_NEW = 0x052

class KBHit:
    """Cross-platform non-blocking keyboard input."""
    def __init__(self):
        if msvcrt is None and termios is None:
            self.active = False
            return
        self.active = True
        if platform.system() == "Windows":
            self.getch = msvcrt.getwch
            self.kbhit = msvcrt.kbhit
        else:
            self.fd = sys.stdin.fileno()
            self.new_term = termios.tcgetattr(self.fd)
            self.old_term = termios.tcgetattr(self.fd)
            self.new_term[3] = (self.new_term[3] & ~termios.ICANON & ~termios.ECHO)
            termios.tcsetattr(self.fd, termios.TCSAFLUSH, self.new_term)
            atexit.register(self.set_normal_term)

    def set_normal_term(self):
        if self.active and platform.system() != "Windows":
            termios.tcsetattr(self.fd, termios.TCSAFLUSH, self.old_term)

    def getch(self):
        if not self.active: return ""
        if platform.system() != "Windows": return sys.stdin.read(1)
        return msvcrt.getwch()

    def kbhit(self):
        if not self.active: return False
        if platform.system() != "Windows":
            dr, _, _ = select([sys.stdin], [], [], 0)
            return dr != []
        return msvcrt.kbhit()


class SuperCapMonitor:
    def __init__(self, port, baudrate):
        self.bus = can.interface.Bus(interface='slcan', channel=port, ttyBaudrate=baudrate)
        self.running = True
        self.sending_enabled = True
        self.command_data = {
            'enableDCDC': True, 'systemRestart': False, 'clearError': False,
            'enableActiveChargingLimit': False, 'useNewFeedbackMessage': False,
            'refereePowerLimit': 37, 'refereeEnergyBuffer': 57, 'activeChargingLimitRatio': 255
        }
        # TUI state
        self.console = Console()
        self.command_log = deque(maxlen=100)
        self.command_buffer = ""
        self.latest_feedback = {}
        self.last_message_time = 0
        self.lock = threading.Lock()

    def _receiver_thread(self):
        while self.running:
            try:
                msg = self.bus.recv(timeout=1)
                if msg: self.parse_message(msg)
            except can.CanError as e:
                if self.running: self.log_command(f"[bold red]CAN Error: {e}[/bold red]")

    def log_command(self, message):
        now = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        with self.lock:
            self.command_log.append(f"([dim]{now}[/dim]) {message}")

    def parse_message(self, msg):
        parsed_data = None
        if msg.arbitration_id == CAN_ID_FEEDBACK_OLD and msg.dlc == 8:
            try:
                status, p_chassis, p_limit, cap_energy = struct.unpack('<BfHB', msg.data)
                parsed_data = self.format_status_code(status)
                parsed_data.update({
                    "Type": "Old",
                    "Chassis Power": f"{p_chassis:6.2f} W",
                    "Referee Power": "[dim]N/A[/dim]",
                    "Power Limit": f"{p_limit} W",
                    "Cap Energy": f"{cap_energy}/250",
                })
            except struct.error:
                self.log_command(f"[yellow]WARN: Invalid structure for old feedback (ID {CAN_ID_FEEDBACK_OLD:#05x})[/yellow]")
        elif msg.arbitration_id == CAN_ID_FEEDBACK_NEW and msg.dlc == 8:
            try:
                status, p_chassis_raw, p_referee_raw, p_limit, cap_energy = struct.unpack('<BHHHB', msg.data)
                p_chassis = (p_chassis_raw - 16384) / 64.0
                p_referee = (p_referee_raw - 16384) / 64.0
                parsed_data = self.format_status_code(status)
                parsed_data.update({
                    "Type": "New",
                    "Chassis Power": f"{p_chassis:6.3f} W",
                    "Referee Power": f"{p_referee:6.3f} W",
                    "Power Limit": f"{p_limit} W",
                    "Cap Energy": f"{cap_energy}/250",
                })
            except struct.error:
                self.log_command(f"[yellow]WARN: Invalid structure for new feedback (ID {CAN_ID_FEEDBACK_NEW:#05x})[/yellow]")

        if parsed_data:
            with self.lock:
                self.latest_feedback = parsed_data
                self.last_message_time = time.time()

    def format_status_code(self, status):
        power_on = (status >> 7) & 1
        feedback_fmt_new = (status >> 6) & 1
        err_map = {0: "[green]No Error[/green]", 1: "[yellow]Auto-Recover[/yellow]", 2: "[orange3]Manual-Recover[/orange3]", 3: "[bold red]Unrecoverable[/bold red]"}
        return {
            "Power Status": "[green]ON[/green]" if power_on else "[red]OFF[/red]",
            "Feedback Format": "New" if feedback_fmt_new else "Old",
            "Error Level": err_map.get(status & 3, "Unknown")
        }

    def send_command(self):
        try:
            byte0 = ((1 if self.command_data['enableDCDC'] else 0) |
                     ((1 if self.command_data['systemRestart'] else 0) << 1) |
                     ((1 if self.command_data['clearError'] else 0) << 5) |
                     ((1 if self.command_data['enableActiveChargingLimit'] else 0) << 6) |
                     ((1 if self.command_data['useNewFeedbackMessage'] else 0) << 7))
            data = struct.pack('<BHHB', byte0, int(self.command_data['refereePowerLimit']),
                               int(self.command_data['refereeEnergyBuffer']),
                               int(self.command_data['activeChargingLimitRatio']))
            data += b'\x00\x00'
            msg = can.Message(arbitration_id=CAN_ID_HOST_COMMAND, data=data, is_extended_id=False, dlc=8)
            self.bus.send(msg)
            if self.command_data['systemRestart']: self.command_data['systemRestart'] = False
            if self.command_data['clearError']: self.command_data['clearError'] = False
        except (can.CanError, struct.error) as e:
            self.log_command(f"[bold red]Send Error: {e}[/bold red]")

    def process_command(self, cmd_str):
        self.log_command(f"[bold blue]>> {cmd_str}[/bold blue]")
        cmd_line = cmd_str.strip().lower().split()
        if not cmd_line: return
        cmd = cmd_line[0]

        if cmd in ('q', 'quit', 'exit'): self.running = False
        elif cmd == 'on': self.command_data['enableDCDC'] = True
        elif cmd == 'off': self.command_data['enableDCDC'] = False
        elif cmd == 'restart': self.command_data['systemRestart'] = True
        elif cmd == 'clear': self.command_data['clearError'] = True
        elif cmd == 'send':
            if len(cmd_line) > 1 and cmd_line[1] == 'off': self.sending_enabled = False
            else: self.sending_enabled = True
        elif cmd == 'format':
            if len(cmd_line) > 1 and cmd_line[1] == 'new': self.command_data['useNewFeedbackMessage'] = True
            else: self.command_data['useNewFeedbackMessage'] = False
        elif cmd == 'limit':
            if len(cmd_line) > 1:
                try: self.command_data['refereePowerLimit'] = int(cmd_line[1])
                except ValueError: self.log_command("[yellow]Usage: limit <watts>[/yellow]")
            else: self.log_command("[yellow]Usage: limit <watts>[/yellow]")
        elif cmd == 'buffer':
            if len(cmd_line) > 1:
                try:
                    buffer_val = int(cmd_line[1])
                    if 0 <= buffer_val <= 60:
                        self.command_data['refereeEnergyBuffer'] = buffer_val
                    else:
                        self.log_command("[yellow]Buffer value must be between 0 and 60[/yellow]")
                except ValueError:
                    self.log_command("[yellow]Usage: buffer <value> (0-60)[/yellow]")
            else:
                self.log_command("[yellow]Usage: buffer <value> (0-60)[/yellow]")
        elif cmd == 'help':
            #self.log_command("[green]Commands: on, off, send <on|off>, restart, clear, format <new|old>, limit <watts>, quit[/green]")
            self.log_command("""
[green]Commands:
  help               - Show this help message
  on                 - Enable DCDC converter
  off                - Disable DCDC converter
  send [on|off]     - Enable or disable auto-sending of commands
  restart            - Send system restart command
  clear              - Clear error state
  format [new|old]  - Set feedback message format, default old but new is recommended
  limit <watts>     - Set referee power limit in watts
  buffer <value>    - Set referee energy buffer (0-60) default 57(disabled buffer feedback)
  quit               - Exit the monitor
[/green]
                             """)
        else: self.log_command(f"[red]Unknown command: '{cmd}', type 'help' for a list of commands[/red]")

    def make_layout(self) -> Layout:
        layout = Layout(name="root")
        layout.split(Layout(name="header", size=3), Layout(ratio=1, name="main"), Layout(size=3, name="footer"))
        layout["main"].split_row(Layout(name="status"), Layout(name="log", size=60))
        return layout

    def get_command_log_panel(self) -> Panel:
        with self.lock:
            log_content = "\n".join(self.command_log)
        # Use from_markup to correctly render colors and styles
        log_text = Text.from_markup(log_content)
        return Panel(log_text, title="[bold green]Command Log[/bold green]", border_style="green")

    def get_status_panel(self) -> Panel:
        # --- Sent Command Status ---
        cmd_table = Table.grid(padding=(0, 1))
        cmd_table.add_column(style="bold blue", justify="right")
        cmd_table.add_column(style="white")
        cmd_table.add_row("DCDC Target:", "[green]Enabled[/green]" if self.command_data['enableDCDC'] else "[red]Disabled[/red]")
        cmd_table.add_row("Auto-sending:", "[green]ON[/green]" if self.sending_enabled else "[red]OFF[/red]")
        cmd_table.add_row("Feedback Target:", "New" if self.command_data['useNewFeedbackMessage'] else "Old")
        cmd_table.add_row("Set Power Limit:", f"{self.command_data['refereePowerLimit']} W")

        # --- Received Feedback Status ---
        with self.lock:
            feedback = self.latest_feedback.copy()
            last_msg_time = self.last_message_time
        
        feedback_table = Table.grid(padding=(0, 1))
        feedback_table.add_column(style="bold magenta", justify="right")
        feedback_table.add_column()
        # Use from_markup for each value that might contain style tags
        for key, val in feedback.items():
            feedback_table.add_row(f"{key}:", Text.from_markup(val))
        
        # --- Last Message Time ---
        seconds_ago = time.time() - last_msg_time if last_msg_time > 0 else -1
        time_color = "green" if 0 <= seconds_ago < 0.5 else "red"
        seconds_ago_millis = seconds_ago * 1000 if seconds_ago >= 0 else -1
        time_str = f"[{time_color}]{seconds_ago_millis:.2f}ms ago[/{time_color}]" if seconds_ago >= 0 else "[red]Never[/red]"
        
        return Panel(
            Group(
                Panel(cmd_table, title="[bold blue]Sent Config[/bold blue]", border_style="blue"),
                Panel(feedback_table, title="[bold magenta]Latest Feedback[/bold magenta]", border_style="magenta"),
                Text.from_markup(time_str, justify="center")
            ),
            title="[bold]Live Status[/bold]"
        )

    def run_tui(self):
        kb = KBHit()
        if not kb.active:
            self.console.print("[bold red]Error: Non-blocking input not supported on this platform.[/bold red]")
            return

        layout = self.make_layout()
        receiver = threading.Thread(target=self._receiver_thread, daemon=True)
        receiver.start()
        layout["header"].update(Panel(Text("SuperCap Monitor TUI | Type commands and press Enter", justify="center"), style="bold white on blue"))
        
        last_send_time = 0
        with Live(layout, screen=True, redirect_stderr=False) as live:
            while self.running:
                if kb.kbhit():
                    char = kb.getch()
                    if char in ('\r', '\n'):
                        self.process_command(self.command_buffer)
                        self.command_buffer = ""
                    elif char in ('\b', '\x7f'):
                        self.command_buffer = self.command_buffer[:-1]
                    else:
                        self.command_buffer += char

                if self.sending_enabled and time.time() - last_send_time > 0.1:
                    self.send_command()
                    last_send_time = time.time()

                layout["log"].update(self.get_command_log_panel())
                layout["status"].update(self.get_status_panel())
                layout["footer"].update(Panel(Text.from_markup(f"> {self.command_buffer}"), title="[bold]Command[/bold]", border_style="magenta"))
                time.sleep(1 / 60)
        
        kb.set_normal_term()
        self.running = False
        receiver.join(timeout=1)
        self.bus.shutdown()
        self.console.print("[bold green]Shutdown complete.[/bold green]")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Supercapacitor board monitor using slcan.')
    parser.add_argument('port', help='Serial port for the slcan adapter (e.g., COM3, /dev/ttyUSB0)')
    parser.add_argument('--baudrate', type=int, default=115200, help='Baudrate for the slcan adapter')
    args = parser.parse_args()

    console = Console()
    console.print("--- Welcome to SuperCap Monitor TUI ---")
    console.print(f"Attempting to connect to {args.port} at {args.baudrate} baud.")
    console.print("Please ensure you have installed rich: [bold]pip install rich[/bold]")

    try:
        monitor = SuperCapMonitor(args.port, args.baudrate)
        monitor.run_tui()
    except Exception as e:
        console.print(f"\n[bold red]An unexpected error occurred:[/bold red]")
        console.print_exception(show_locals=True)
