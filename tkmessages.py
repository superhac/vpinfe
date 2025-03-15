from enum import Enum, auto
from typing import Callable

class TKMsgType(Enum):
    ENABLE_STATUS_MSG  = auto
    DISABLE_STATUS_MSG = auto
    DISABLE_THREE_DOT  = auto
    CACHE_BUILD_COMPLETED = auto
    SHUTDOWN = auto
    
class TkMsg():
    def __init__(self, MsgType: TKMsgType, func: Callable, msg: str):
        self.msgType = MsgType
        self.call = func
        self.msg = msg

