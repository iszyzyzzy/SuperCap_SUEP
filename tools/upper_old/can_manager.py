import threading
import time
from can_sdk_adapter import Canbus
from canSDK import can_value_type
from typing import Callable

# --- Configuration ---
# CAN message IDs
CONTROL_CAN_ID = 0x050

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
        import struct
        return list(struct.pack('<BHHB',
                           byte0,
                           self.refereePowerLimit,
                           self.refereeEnergyBuffer,
                           self.activeChargingLimitRatio))

class CANManager(threading.Thread):
    """Handles all CAN communication in a separate thread using the new SDK."""
    def __init__(self, rx_callback: Callable[[can_value_type], None], error_callback: Callable[[str], None]):
        super().__init__(daemon=True)
        self.rx_callback = rx_callback
        self.error_callback = error_callback
        self.bus: Canbus | None = None
        self.running = False
        self.rx_data = RxData()
        self.auto_send_interval = 0.1  # seconds (10Hz)
        self.auto_send_enabled = False
        self.device_sn = ""

    def connect(self, sn: str, nom_bitrate: int, data_bitrate: int):
        """Connects to the CAN bus using the SDK."""
        try:
            self.device_sn = sn
            self.bus = Canbus(nom_baud=nom_bitrate, dat_baud=data_bitrate, sn=self.device_sn)
            self.bus.set_callback(self.rx_callback)
            self.error_callback(f"Successfully connected to device with SN: {sn}.")
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
            self.bus.close()
            self.bus = None
        self.error_callback("Disconnected from CAN bus.")

    def run(self):
        """Main loop for sending CAN messages."""
        last_send_time = 0
        while self.running and self.bus:
            # Auto-sending logic
            if self.auto_send_enabled and (time.time() - last_send_time > self.auto_send_interval):
                self.send_control_packet()
                last_send_time = time.time()
            
            # The receiving is handled by the callback, so we just need to keep the thread alive
            time.sleep(0.01)

    def send_control_packet(self):
        """Sends the control packet based on current rx_data."""
        if not self.bus or not self.running:
            self.error_callback("Cannot send: Not connected to CAN bus.")
            return
        
        try:
            packed_data = self.rx_data.pack()
            self.bus.send(CONTROL_CAN_ID, packed_data)
        except Exception as e:
            self.error_callback(f"Error sending CAN message: {e}")
    
    def update_control_data(self, new_rx_data: RxData):
        """Thread-safe way to update the data to be sent."""
        self.rx_data = new_rx_data

