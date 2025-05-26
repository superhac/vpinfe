#!/usr/bin/env python3

from __future__ import print_function


from inputs import get_gamepad, devices

def main():
    print("Devices")
    for device in devices:
        print(device)
    print("\nWaiting for input.")
    """Just print out some event infomation when the gamepad is used."""
    while 1:
        events = get_gamepad()
        for event in events:
            print(event.ev_type, event.code, event.state)


if __name__ == "__main__":
    main()
