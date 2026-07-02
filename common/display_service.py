from __future__ import annotations

import sys
import threading


# Xlib / libxcb / libXau are NOT thread-safe. screeninfo.get_monitors() opens an
# X11 display connection via ctypes, so calling it from several pywebview worker
# threads at once (each window's JS calls api.get_monitors() on its own thread)
# races inside libXau and corrupts the malloc heap -> SIGABRT. Serialize access
# with a lock and cache the result: monitor geometry is static for a session, so
# after the first successful query no further X connections are opened.
_monitors_lock = threading.Lock()
_monitors_cache = None


def _query_monitors():
    if sys.platform == "darwin":
        from frontend.chromium_manager import get_mac_screens

        return get_mac_screens()

    from screeninfo import get_monitors

    return get_monitors()


def get_display_monitors(refresh: bool = False):
    global _monitors_cache
    with _monitors_lock:
        if refresh or _monitors_cache is None:
            _monitors_cache = _query_monitors()
        return _monitors_cache


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
