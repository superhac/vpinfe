from __future__ import annotations

import logging
import sys
import threading

logger = logging.getLogger("vpinfe.common.host.display_service")


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
    """Every display this machine has, or none when it cannot say.

    Enumeration fails on a machine with no session attached - a headless server, a
    container, a session that has gone away - and it used to raise from here. The theme
    asks for this list while it is starting up, so the throw left the frontend connected,
    serving contract 2, and never finishing: a blank screen with everything reporting
    healthy. No monitors is a thing callers already handle; not answering is not.
    """
    global _monitors_cache
    with _monitors_lock:
        if refresh or _monitors_cache is None:
            try:
                _monitors_cache = _query_monitors()
            except Exception:
                logger.warning("Could not enumerate displays; continuing with none",
                               exc_info=True)
                _monitors_cache = []
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
