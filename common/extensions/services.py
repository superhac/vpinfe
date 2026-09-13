"""Something an extension does that core needs to reach, and that is not about a game.

The other direction from `contributions`. That one answers "what does an extension know
about this game"; this one answers "who is signed in", "sync the library now" - questions
with no game in them.

**Core keeps the method; the extension answers it.** A theme has been able to ask who is
playing since long before extensions existed, and published themes still call those
methods, so they cannot move or be removed. What moves is the answer behind them. Core
asks by name and gets None when nothing provides it, which is the case that has to work:
an extension that is disabled, failed to load, or was never installed leaves core
answering exactly what it answered before there was one.

One provider per name. A second is refused rather than allowed to win, because which of
two answers a theme got would depend on load order.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass

logger = logging.getLogger("vpinfe.common.extensions.services")


@dataclass(frozen=True)
class Service:
    extension: str
    name: str
    run: Callable[..., object]


_lock = threading.RLock()
_services: dict[str, Service] = {}


def provide(extension: str, name: str, run: Callable[..., object]) -> None:
    """An extension: answer this from now on."""
    wanted = str(name or "").strip()
    if not wanted:
        raise ValueError("a service needs a name")
    with _lock:
        held = _services.get(wanted)
        if held is not None and held.extension != extension:
            raise ValueError(
                f"{wanted!r} is already answered by {held.extension}")
        _services[wanted] = Service(extension=extension, name=wanted, run=run)
    logger.info("%s answers %s", extension, wanted)


def forget(extension: str) -> None:
    """Everything one extension answered, when it unloads."""
    with _lock:
        for name in [k for k, v in _services.items() if v.extension == extension]:
            _services.pop(name, None)


def forget_all() -> None:
    with _lock:
        _services.clear()


def provided() -> tuple[str, ...]:
    with _lock:
        return tuple(sorted(_services))


def ask(name: str, *args, **kwargs):
    """Core: get the answer, or None if nothing provides it.

    None rather than raising, because "no extension is doing this" is the ordinary state
    and every caller is a surface that has to keep working without one. A provider that
    throws is logged and answers None for the same reason: a broken extension must not
    take a theme method down with it.
    """
    with _lock:
        held = _services.get(str(name or "").strip())
    if held is None:
        return None
    try:
        return held.run(*args, **kwargs)
    except Exception:
        logger.exception("%s failed answering %s", held.extension, held.name)
        return None


def answered_by(name: str) -> str:
    """Which extension answers this, or "" - for the page that shows what is installed."""
    with _lock:
        held = _services.get(str(name or "").strip())
    return held.extension if held is not None else ""
