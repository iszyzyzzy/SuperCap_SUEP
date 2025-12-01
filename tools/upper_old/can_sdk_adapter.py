import time
from typing import Callable, List
import canSDK

class Canbus:
    def __init__(self, nom_baud: int, dat_baud: int, sn: str):
        self.usb_hw = canSDK.usb_class(nom_baud, dat_baud, sn)
        self.callback: Callable[[canSDK.can_value_type], None] | None = None
        time.sleep(0.5)
        self.usb_hw.setFrameCallback(lambda val: self._internal_callback(val))
        time.sleep(0.2)

    def _internal_callback(self, value: canSDK.can_value_type):
        if self.callback:
            self.callback(value)

    def set_callback(self, callback: Callable[[canSDK.can_value_type], None]):
        self.callback = callback

    def send(self, can_id: int, data: List[int]):
        self.usb_hw.fdcanFrameSend(data, can_id)

    def close(self):
        if self.usb_hw.getDeviceHandle() is not None:
            self.usb_hw.close()

    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
