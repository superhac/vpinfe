"""Whether a launch has been requested from somewhere other than the frontend.

The Remote Control page sets this so the frontend can put an overlay up before
VPX takes the screen. The frontend polls it today; it becomes an event on the bus,
and the poll goes away.

Play-host state: it describes what is happening on this machine.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass

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


def set_launching(table_name: str | None) -> LaunchState:
    """Record that a launch is starting, and for which table."""
    global _state
    with _lock:
        _state = LaunchState(launching=True, table_name=table_name)
        return _state


def clear() -> LaunchState:
    """Record that nothing is launching. Safe to call when nothing was."""
    global _state
    with _lock:
        _state = LaunchState()
        return _state
