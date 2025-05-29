from pinlog import get_logger
from ui.imageworkermanager import ImageWorkerManager
from config import Config
from typing import List
from inputdefs import InputDefs
from ui.fullscreenimagewindow import FullscreenImageWindow


class InputController():
    def __init__(self, icms : List[ImageWorkerManager],vpinfeIniConfig : Config ):
        self.logger = get_logger()
        self.icms = icms
        self.vpinfeIniConfig = vpinfeIniConfig
        
    def input(self, response):
        match response[0]:
            case "gamepad":
                msg = response[1]
                self.logger.debug(f"gamepad msg: {msg}")
                if msg['code'] == self.vpinfeIniConfig.get_string('Settings','joyleft','') and msg['state'] == 1 or msg['state'] == -1 : # left move
                    windows = FullscreenImageWindow.windows
                    for win in windows:
                        win.processInputControl(InputDefs.LEFT)
                elif msg['code'] == self.vpinfeIniConfig.get_string('Settings','joyright','') and msg['state'] == 1 or msg['state'] == -1: # right move
                    windows = FullscreenImageWindow.windows
                    for win in windows:
                        win.processInputControl(InputDefs.RIGHT)
                elif msg['code'] == self.vpinfeIniConfig.get_string('Settings','joymenu','') and msg['state'] == 1 or msg['state'] == -1: # menu
                    windows = FullscreenImageWindow.windows
                    for win in windows:
                        win.processInputControl(InputDefs.MENU)
                elif msg['code'] == self.vpinfeIniConfig.get_string('Settings','joyselect','') and msg['state'] == 1 or msg['state'] == -1: # Select
                    print("got selected")
                    windows = FullscreenImageWindow.windows
                    for win in windows:
                        selected =  win.processInputControl(InputDefs.SELECT)
                        if selected:
                            print(selected)
                        
                       
                
    