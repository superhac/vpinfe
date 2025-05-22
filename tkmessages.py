from enum import Enum, auto
from typing import Callable

class TKMsgType(Enum):
    ENABLE_STATUS_MSG  = auto()
    DISABLE_STATUS_MSG = auto()
    DISABLE_THREE_DOT  = auto()
    CACHE_BUILD_COMPLETED = auto()
    SHUTDOWN = auto()
    JOY_BUTTON_DOWN = auto()
    JOY_BUTTON_UP = auto()
    JOY_AXIS_MOTION = auto()
    
class TkMsg():
    def __init__(self, MsgType: TKMsgType, func: Callable = None, payload: dict = None):
        self.msgType = MsgType
        self.call = func
        self.payload = payload if payload is not None else {}
