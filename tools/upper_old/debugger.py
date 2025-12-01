# ...existing code...
import customtkinter as ctk
import tkinter as tk
import struct
import socket
import threading
import time
import subprocess
import sys
from can_manager import CANManager, RxData
import canSDK


# --- Configuration ---
# UDP settings for data plotting/streaming
UDP_IP = "127.0.0.1"
UDP_PORT = 23456

# CAN settings for the new SDK
NOMINAL_BITRATE = 1000000
DATA_BITRATE = 5000000
DEFAULT_SN = "14AA044B241402B10DDBDAFE448040BB" # Replace with your device's SN

# CAN message IDs
CONTROL_CAN_ID = 0x050
FEEDBACK_CAN_ID_OLD = 0x051
FEEDBACK_CAN_ID_NEW = 0x052

# --- Data Structures ---
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

    def unpack(self, msg: canSDK.can_value_type):
        """Unpacks data from a can_value_type message."""
        can_id = msg.head.id
        data = msg.data

        if can_id == FEEDBACK_CAN_ID_NEW and msg.head.dlc >= 7:
            # Note: The data from can_value_type is a list of bytes.
            # We need to convert it to a bytes object for struct.unpack.
            unpacked_data = struct.unpack('<BHНB', bytes(data[:7]))
            byte0, chassis_power_raw, referee_power_raw, limit_raw, energy_raw = unpacked_data
            self.statusCode = byte0
            self.chassisPower_new = (chassis_power_raw - 16384) / 64.0
            self.refereePower_new = (referee_power_raw - 16384) / 64.0
            self.chassisPowerLimit = limit_raw
            self.capEnergy = energy_raw
            self.is_new_format = True
            return True
        elif can_id == FEEDBACK_CAN_ID_OLD and msg.head.dlc >= 8:
            unpacked_data = struct.unpack('<BfHB', bytes(data[:8]))
            byte0, power_raw, limit_raw, energy_raw = unpacked_data
            self.statusCode = byte0
            self.chassisPower_old = power_raw
            self.chassisPowerLimit = limit_raw
            self.capEnergy = energy_raw
            self.is_new_format = False
            return True
        return False

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
        self.connection_frame.grid_columnconfigure(3, weight=1)

        self.tx_frame = ctk.CTkFrame(self)
        self.tx_frame.grid(row=1, column=0, padx=10, pady=10, sticky="nsew")
        ctk.CTkLabel(self.tx_frame, text="Transmit Control (Master -> SuperCap)", anchor="w").pack(fill='x', padx=10, pady=(8,4))

        self.rx_frame = ctk.CTkFrame(self)
        self.rx_frame.grid(row=1, column=1, padx=10, pady=10, sticky="nsew")
        ctk.CTkLabel(self.rx_frame, text="Receive Feedback (SuperCap -> Master)").grid(row=0, column=0, columnspan=2, padx=10, pady=(8,4), sticky="w")
        
        self.log_frame = ctk.CTkFrame(self)
        self.log_frame.grid(row=2, column=0, columnspan=2, padx=10, pady=10, sticky="nsew")
        self.log_frame.grid_rowconfigure(0, weight=1)
        self.log_frame.grid_columnconfigure(0, weight=1)

        # --- Connection Frame Widgets ---
        ctk.CTkLabel(self.connection_frame, text="Device SN:").grid(row=0, column=0, padx=5, pady=5)
        self.sn_entry = ctk.CTkEntry(self.connection_frame, width=300)
        self.sn_entry.grid(row=0, column=1, padx=5, pady=5)
        self.sn_entry.insert(0, DEFAULT_SN)

        self.find_sn_button = ctk.CTkButton(self.connection_frame, text="Find SN", command=self.find_serial_number, width=80)
        self.find_sn_button.grid(row=0, column=2, padx=5, pady=5)
        
        self.connect_button = ctk.CTkButton(self.connection_frame, text="Connect", command=self.toggle_can_connection)
        self.connect_button.grid(row=0, column=3, padx=10, pady=10, sticky="w")

        self.connection_status_label = ctk.CTkLabel(self.connection_frame, text="Disconnected", text_color="red")
        self.connection_status_label.grid(row=0, column=4, padx=5, pady=5, sticky="w")

        # ... (rest of the widget creation is the same, just need to make sure the class names match)

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
        self._create_rx_label("chassisPower", "Chassis Power (W)", 1, "0.00")
        self._create_rx_label("refereePower", "Referee Power (W)", 2, "0.00")
        self._create_rx_label("chassisPowerLimit", "Chassis Power Limit (W)", 3, "0")
        self._create_rx_label("capEnergy", "Cap Energy (0-250)", 4, "0")
        
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

    def find_serial_number(self):
        self.log_message("Attempting to find device serial number...")
        try:
            # We assume dev_sn.py is in the same directory or in the path
            process = subprocess.Popen([sys.executable, 'Upper/canSDK/Python/dev_sn.py'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            stdout, stderr = process.communicate(timeout=15)
            
            if process.returncode == 0:
                self.log_message("dev_sn.py executed successfully.")
                # Parse stdout to find the SN
                sn_found = False
                for line in stdout.splitlines():
                    if "SN:" in line:
                        sn = line.split("SN:")[1].strip()
                        self.sn_entry.delete(0, 'end')
                        self.sn_entry.insert(0, sn)
                        self.log_message(f"Found and updated SN: {sn}")
                        sn_found = True
                        break
                if not sn_found:
                    self.log_message("Could not parse SN from dev_sn.py output.")
                    self.log_message(f"Output:\n{stdout}")
            else:
                self.log_message(f"Error running dev_sn.py (Code: {process.returncode})")
                self.log_message(f"Error Output:\n{stderr}")

        except FileNotFoundError:
            self.log_message("Error: 'dev_sn.py' not found. Make sure it's in the 'Upper/canSDK/Python/' directory.")
        except subprocess.TimeoutExpired:
            self.log_message("Error: 'dev_sn.py' timed out.")
        except Exception as e:
            self.log_message(f"An error occurred while running dev_sn.py: {e}")

    def toggle_can_connection(self):
        if self.can_manager.running:
            self.can_manager.disconnect()
            self.connect_button.configure(text="Connect")
            self.connection_status_label.configure(text="Disconnected", text_color="red")
        else:
            sn = self.sn_entry.get()
            if not sn:
                self.log_message("Serial Number cannot be empty.")
                return

            self.log_message(f"Connecting to device with SN '{sn}'...")
            if self.can_manager.connect(sn, NOMINAL_BITRATE, DATA_BITRATE):
                self.can_manager.start()
                self.connect_button.configure(text="Disconnect")
                self.connection_status_label.configure(text="Connected", text_color="green")
            else:
                # Error message is handled by the CANManager's callback
                pass

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
            def data_updater():
                if self.can_manager.auto_send_enabled:
                    self.update_control_data_from_ui()
                    self.after(100, data_updater) # update every 100ms
            data_updater()
        else:
            self.log_message("Auto-send disabled.")

    def handle_can_message(self, msg: canSDK.can_value_type):
        """Callback for incoming CAN messages from the new manager."""
        if self.tx_data.unpack(msg):
            self.after(0, self.update_rx_display) # Schedule UI update on main thread
            self.send_udp_data()

    def update_rx_display(self):
        """Updates the feedback display labels in the UI."""
        if self.tx_data.is_new_format:
            self.rx_labels['chassisPower'].configure(text=f"{self.tx_data.chassisPower_new:.2f}")
            self.rx_labels['refereePower'].configure(text=f"{self.tx_data.refereePower_new:.2f}")
        else:
            self.rx_labels['chassisPower'].configure(text=f"{self.tx_data.chassisPower_old:.2f}")
            self.rx_labels['refereePower'].configure(text="N/A (Old Fmt)")

        self.rx_labels['chassisPowerLimit'].configure(text=f"{self.tx_data.chassisPowerLimit}")
        self.rx_labels['capEnergy'].configure(text=f"{self.tx_data.capEnergy}")
        
        status = self.tx_data.statusCode
        self.status_labels['power_stage'].configure(text="ON" if (status >> 7) & 1 else "OFF")
        self.status_labels['feedback_format'].configure(text="New (0x052)" if (status >> 6) & 1 else "Old (0x051)")
        
        limit_reasons = ["None", "Vcap Max", "Vbus Max", "Ibus Max", "I_L Max"]
        limit_index = (status >> 2) & 0b111
        if limit_index >= len(limit_reasons): limit_index = 0
        self.status_labels['control_limit'].configure(text=limit_reasons[limit_index])

        error_levels = ["No Error", "Warning", "Error", "Fatal"]
        error_index = status & 0b11
        self.status_labels['error_level'].configure(text=error_levels[error_index])


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