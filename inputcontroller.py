import logging
from ui.imageworkermanager import ImageWorkerManager
from config import Config
from typing import List
from inputdefs import InputDefs
from ui.fullscreenimagewindow import FullscreenImageWindow
from globalsignals import dispatcher

class InputController():
    def __init__(self, vpinfeIniConfig : Config ):
        self.logger = logging.getLogger()
        self.vpinfeIniConfig = vpinfeIniConfig
        
    def input(self, response):
        match response[0]:
            case "gamepad":
                msg = response[1]
                #self.logger.debug(f"gamepad msg: {msg}")
                if msg['code'] == self.vpinfeIniConfig.get_string('Settings','joyleft','') and msg['state'] == 1 or msg['state'] == -1 : # left move
                    dispatcher.customEvent.emit("gamepad", {"op": InputDefs.LEFT})
                elif msg['code'] == self.vpinfeIniConfig.get_string('Settings','joyright','') and msg['state'] == 1 or msg['state'] == -1: # right move
                    dispatcher.customEvent.emit("gamepad", {"op": InputDefs.RIGHT})
                elif msg['code'] == self.vpinfeIniConfig.get_string('Settings','joymenu','') and msg['state'] == 1 or msg['state'] == -1: # menu
                    dispatcher.customEvent.emit("gamepad", {"op": InputDefs.MENU})
                elif msg['code'] == self.vpinfeIniConfig.get_string('Settings','joyselect','') and msg['state'] == 1 or msg['state'] == -1: # Select
                        dispatcher.customEvent.emit("gamepad", {"op": InputDefs.SELECT})
        return None