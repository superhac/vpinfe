from pinlog import get_logger
from ui.imageworkermanager import ImageWorkerManager
from config import Config
from typing import List


class InputController():
    def __init__(self, icms : List[ImageWorkerManager],vpinfeIniConfig : Config ):
        self.logger = get_logger()
        self.icms = icms
        self.vpinfeIniConfig = vpinfeIniConfig
        
    def input(self, responses):
        for msg in responses:
            # GamePad Events
                self.logger.debug(f"gamepad-1 msg: {msg}")
                if msg['code'] == self.vpinfeIniConfig.get_string('Settings','joyleft','') and msg['state'] == 1 or msg['state'] == -1 : # left move
                    self.nextImage()
                elif msg['code'] == self.vpinfeIniConfig.get_string('Settings','joyright','') and msg['state'] == 1 or msg['state'] == -1: # left move
                    self.prevImage()
                    
    def nextImage(self):
        for manager in self.icms:
            manager.load_next()

    def prevImage(self):
        for manager in self.icms:
                manager.load_previous()