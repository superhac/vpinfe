"""What the frontend does about a launch, wherever the launch came from.

The window messages used to be written into the launch itself, which is why only
launches started from the wheel produced them. They are subscribers now, so a
launch from the Remote Control page or the API drives the windows the same way.

Registered once per process against the shared bridge - every API instance sends
through the same one, so registering per window would send each message three
times.
"""

from __future__ import annotations

import logging
import sys

from common import events
from frontend.last_table import save_last_table

logger = logging.getLogger("vpinfe.frontend.play_events")

_registered = False
_bridge = None
_browser = None
_ini_config = None


def _broadcast(message: dict) -> None:
    if _bridge is not None:
        _bridge.send_event_all_with_iframe(message)


def on_launching(*, table=None, **_payload) -> None:
    """Suppress frontend input and record where the player was.

    Runs after every hook, so a peripheral that refused the launch has already
    stopped this - input is never suppressed for a launch that is not happening.
    """
    if table is not None and _ini_config is not None:
        save_last_table(_ini_config, table)
    _broadcast({"type": "TableLaunching"})


def on_launched(**_payload) -> None:
    """The table is actually up, not merely started."""
    _broadcast({"type": "TableRunning"})


def on_exited(**_payload) -> None:
    """Always reached once a launch was announced, so input always comes back."""
    _broadcast({"type": "TableLaunchComplete"})
    if sys.platform == "darwin" and _browser is not None:
        try:
            _browser.activate_all_mac()
        except Exception:
            logger.exception("Could not bring the frontend windows back to the front")


def register(ws_bridge, frontend_browser=None, ini_config=None) -> None:
    """Attach the frontend's reaction to the table lifecycle. Idempotent."""
    global _registered, _bridge, _browser, _ini_config
    _bridge = ws_bridge
    _browser = frontend_browser
    _ini_config = ini_config
    if _registered:
        return

    events.subscribe(events.TABLE_LAUNCHING, on_launching)
    events.subscribe(events.TABLE_LAUNCHED, on_launched)
    events.subscribe(events.TABLE_EXITED, on_exited)
    _registered = True


def reset_for_tests() -> None:
    global _registered, _bridge, _browser, _ini_config
    _registered = False
    _bridge = _browser = _ini_config = None
