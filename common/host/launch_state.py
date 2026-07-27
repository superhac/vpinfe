"""What this play host is doing, and who asked for it.

Every change is announced as `play.state_changed`, so a consumer can be told rather
than having to ask.

`source` exists because one consumer - the frontend - needs to tell its own launches
apart from everyone else's, and every other consumer needs the state to be true
regardless of who started it. Reporting only launches the frontend did not start
would make the state a message to one client rather than a fact about the machine.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass

from common import events

# Who asked. The frontend ignores its own; nothing else needs to care.
SOURCE_FRONTEND = "frontend"
SOURCE_REMOTE = "remote"
SOURCE_API = "api"

_lock = threading.Lock()


@dataclass(frozen=True)
class LaunchState:
    launching: bool = False
    table_name: str | None = None
    source: str | None = None

    def as_dict(self) -> dict:
        return {"launching": self.launching, "table_name": self.table_name,
                "source": self.source}


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


def set_launching(table_name: str | None, *, source: str) -> LaunchState:
    """Record that a launch is starting, for which table, and who asked.

    `source` is required rather than defaulted: a caller that does not say is a
    caller the frontend cannot tell apart from itself.
    """
    return _replace(LaunchState(launching=True, table_name=table_name, source=source))


def clear() -> LaunchState:
    """Record that nothing is launching. Safe to call when nothing was."""
    return _replace(LaunchState())
