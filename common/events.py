"""The in-process event bus.

A hook is part of an operation and can stop it; a subscriber is only told. Handlers
run on the publishing thread - this is not a work queue. See docs/common.md.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass, field

logger = logging.getLogger("vpinfe.common.events")

# Table lifecycle. `launching` is the one with hooks that matter: everything
# registered against it has finished before the game file is started.
TABLE_LAUNCHING = "table.launching"
TABLE_LAUNCHED = "table.launched"
TABLE_EXITED = "table.exited"

# Play-host state changed - today that is the remote-launch overlay. Carries the
# whole new state, so a consumer that missed one is still correct after the next.
PLAY_STATE_CHANGED = "play.state_changed"

# Slow work. One shape everywhere, whether the work runs in this process or not:
#   job.progress  {job_id, pct, message}
#   job.done      {job_id}
#   job.failed    {job_id, error}
JOB_PROGRESS = "job.progress"
JOB_DONE = "job.done"
JOB_FAILED = "job.failed"

DEFAULT_PRIORITY = 100


@dataclass
class _Registrations:
    hooks: list[tuple[int, int, Callable]] = field(default_factory=list)
    subscribers: list[Callable] = field(default_factory=list)


_lock = threading.RLock()
_events: dict[str, _Registrations] = {}
_sequence = 0


def _slot(name: str) -> _Registrations:
    return _events.setdefault(name, _Registrations())


def hook(name: str, handler: Callable, *, priority: int = DEFAULT_PRIORITY) -> Callable:
    """Register a handler that the operation waits for. Lower priority runs first.

    Raising from a hook stops the operation. Register one only when that is the
    behavior you want.
    """
    global _sequence
    with _lock:
        _sequence += 1
        # The counter keeps equal priorities in registration order rather than
        # letting sort() compare the functions themselves.
        _slot(name).hooks.append((priority, _sequence, handler))
        _slot(name).hooks.sort(key=lambda entry: (entry[0], entry[1]))
    return handler


def subscribe(name: str, handler: Callable) -> Callable:
    """Register a handler that is told what happened and cannot affect it."""
    with _lock:
        _slot(name).subscribers.append(handler)
    return handler


def unsubscribe(name: str, handler: Callable) -> None:
    with _lock:
        slot = _slot(name)
        slot.hooks = [entry for entry in slot.hooks if entry[2] is not handler]
        slot.subscribers = [h for h in slot.subscribers if h is not handler]


def emit(name: str, **payload) -> None:
    """Run the hooks in order, then notify the subscribers.

    Hook failures propagate. Subscriber failures are logged and contained.
    """
    with _lock:
        slot = _slot(name)
        hooks = [entry[2] for entry in slot.hooks]
        subscribers = list(slot.subscribers)

    logger.debug("emit %s hooks=%s subscribers=%s", name, len(hooks), len(subscribers))

    for handler in hooks:
        handler(**payload)

    for handler in subscribers:
        try:
            handler(**payload)
        except Exception:
            logger.exception("Subscriber to %s failed", name)


def clear() -> None:
    """Drop every registration. For tests."""
    with _lock:
        _events.clear()


def registered(name: str) -> tuple[int, int]:
    """(hooks, subscribers) for an event. For tests and diagnostics."""
    with _lock:
        slot = _slot(name)
        return len(slot.hooks), len(slot.subscribers)
