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
        self._target_func = target_func
        self._running = False

        logger.debug(f"Created {self._name} thread.")

    def start(self):
        logger.debug(f"Starting {self._name} thread.")
        self._running = True
        self._target_func()
        self._running = False
        logger.debug(f"Completed {self._name} thread.")

    def is_running(self):
        return self._running

    def is_paused(self):
        return self.is_running() and not self._pause_event.is_set()

    def pause(self):
        logger.debug(f"Pausing {self._name} thread.")
        self._pause_event.clear()

    def resume(self):
        logger.debug(f"Resuming {self._name} thread.")
        self._pause_event.set()

    def sleep(self, duration):
        time.sleep(duration)

    def wait(self):
        waited = False
        if self.is_paused():
            logger.debug(f"Waiting for {self._name} thread to resume.")
            waited = True
        self._pause_event.wait()
        if waited:
            logger.debug(f"Continuing {self._name} thread.")

    def stop(self):
        logger.debug(f"Stopping {self._name} thread.")
        self._pause_event.set()  # Unpause so it can exit if paused
