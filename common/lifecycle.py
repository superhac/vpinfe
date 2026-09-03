"""Starting, stopping and restarting things, however the request arrives.

    scope     frontend   app        system     table
    start     yes        -          -          -
    stop      yes        yes        poweroff   yes
    restart   yes        yes        yes        -

Two axes rather than four verbs, so reboot is `restart` at system scope and an instance
started headless can open its windows without being restarted.

**An origin is an address, not a category:** a confirm belongs on the surface that asked,
and a dialog raised anywhere else is a hang on a screen nobody is watching. Confirming and
notifying are separate, and only the first can block.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

logger = logging.getLogger("vpinfe.common.lifecycle")

# What a request applies to.
FRONTEND = "frontend"       # the Chromium windows; VPinFE keeps running
APP = "app"                 # VPinFE itself
SYSTEM = "system"           # the machine
TABLE = "table"             # the table being played; VPinFE and the frontend keep running

# What happens to it.
START = "start"
STOP = "stop"
RESTART = "restart"

# Naming it avoids "stop the system" reading as "stop VPinFE on the system".
POWEROFF = (SYSTEM, STOP)

_ALLOWED = {
    (FRONTEND, START), (FRONTEND, STOP), (FRONTEND, RESTART),
    (APP, STOP), (APP, RESTART),
    (SYSTEM, STOP), (SYSTEM, RESTART),
    # Stop only: starting a table is a launch, which needs to know which one, and
    # restarting one is that launch again.
    (TABLE, STOP),
}

# Where a request came from. Not a category: a confirm has to reach the person who asked.
SURFACE_FRONTEND = "frontend"
SURFACE_MANAGER_UI = "manager_ui"
SURFACE_SIGNAL = "signal"
SURFACE_EXTENSION = "extension"
# An HTTP caller. Never answerable: the request is already over by the time anything
# here could ask, so whoever called put the question to their user before calling.
SURFACE_API = "api"


@dataclass(frozen=True)
class Origin:
    """Who asked, and where to reach them: a window name, or a Manager UI client id."""

    surface: str
    address: str = ""

    @property
    def is_answerable(self) -> bool:
        """Whether there is anybody there to ask. A signal is not."""
        return self.surface in (SURFACE_FRONTEND, SURFACE_MANAGER_UI) and bool(self.address)


@dataclass(frozen=True)
class Request:
    scope: str
    action: str
    origin: Origin
    reason: str = ""

    @property
    def pair(self) -> tuple[str, str]:
        return (self.scope, self.action)

    def describe(self) -> str:
        """What this asks for, in the words a person would use.

        Written out rather than built from the scope and the action: the template read
        "stop the app", which names an internal scope at someone about to be asked
        whether they meant it. Already sentence-cased, because str.capitalize lowercases
        the rest and "Quit VPinFE" would come back as "Quit vpinfe".
        """
        return _DESCRIPTIONS.get(self.pair, f"{self.action} the {self.scope}")


# Every allowed pair, in the words the confirm card and the log both use.
_DESCRIPTIONS = {
    (FRONTEND, START): "Open the frontend windows",
    (FRONTEND, STOP): "Close the frontend windows",
    (FRONTEND, RESTART): "Reopen the frontend windows",
    (APP, STOP): "Quit VPinFE",
    (APP, RESTART): "Restart VPinFE",
    (SYSTEM, STOP): "Power off this machine",
    (SYSTEM, RESTART): "Reboot this machine",
    (TABLE, STOP): "Close the table that is running",
}


@dataclass
class _Registry:
    confirmers: dict = field(default_factory=dict)
    performers: dict = field(default_factory=dict)
    notifiers: list = field(default_factory=list)


_registry = _Registry()


def register_confirmer(surface: str, confirmer) -> None:
    """How to ask a person on `surface`. Returns True to proceed."""
    _registry.confirmers[surface] = confirmer


def register_performer(scope: str, action: str, performer) -> None:
    """What actually does it. One per scope/action, registered by the layer that owns it."""
    if (scope, action) not in _ALLOWED:
        raise ValueError(f"not a lifecycle action: {action} the {scope}")
    _registry.performers[(scope, action)] = performer


def register_notifier(notifier) -> None:
    """Told about a request that is going ahead. Nothing waits on this and nothing may
    veto through it - it is how a surface that did not ask says what is about to happen."""
    # Registering the same one twice would announce twice; a performer cannot make that
    # mistake because it is keyed.
    if notifier not in _registry.notifiers:
        _registry.notifiers.append(notifier)


def reset_for_tests() -> None:
    _registry.confirmers.clear()
    _registry.performers.clear()
    _registry.notifiers.clear()


def needs_confirmation(request: Request, confirm_scopes) -> bool:
    """Whether the user asked to be checked on this. By scope, because "ask before
    anything touches the system" is what people mean and a key per pair is a grid
    nobody fills in."""
    wanted = {str(s).strip().lower() for s in (confirm_scopes or []) if str(s).strip()}
    return request.scope in wanted


def confirm(request: Request, confirm_scopes) -> bool:
    """Ask, if this wants asking and there is somebody to ask.

    An unanswerable origin proceeds: a SIGTERM that waits on a dialog is a process that
    will not die. A surface that should answer and cannot denies instead - the window
    went away, so the person is not there either.
    """
    if not needs_confirmation(request, confirm_scopes):
        return True
    if not request.origin.is_answerable:
        logger.info("No surface to confirm with (%s); proceeding with %s",
                    request.origin.surface, request.describe())
        return True

    confirmer = _registry.confirmers.get(request.origin.surface)
    if confirmer is None:
        logger.warning("Nothing can confirm on %s; proceeding with %s",
                       request.origin.surface, request.describe())
        return True
    try:
        return bool(confirmer(request))
    except Exception:
        # A confirmer that breaks must not take the action with it, in either direction.
        logger.exception("Confirming %s failed; not proceeding", request.describe())
        return False


def announce(request: Request) -> None:
    """Tell every other surface what is about to happen. Never blocks the action."""
    for notifier in list(_registry.notifiers):
        try:
            notifier(request)
        except Exception:
            logger.exception("A lifecycle notifier failed; continuing")


def request(scope: str, action: str, *, origin: Origin, confirm_scopes=(),
            reason: str = "") -> bool:
    """Confirm, announce, then do it. Returns whether it went ahead."""
    if (scope, action) not in _ALLOWED:
        raise ValueError(f"not a lifecycle action: {action} the {scope}")

    pending = Request(scope, action, origin, reason)
    if not confirm(pending, confirm_scopes):
        logger.info("%s was declined at %s", pending.describe(), origin.surface)
        return False

    performer = _registry.performers.get(pending.pair)
    if performer is None:
        logger.error("Nothing performs %s on this build", pending.describe())
        return False

    logger.info("%s, asked for by %s", pending.describe(), origin.surface)
    announce(pending)
    performer(pending)
    return True
