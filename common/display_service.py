from __future__ import annotations

import sys


def get_display_monitors():
    if sys.platform == "darwin":
        from frontend.chromium_manager import get_mac_screens

        return get_mac_screens()

    from screeninfo import get_monitors

    return get_monitors()


def monitors_as_dicts():
    return [
        {
            "name": f"Monitor {i}",
            "x": monitor.x,
            "y": monitor.y,
            "width": monitor.width,
            "height": monitor.height,
        }
        for i, monitor in enumerate(get_display_monitors())
    ]
