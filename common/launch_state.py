"""Whether a launch has been requested from somewhere other than the frontend.

The Remote Control page sets this so the frontend can put an overlay up before VPX
takes the screen. Every change is announced as `play.state_changed`, so a consumer
can be told instead of asking: the frontend polls today, and the poll retires once
there is a stream to subscribe to.

Play-host state: it describes what is happening on this machine.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass

from common import events

_lock = threading.Lock()


@dataclass(frozen=True)
class LaunchState:
    launching: bool = False
    table_name: str | None = None

    def as_dict(self) -> dict:
        return {"launching": self.launching, "table_name": self.table_name}


_state = LaunchState()


def current() -> LaunchState:
    with _lock:
        return _state


def _replace(new_state: LaunchState) -> LaunchState:
    """Swap the state and announce it, if it actually changed.

    The event goes out after the lock is released. Handlers are arbitrary code and
    may well read the state back; publishing while holding the lock would deadlock
    the first one that did.
    """
    global _state
    with _lock:
        if new_state == _state:
            return _state
        _state = new_state

    events.emit(events.PLAY_STATE_CHANGED, state=new_state.as_dict())
    return new_state


def set_launching(table_name: str | None) -> LaunchState:
    """Record that a launch is starting, and for which table."""
    return _replace(LaunchState(launching=True, table_name=table_name))


def clear() -> LaunchState:
    """Record that nothing is launching. Safe to call when nothing was."""
    return _replace(LaunchState())
