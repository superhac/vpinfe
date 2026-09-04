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
import threading

from common import events
from frontend.last_game import save_last_launched

logger = logging.getLogger("vpinfe.frontend.play_events")

# How long a run of game changes has to go quiet before the windows are sent back for the
# payload. An import touches one game at a time, and each refresh costs every window a
# rebuild of the whole list, so the burst is answered once.
CHANGE_COALESCE_SECONDS = 0.5

_registered = False
_bridge = None
_browser = None
_ini_config = None
_change_timer = None
_change_lock = threading.Lock()


# The same map vpinfe-core.js keeps as MESSAGE_TYPE_ALIASES, and it has to stay the same:
# a theme matches on whichever spelling it was written against, so both have to arrive.
# Empty now that the backend messages carry the Table* names 2.x published, and it has to
# be filled again the next time one of them is renamed.
_LEGACY_MESSAGE_TYPES: dict[str, str] = {}


def _mark_views_stale() -> None:
    """Tell the shared view the library moved, before the windows are sent for it.

    Set here rather than in each window's handler: the broadcast is one event and the
    refresh behind it should be one refresh, however many windows answer it.
    """
    if _bridge is None:
        return
    for api in list(getattr(_bridge, "_api_instances", {}).values()):
        view = getattr(api, "view", None)
        if view is not None:
            view.mark_stale()


def _broadcast(message: dict) -> None:
    if _bridge is None:
        return
    if message.get("type") == "TableDataChange":
        _mark_views_stale()
    _bridge.send_event_all_with_iframe(message)
    legacy = _LEGACY_MESSAGE_TYPES.get(message.get("type"))
    if legacy is not None:
        _bridge.send_event_all_with_iframe({**message, "type": legacy})


def on_launching(*, game=None, table_id="", **_payload) -> None:
    """Suppress frontend input and record where the player was.

    Runs after every hook, so a peripheral that refused the launch has already
    stopped this - input is never suppressed for a launch that is not happening.
    """
    if game is not None and _ini_config is not None:
        save_last_launched(_ini_config, game, table_id)
    _broadcast({"type": "TableLaunching"})
    if sys.platform == "win32" and _browser is not None:
        # VPX pauses whenever its player window loses focus, and Windows will not let a
        # process hand the foreground to one it spawned - so a table came up paused until
        # the user alt-tabbed. Out of the way, and VPX takes the foreground itself.
        try:
            _browser.minimize_all_windows()
        except Exception:
            logger.exception("Could not get the frontend windows out of VPX's way")


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
    if sys.platform == "win32" and _browser is not None:
        # Reached on every path out, including a launch that failed, so a cabinet with
        # no keyboard is never left staring at minimized windows.
        try:
            _browser.restore_all_windows()
        except Exception:
            logger.exception("Could not bring the frontend windows back")


def on_play_recorded(**_payload) -> None:
    """Send the windows back for the payload, now that the session is in it.

    Not on_exited: the exit is announced before the runtime and the score are written.
    """
    _broadcast({"type": "TableDataChange"})


def on_game_changed(**_payload) -> None:
    """A game or the collections file changed. Coalesced, never immediate."""
    global _change_timer
    with _change_lock:
        if _change_timer is not None:
            _change_timer.cancel()
        _change_timer = threading.Timer(CHANGE_COALESCE_SECONDS, _flush_game_changes)
        _change_timer.daemon = True
        _change_timer.start()


def _flush_game_changes() -> None:
    global _change_timer
    with _change_lock:
        _change_timer = None
    _broadcast({"type": "TableDataChange"})


def register(ws_bridge, frontend_browser=None, ini_config=None) -> None:
    """Attach the frontend's reaction to the game lifecycle. Idempotent."""
    global _registered, _bridge, _browser, _ini_config
    _bridge = ws_bridge
    _browser = frontend_browser
    _ini_config = ini_config
    if _registered:
        return

    events.subscribe(events.TABLE_LAUNCHING, on_launching)
    events.subscribe(events.TABLE_LAUNCHED, on_launched)
    events.subscribe(events.TABLE_EXITED, on_exited)
    events.subscribe(events.TABLE_PLAY_RECORDED, on_play_recorded)
    events.subscribe(events.GAME_CHANGED, on_game_changed)
    events.subscribe(events.COLLECTIONS_CHANGED, on_game_changed)
    _registered = True


def reset_for_tests() -> None:
    global _registered, _bridge, _browser, _ini_config, _change_timer
    _registered = False
    _bridge = _browser = _ini_config = None
    with _change_lock:
        if _change_timer is not None:
            _change_timer.cancel()
        _change_timer = None
