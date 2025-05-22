import sdl2
import sdl2.ext
from screen import Screen
import time
import threading
from pinlog import get_logger
from tkmessages import TKMsgType, TkMsg

class JoystickHandler:
    logger = None

    def __init__(self, tk_queue, shutdown_event, tasks_manager):
        global logger
        logger = get_logger()

        self._tk_queue = tk_queue
        self._shutdown_event = shutdown_event
        self._tasks_manager = tasks_manager
        self.gameControllers = []

        self._open_joysticks()

    def _open_joysticks(self):
        logger.info("Checking for gamepads")
        if sdl2.SDL_InitSubSystem(sdl2.SDL_INIT_JOYSTICK) < 0:
            logger.error(f"SDL_InitSubSystem Error: {sdl2.SDL_GetError()}")
            return
        sdl2.joystick.SDL_JoystickEventState(sdl2.SDL_ENABLE)
        num_joysticks = sdl2.joystick.SDL_NumJoysticks()
        logger.info(f"Found {num_joysticks} joystick(s).")

        for i in range(num_joysticks):
            joystick = sdl2.joystick.SDL_JoystickOpen(i)
            if joystick:
                self.gameControllers.append(joystick)
                logger.info(f"Opened Joystick {i}: {sdl2.joystick.SDL_JoystickName(joystick).decode('utf-8', errors='ignore')}")
            else:
                logger.warning(f"Could not open joystick {i}: {sdl2.SDL_GetError()}")

    def _close_joysticks(self):
        logger.debug("Closing joysticks.")
        for joystick in self.gameControllers:
            logger.debug(f"Closing Joystick: {sdl2.joystick.SDL_JoystickName(joystick).decode('utf-8', errors='ignore')}")
            sdl2.joystick.SDL_JoystickClose(joystick)
        self.gameControllers = [] # Clear the list after closing
        logger.debug("Joysticks closed.")

    def _send_message(self, msg_type, data = None):
        self._tk_queue.put(TkMsg(msg_type, payload=data))
        Screen.rootWindow.event_generate("<<vpinfe_tk>>")

    def input_loop(self):
        while not self._shutdown_event.is_set():

            was_paused = self._tasks_manager.is_paused("gameControllerInput")

            self._tasks_manager.wait("gameControllerInput")
            if self._shutdown_event.is_set():
                break;

            if was_paused:
                for event in sdl2.ext.get_events():
                    # When we're paused SDL keep getting events that we don't want to process later.
                    pass

            event = sdl2.SDL_Event()
            while sdl2.SDL_PollEvent(event) != 0:
                if self._shutdown_event.is_set():
                    break;
                if event.type == sdl2.SDL_QUIT:
                    self._send_message(TKMsgType.SHUTDOWN)
                    break
                if event.type == sdl2.SDL_JOYAXISMOTION:
                    #axis_id = event.jaxis.axis
                    #axis_value = event.jaxis.value / 32767.0  # Normalize to -1.0 to 1.0
                    #logger.debug(f"Axis {axis_id}: {axis_value}")
                    pass
                elif event.type == sdl2.SDL_JOYBUTTONDOWN:
                    self._send_message(TKMsgType.JOY_BUTTON_DOWN, {'which': event.jbutton.which, 'button': event.jbutton.button})
                    #logger.debug(f"Joystick {event.jbutton.which} button {event.jbutton.button} pressed")
                elif event.type == sdl2.SDL_JOYBUTTONUP:
                    self._send_message(TKMsgType.JOY_BUTTON_UP, {'which': event.jbutton.which, 'button': event.jbutton.button})
                    #logger.debug(f"Joystick {event.jbutton.which} button {event.jbutton.button} released")
                if self._shutdown_event.is_set():
                    break;

            time.sleep(0.01)

        self._close_joysticks()
        logger.info("Joystick input thread stopped.")
