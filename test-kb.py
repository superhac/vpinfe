"""Simple example showing how to get keyboard events."""

from threading import Thread, Event
import time
from thirdparty.inputs import devices, get_key
import sys

def main():
    keyboard = devices.keyboards[0]
    """Just print out some event infomation when keys are pressed."""
    while 1:
        events = keyboard._do_iter()
        if events:
            for event in events:
                print(event.ev_type, event.code, event.state)
        time.sleep(0.01)

if __name__ == "__main__":
    main()
