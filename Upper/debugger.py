# ...existing code...
import customtkinter as ctk
import tkinter as tk
import struct
import socket
import threading
import time
import can

# --- Configuration ---
# UDP settings for data plotting/streaming
UDP_IP = "127.0.0.1"
UDP_PORT = 23456

# CAN settings -
# IMPORTANT: Change these to match your hardware and setup
# See https://python-can.readthedocs.io/en/master/interfaces.html for interface names
# Common interfaces: 'pcan', 'vector', 'kvaser', 'slcan', 'seeed'
CAN_INTERFACE = 'slcan'
CAN_CHANNEL = 'COM3'  # e.g., 'PCAN_USBBUS1', 'can0', or a serial port for slcan
CAN_BITRATE = 1000000

# CAN message IDs
CONTROL_CAN_ID = 0x050
FEEDBACK_CAN_ID_OLD = 0x051
FEEDBACK_CAN_ID_NEW = 0x052

# --- Data Structures ---
class RxData:
    """Structure for data sent to the power board (Master -> SuperCap)"""
    def __init__(self):
        self.enableDCDC = 0
        self.systemRestart = 0
        self.clearError = 0
        self.enableActiveChargingLimit = 0
        self.useNewFeedbackMessage = 1
        self.refereePowerLimit = 80
        self.refereeEnergyBuffer = 50
        self.activeChargingLimitRatio = 200

    def pack(self):
        """Packs the data into an 8-byte array for CAN transmission."""
        byte0 = (
            (self.enableDCDC & 0x01) |
            ((self.systemRestart & 0x01) << 1) |
            ((self.clearError & 0x01) << 5) |
            ((self.enableActiveChargingLimit & 0x01) << 6) |
            ((self.useNewFeedbackMessage & 0x01) << 7)
        )
        # Format: <B H H B x (Byte, UShort, UShort, Byte, 1 padding byte)
        return struct.pack('<BHHB',
                           byte0,
                           self.refereePowerLimit,
                           self.refereeEnergyBuffer,
                           self.activeChargingLimitRatio)

class TxData:
    """Structure for data received from the power board (SuperCap -> Master)"""
    def __init__(self):
        # Common fields
        self.statusCode = 0
        self.capEnergy = 0
        self.chassisPowerLimit = 0

        # New format (0x052)
        self.chassisPower_new = 0.0
        self.refereePower_new = 0.0

        # Old format (0x051)
        self.chassisPower_old = 0.0
        
        self.is_new_format = False

    def unpack(self, msg: can.Message):
        """Unpacks data from a CAN message."""
        if msg.arbitration_id == FEEDBACK_CAN_ID_NEW and len(msg.data) >= 7:
            byte0, chassis_power_raw, referee_power_raw, limit_raw, energy_raw = struct.unpack('<BHНB', msg.data[:7])
            self.statusCode = byte0
            self.chassisPower_new = (chassis_power_raw - 16384) / 64.0
            self.refereePower_new = (referee_power_raw - 16384) / 64.0
            self.chassisPowerLimit = limit_raw
            self.capEnergy = energy_raw
            self.is_new_format = True
            return True
        elif msg.arbitration_id == FEEDBACK_CAN_ID_OLD and len(msg.data) >= 8:
            byte0, power_raw, limit_raw, energy_raw = struct.unpack('<BfHB', msg.data[:8])
            self.statusCode = byte0
            self.chassisPower_old = power_raw
            self.chassisPowerLimit = limit_raw
            self.capEnergy = energy_raw
            self.is_new_format = False
            return True
        return False


class CANManager(threading.Thread):
    """Handles all CAN communication in a separate thread."""
    def __init__(self, rx_callback, error_callback):
        super().__init__(daemon=True)
        self.rx_callback = rx_callback
        self.error_callback = error_callback
        self.bus = None
        self.running = False
        self.rx_data = RxData()
        self.auto_send_interval = 0.1  # seconds (10Hz)
        self.auto_send_enabled = False

    def connect(self, interface, channel, bitrate):
        """Connects to the CAN bus."""
        try:
            self.bus = can.interface.Bus(interface=interface, channel=channel, bitrate=bitrate)
            self.error_callback(f"Successfully connected to {interface} on {channel}.")
            self.running = True
            return True
        except Exception as e:
            self.error_callback(f"Error connecting to CAN: {e}")
            self.bus = None
            self.running = False
            return False

    def disconnect(self):
        """Disconnects from the CAN bus."""
        self.running = False
        if self.bus:
            self.bus.shutdown()
            self.bus = None
        self.error_callback("Disconnected from CAN bus.")

    def run(self):
        """Main loop for sending and receiving CAN messages."""
        last_send_time = 0
        while self.running and self.bus:
            # Auto-sending logic
            if self.auto_send_enabled and (time.time() - last_send_time > self.auto_send_interval):
                self.send_control_packet()
                last_send_time = time.time()

            # Receiving logic
            try:
                msg = self.bus.recv(timeout=0.05)
                if msg:
                    self.rx_callback(msg)
            except can.CanError as e:
                self.error_callback(f"CAN Receive Error: {e}")
                time.sleep(0.5) # Avoid spamming errors
        
        if self.bus:
            self.bus.shutdown()

    def send_control_packet(self):
        """Sends the control packet based on current rx_data."""
        if not self.bus or not self.running:
            self.error_callback("Cannot send: Not connected to CAN bus.")
            return
        
        try:
            packed_data = self.rx_data.pack()
            msg = can.Message(arbitration_id=CONTROL_CAN_ID, data=packed_data, is_extended_id=False, dlc=7)
            self.bus.send(msg)
        except Exception as e:
            self.error_callback(f"Error sending CAN message: {e}")
    
    def update_control_data(self, new_rx_data: RxData):
        """Thread-safe way to update the data to be sent."""
        self.rx_data = new_rx_data


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("SuperCap Debugger")
        self.geometry("850x650")
        ctk.set_appearance_mode("Dark")
        
        self.rx_data = RxData()
        self.tx_data = TxData()
        self.can_manager = CANManager(self.handle_can_message, self.log_message)
        self.udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        
        self.tx_vars = {}
        self.rx_labels = {}
        self.status_labels = {}

        self._create_widgets()

    def _create_widgets(self):
        """Create all the UI widgets."""
        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=2)
        self.grid_rowconfigure(2, weight=1)

        # --- Frames ---
        self.connection_frame = ctk.CTkFrame(self)
        self.connection_frame.grid(row=0, column=0, columnspan=2, padx=10, pady=10, sticky="nsew")
        self.connection_frame.grid_columnconfigure(5, weight=1)

        # tx_frame: 移除 text 参数，改为在 frame 内部添加标题 Label（使用 pack）
        self.tx_frame = ctk.CTkFrame(self)
        self.tx_frame.grid(row=1, column=0, padx=10, pady=10, sticky="nsew")
        ctk.CTkLabel(self.tx_frame, text="Transmit Control (Master -> SuperCap)", anchor="w").pack(fill='x', padx=10, pady=(8,4))

        # rx_frame: 移除 text 参数，添加标题 Label（使用 grid），并将内部行号下移 1 行
        self.rx_frame = ctk.CTkFrame(self)
        self.rx_frame.grid(row=1, column=1, padx=10, pady=10, sticky="nsew")
        ctk.CTkLabel(self.rx_frame, text="Receive Feedback (SuperCap -> Master)").grid(row=0, column=0, columnspan=2, padx=10, pady=(8,4), sticky="w")
        
        self.log_frame = ctk.CTkFrame(self)
        self.log_frame.grid(row=2, column=0, columnspan=2, padx=10, pady=10, sticky="nsew")
        self.log_frame.grid_rowconfigure(0, weight=1)
        self.log_frame.grid_columnconfigure(0, weight=1)

        # --- Connection Frame Widgets ---
        ctk.CTkLabel(self.connection_frame, text="Interface:").grid(row=0, column=0, padx=5, pady=5)
        self.can_interface_entry = ctk.CTkEntry(self.connection_frame)
        self.can_interface_entry.grid(row=0, column=1, padx=5, pady=5)
        self.can_interface_entry.insert(0, CAN_INTERFACE)

        ctk.CTkLabel(self.connection_frame, text="Channel:").grid(row=0, column=2, padx=5, pady=5)
        self.can_channel_entry = ctk.CTkEntry(self.connection_frame)
        self.can_channel_entry.grid(row=0, column=3, padx=5, pady=5)
        self.can_channel_entry.insert(0, CAN_CHANNEL)
        
        self.connect_button = ctk.CTkButton(self.connection_frame, text="Connect", command=self.toggle_can_connection)
        self.connect_button.grid(row=0, column=4, padx=10, pady=10)

        self.connection_status_label = ctk.CTkLabel(self.connection_frame, text="Disconnected", text_color="red")
        self.connection_status_label.grid(row=0, column=5, padx=5, pady=5, sticky="w")

        # --- Transmit Frame Widgets ---
        self.tx_vars['enableDCDC'] = ctk.BooleanVar(value=bool(self.rx_data.enableDCDC))
        ctk.CTkCheckBox(self.tx_frame, text="Enable DCDC", variable=self.tx_vars['enableDCDC']).pack(anchor='w', padx=10, pady=5)

        self.tx_vars['systemRestart'] = ctk.BooleanVar(value=bool(self.rx_data.systemRestart))
        ctk.CTkCheckBox(self.tx_frame, text="System Restart", variable=self.tx_vars['systemRestart']).pack(anchor='w', padx=10, pady=5)
        
        self.tx_vars['clearError'] = ctk.BooleanVar(value=bool(self.rx_data.clearError))
        ctk.CTkCheckBox(self.tx_frame, text="Clear Error", variable=self.tx_vars['clearError']).pack(anchor='w', padx=10, pady=5)

        self.tx_vars['enableActiveChargingLimit'] = ctk.BooleanVar(value=bool(self.rx_data.enableActiveChargingLimit))
        ctk.CTkCheckBox(self.tx_frame, text="Enable Active Charging Limit", variable=self.tx_vars['enableActiveChargingLimit']).pack(anchor='w', padx=10, pady=5)

        self.tx_vars['useNewFeedbackMessage'] = ctk.BooleanVar(value=bool(self.rx_data.useNewFeedbackMessage))
        ctk.CTkSwitch(self.tx_frame, text="Use New Feedback Message (0x052)", variable=self.tx_vars['useNewFeedbackMessage']).pack(anchor='w', padx=10, pady=15)
        
        self._create_tx_entry("refereePowerLimit", "Referee Power Limit (W)", self.rx_data.refereePowerLimit)
        self._create_tx_entry("refereeEnergyBuffer", "Referee Energy Buffer (J)", self.rx_data.refereeEnergyBuffer)
        self._create_tx_entry("activeChargingLimitRatio", "Active Charging Limit Ratio (0-255)", self.rx_data.activeChargingLimitRatio)

        ctk.CTkButton(self.tx_frame, text="Send Once", command=self.send_once).pack(fill='x', padx=10, pady=10)
        self.auto_send_switch = ctk.CTkSwitch(self.tx_frame, text="Auto-Send (10Hz)", command=self.toggle_auto_send)
        self.auto_send_switch.pack(anchor='w', padx=10, pady=10)

        # --- Receive Frame Widgets ---
        self.rx_frame.grid_columnconfigure(1, weight=1)
        # 注意：行号下移 1 行，因为在 rx_frame 内部已添加标题占用 row=0
        self._create_rx_label("chassisPower", "Chassis Power (W)", 1, "0.00")
        self._create_rx_label("refereePower", "Referee Power (W)", 2, "0.00")
        self._create_rx_label("chassisPowerLimit", "Chassis Power Limit (W)", 3, "0")
        self._create_rx_label("capEnergy", "Cap Energy (0-250)", 4, "0")
        
        # Status Code Details
        # 移除 text 参数，内部添加标题（row=0），并把后续 status label 行号下移 1 行（调用时加 1）
        status_frame = ctk.CTkFrame(self.rx_frame)
        status_frame.grid(row=5, column=0, columnspan=2, padx=10, pady=10, sticky="nsew")
        ctk.CTkLabel(status_frame, text="Status Code Details").grid(row=0, column=0, columnspan=2, padx=5, pady=(4,8), sticky="w")
        self._create_status_label(status_frame, "Power Stage", "power_stage", 1)
        self._create_status_label(status_frame, "Feedback Format", "feedback_format", 2)
        self._create_status_label(status_frame, "Control Loop Limit", "control_limit", 3)
        self._create_status_label(status_frame, "Error Level", "error_level", 4)

        # --- Log Frame Widgets ---
        self.log_textbox = ctk.CTkTextbox(self.log_frame, state='disabled', wrap='word')
        self.log_textbox.grid(row=0, column=0, sticky="nsew")
        
    def _create_tx_entry(self, key, text, default_value):
        frame = ctk.CTkFrame(self.tx_frame, fg_color="transparent")
        frame.pack(fill='x', padx=10, pady=5)
        ctk.CTkLabel(frame, text=text).pack(side='left')
        self.tx_vars[key] = ctk.StringVar(value=str(default_value))
        entry = ctk.CTkEntry(frame, textvariable=self.tx_vars[key])
        entry.pack(side='right')

    def _create_rx_label(self, key, text, row, default_value):
        ctk.CTkLabel(self.rx_frame, text=f"{text}:").grid(row=row, column=0, padx=10, pady=5, sticky="w")
        self.rx_labels[key] = ctk.CTkLabel(self.rx_frame, text=default_value, font=ctk.CTkFont(weight="bold"))
        self.rx_labels[key].grid(row=row, column=1, padx=10, pady=5, sticky="w")
        
    def _create_status_label(self, parent, text, key, row):
        ctk.CTkLabel(parent, text=f"{text}:").grid(row=row, column=0, padx=10, pady=2, sticky="w")
        self.status_labels[key] = ctk.CTkLabel(parent, text="N/A", font=ctk.CTkFont(weight="bold"))
        self.status_labels[key].grid(row=row, column=1, padx=10, pady=2, sticky="w")


    def toggle_can_connection(self):
        if self.can_manager.running:
            self.can_manager.disconnect()
            self.connect_button.configure(text="Connect")
            self.connection_status_label.configure(text="Disconnected", text_color="red")
        else:
            interface = self.can_interface_entry.get()
            channel = self.can_channel_entry.get()
            print(f"Connecting to CAN interface '{interface}' on channel '{channel}'...")
            if self.can_manager.connect(interface, channel, CAN_BITRATE):
                self.can_manager.start()
                self.connect_button.configure(text="Disconnect")
                self.connection_status_label.configure(text="Connected", text_color="green")

    def update_control_data_from_ui(self):
        """Reads values from the UI and updates the rx_data object."""
        try:
            self.rx_data.enableDCDC = self.tx_vars['enableDCDC'].get()
            self.rx_data.systemRestart = self.tx_vars['systemRestart'].get()
            self.rx_data.clearError = self.tx_vars['clearError'].get()
            self.rx_data.enableActiveChargingLimit = self.tx_vars['enableActiveChargingLimit'].get()
            self.rx_data.useNewFeedbackMessage = self.tx_vars['useNewFeedbackMessage'].get()
            self.rx_data.refereePowerLimit = int(self.tx_vars['refereePowerLimit'].get())
            self.rx_data.refereeEnergyBuffer = int(self.tx_vars['refereeEnergyBuffer'].get())
            self.rx_data.activeChargingLimitRatio = int(self.tx_vars['activeChargingLimitRatio'].get())
            self.can_manager.update_control_data(self.rx_data)
            return True
        #except (ValueError, TclError) as e:
        except Exception as e:
            self.log_message(f"Invalid input: {e}")
            return False

    def send_once(self):
        if self.update_control_data_from_ui():
            self.can_manager.send_control_packet()

    def toggle_auto_send(self):
        self.can_manager.auto_send_enabled = not self.can_manager.auto_send_enabled
        if self.can_manager.auto_send_enabled:
            self.log_message("Auto-send enabled.")
            # Continuously update data while auto-sending
            def data_updater():
                if self.can_manager.auto_send_enabled:
                    self.update_control_data_from_ui()
                    self.after(100, data_updater) # update every 100ms
            data_updater()
        else:
            self.log_message("Auto-send disabled.")

    def handle_can_message(self, msg):
        """Callback for incoming CAN messages."""
        if self.tx_data.unpack(msg):
            self.after(0, self.update_rx_display) # Schedule UI update on main thread
            self.send_udp_data()

    def update_rx_display(self):
        """Updates the feedback display labels in the UI."""
        # Update main values
        if self.tx_data.is_new_format:
            self.rx_labels['chassisPower'].configure(text=f"{self.tx_data.chassisPower_new:.2f}")
            self.rx_labels['refereePower'].configure(text=f"{self.tx_data.refereePower_new:.2f}")
        else:
            self.rx_labels['chassisPower'].configure(text=f"{self.tx_data.chassisPower_old:.2f}")
            self.rx_labels['refereePower'].configure(text="N/A (Old Fmt)")

        self.rx_labels['chassisPowerLimit'].configure(text=f"{self.tx_data.chassisPowerLimit}")
        self.rx_labels['capEnergy'].configure(text=f"{self.tx_data.capEnergy}")
        
        # Decode and display status code
        status = self.tx_data.statusCode
        self.status_labels['power_stage'].configure(text="ON" if (status >> 7) & 1 else "OFF")
        self.status_labels['feedback_format'].configure(text="New (0x052)" if (status >> 6) & 1 else "Old (0x051)")
        
        limit_reasons = ["None", "Vcap Max", "Vbus Max", "Ibus Max"]
        self.status_labels['control_limit'].configure(text=limit_reasons[(status >> 2) & 0b11])

        error_levels = ["No Error", "Auto-Recover", "Manual Recover", "Unrecoverable"]
        self.status_labels['error_level'].configure(text=error_levels[status & 0b11])


    def send_udp_data(self):
        """Formats and sends data via UDP."""
        try:
            if self.tx_data.is_new_format:
                data_str = f"chassisPower={self.tx_data.chassisPower_new:.2f},refereePower={self.tx_data.refereePower_new:.2f},"
            else:
                data_str = f"chassisPower={self.tx_data.chassisPower_old:.2f},"
            
            data_str += f"chassisPowerLimit={self.tx_data.chassisPowerLimit},capEnergy={self.tx_data.capEnergy}\r\n"
            
            self.udp_socket.sendto(data_str.encode(), (UDP_IP, UDP_PORT))
        except Exception as e:
            self.log_message(f"UDP Send Error: {e}")

    def log_message(self, msg):
        """Adds a message to the log textbox."""
        self.log_textbox.configure(state='normal')
        self.log_textbox.insert('end', f"[{time.strftime('%H:%M:%S')}] {msg}\n")
        self.log_textbox.see('end')
        self.log_textbox.configure(state='disabled')

    def on_closing(self):
        """Handles window closing event."""
        if self.can_manager.running:
            self.can_manager.disconnect()
        self.destroy()


if __name__ == "__main__":
    app = App()
    app.protocol("WM_DELETE_WINDOW", app.on_closing)
    app.mainloop()