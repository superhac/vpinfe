"""The registry: which apps this install has.

The built-in source is code that ships with the program, so it cannot fail to be there -
`generic` has to exist for an install whose everything else is broken to still be
configurable. A loaded source arrives later and only ever adds, which is why everything
reads through `all_apps()` rather than a constant frozen at import time.

Two `apps` packages: this one is core's registry, the top-level `apps/` holds the
implementations.
"""

from __future__ import annotations

from .contract import App, Availability, Claim, Entry, Field, Kinds, Parsed, Session

__all__ = [
    "App", "Availability", "Claim", "Entry", "Field", "Kinds", "Parsed", "Session",
    "all_apps", "app_for", "app_name", "default_app", "get", "strip_suffix",
    "table_suffixes",
]

_built_in_apps: tuple[App, ...] = ()


def _built_in() -> tuple[App, ...]:
    """Imported here rather than at the top of the file: importing `common.apps.contract`
    initializes this package, so an app imported first would find it half-built."""
    global _built_in_apps
    if not _built_in_apps:
        from apps.generic import GENERIC
        from apps.vpx import VPX

        _built_in_apps = (VPX, GENERIC)
    return _built_in_apps


_contributed: dict[str, App] = {}


def contribute(app: App) -> None:
    """Add an app an extension provides.

    Kept apart from the built-ins and always offered after them, so a contributed app
    cannot take a suffix out from under Visual Pinball by loading first. An id already in
    use is refused rather than allowed to win: ids are stored in a table's record, and
    two apps answering to one id makes what is stored ambiguous.
    """
    if any(one.id == app.id for one in _built_in()):
        raise ValueError(f"{app.id!r} is an app this build ships")
    if app.id in _contributed:
        raise ValueError(f"{app.id!r} is already provided by something else")
    _contributed[app.id] = app


def withdraw(app_id: str) -> None:
    """Take one back, when its extension is disabled or reloaded."""
    _contributed.pop(str(app_id or ""), None)


def withdraw_all() -> None:
    _contributed.clear()


def contributed() -> tuple[App, ...]:
    return tuple(_contributed.values())


def all_apps() -> tuple[App, ...]:
    """Every app this install has, in the order they are offered.

    Built-ins first. `app_for` takes the first that claims a file, so the order is what
    decides a contest, and this build's own answer wins one.
    """
    return (*_built_in(), *_contributed.values())


def default_app() -> App:
    """What a file nothing else claims is assumed to be."""
    return _built_in()[0]


def get(app_id: str | None) -> App | None:
    """The app with this id, or None. Ids are stored, so an unknown one is a real state
    rather than a programming error."""
    wanted = str(app_id or "").strip()
    return next((app for app in all_apps() if app.id == wanted), None)


def app_for(filename: str) -> App | None:
    """Which app claims this file, or None for something no app plays."""
    return next((app for app in all_apps() if app.claim.claims(filename)), None)


def app_name(app_id: str | None) -> str:
    """What to call an app on screen. Ids are for the wire. An id nothing claims comes
    back as it came, because inventing a name for it would be worse."""
    wanted = str(app_id or "").strip()
    if not wanted:
        return "-"
    found = get(wanted)
    return found.name if found is not None else wanted


def table_suffixes() -> tuple[str, ...]:
    """Every extension that makes a file a table, for a folder listing to filter on."""
    return tuple(suffix for app in all_apps() for suffix in app.claim.suffixes)


def strip_suffix(filename: str) -> str:
    """The name without the extension its app claims it by."""
    app = app_for(filename)
    return app.claim.strip_suffix(filename) if app is not None else str(filename or "")
