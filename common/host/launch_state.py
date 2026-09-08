"""What this play host is doing, and who asked for it.

Every change is announced as `play.state_changed`, so a consumer can be told rather
than having to ask.

`source` is who asked. The frontend needs to tell its own launches apart; everyone else
needs the state to be true regardless of who started it.
"""

from __future__ import annotations

import logging
import subprocess
import threading
from dataclasses import dataclass

from common import events

logger = logging.getLogger("vpinfe.common.host.launch_state")

# Who asked. The frontend ignores its own; nothing else needs to care.
SOURCE_FRONTEND = "frontend"
SOURCE_REMOTE = "remote"
SOURCE_API = "api"

_lock = threading.Lock()


@dataclass(frozen=True)
class LaunchState:
    launching: bool = False
    game_name: str | None = None
    source: str | None = None

    def as_dict(self) -> dict:
        return {"launching": self.launching, "game_name": self.game_name,
                "source": self.source}


_state = LaunchState()

# The running table's process, so something other than the thread that launched it can
# end it. Deliberately not a field on LaunchState: that is serialized into every
# `play.state_changed` payload, and a Popen is not something to put on the wire.
_process: subprocess.Popen | None = None


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


def set_launching(game_name: str | None, *, source: str) -> LaunchState:
    """Record that a launch is starting, for which game, and who asked.

    `source` is required rather than defaulted: a caller that does not say is a
    caller the frontend cannot tell apart from itself.
    """
    return _replace(LaunchState(launching=True, game_name=game_name, source=source))


def clear() -> LaunchState:
    """Record that nothing is launching. Safe to call when nothing was."""
    global _process
    with _lock:
        _process = None
    return _replace(LaunchState())


def attach(process: subprocess.Popen) -> None:
    """Hold the launched table's process. Released by `clear()`."""
    global _process
    with _lock:
        _process = process


def stop(timeout: float = 5.0) -> bool:
    """Close the running table. Returns whether there was one to close.

    Terminate then kill, as `dof_service.close` does, so VPX has `timeout` to write its
    NVRAM before it is taken. The launching thread is blocked in `process.wait()` and
    unblocks on its own, so the state is cleared, `table.exited` is announced and the
    play session is recorded by the same `finally` an ordinary quit runs - closing a
    table from here and closing it from the cabinet take one path.
    """
    with _lock:
        process = _process
    # The wait below must not hold the lock: the launching thread takes it in `clear()`
    # the moment the process dies, and holding it here would deadlock against that.
    if process is None or process.poll() is not None:
        return False

    logger.info("Closing the running table")
    process.terminate()
    try:
        process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        logger.warning("The table did not close in %ss; killing it", timeout)
        process.kill()
        try:
            process.wait(timeout=2.0)
        except subprocess.TimeoutExpired:
            logger.error("The table's process survived a kill")
    return True
