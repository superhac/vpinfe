from threading import Thread, Event
from logger import get_logger
import time

class PauseableTask:
    logger = None

    def __init__(self, name, target_func):
        global logger
        logger = get_logger()

        self._pause_event = Event()
        self._pause_event.set()  # Set is unpause, clear is paused
        self._name = name
        logger.debug(f"Created {self._name} thread.")

    def start(self):
        logger.debug(f"Starting {self._name} thread.")
        self._target_func()

    def is_paused(self):
        return not self._pause_event.is_set()

    def pause(self):
        logger.debug(f"Pausing {self._name} thread.")
        self._pause_event.clear()

    def resume(self):
        logger.debug(f"Resuming {self._name} thread.")
        self._pause_event.set()

    def sleep(self, duration):
        time.sleep(duration)

    def stop(self):
        logger.debug(f"Stopping {self._name} thread.")
        self._pause_event.set()  # Unpause so it can exit the loop if paused
