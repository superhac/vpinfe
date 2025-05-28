#!/usr/bin/env python3
import threading
import queue
import time
from inputs import get_gamepad, devices
from screen import Screen
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
        self.event_queue = queue.Queue()

        self._open_joysticks()
        self._start_poll_thread()

    def _open_joysticks(self):
        logger.info("Checking for gamepads")
        gamepads = devices.gamepads
        if not gamepads:
            logger.warning("No gamepads found.")
        else:
            for pad in gamepads:
                logger.info(f"Found gamepad: {pad.name}")

    def _close_joysticks(self):
        logger.debug("Joysticks closed.")

    def _send_message(self, msg_type, data=None):
        self._tk_queue.put(TkMsg(msg_type, payload=data))
        Screen.rootWindow.event_generate("<<vpinfe_tk>>")

    def _start_poll_thread(self):
        def poll():
            while not self._shutdown_event.is_set():
                event_list = []

                if not devices.gamepads:
                    sleep(0.5)
                    continue

                try:
                    event_list = get_gamepad()
                except Exception as e:
                    logger.warning(f"Polling error: {e}")
                    event_list = []

                for event in event_list:
                    self.event_queue.put(event)

        self._poll_thread = threading.Thread(target=poll, daemon=True)
        self._poll_thread.start()
        logger.info("Gamepad polling thread started.")

    def input_loop(self):
        while not self._shutdown_event.is_set():
            self._tasks_manager.wait("gameControllerInput")

            if self._shutdown_event.is_set():
                break

            try:
                while not self.event_queue.empty():
                    event = self.event_queue.get_nowait()
                    if event.ev_type == "Key":
                        if event.state == 1:
                            self._send_message(TKMsgType.JOY_BUTTON_DOWN, {'code': event.code, 'state': event.state})
                        elif event.state == 0:
                            self._send_message(TKMsgType.JOY_BUTTON_UP, {'code': event.code, 'state': event.state})
                    elif event.ev_type == "Absolute":
                        self._send_message(TKMsgType.JOY_AXIS_MOTION, {'code': event.code, 'state': event.state})
            except queue.Empty:
                pass

            time.sleep(0.01)

        self._close_joysticks()
        logger.info("Joystick input thread stopped.")
