"""The applications that play a table, and which files each one claims.

Visual Pinball is the only one today, and writing it down is what makes the next one
an entry in a tuple rather than a search for every place ".vpx" was assumed.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class App:
    """One launcher, and the files it claims. `settings_key` says where its binary is
    configured; suffixes are lowercase and include the dot."""

    id: str
    name: str
    suffixes: tuple[str, ...]
    settings_key: str = ""


APPS: tuple[App, ...] = (
    App("vpx", "Visual Pinball X", (".vpx",), "vpx_bin_path"),
)

DEFAULT_APP = APPS[0]


def app_for(filename: str) -> App | None:
    """Which app claims this file, or None for something that is not a table."""
    lowered = str(filename or "").lower()
    return next((app for app in APPS
                 if any(lowered.endswith(suffix) for suffix in app.suffixes)), None)


def table_suffixes() -> tuple[str, ...]:
    """Every extension that makes a file a table, for a folder listing to filter on."""
    return tuple(suffix for app in APPS for suffix in app.suffixes)


def strip_suffix(filename: str) -> str:
    """The name without the extension its app claims it by. Not Path.stem: "Foo (Bar
    1.2).vpx" keeps everything up to the extension we know, and only that."""
    app = app_for(filename)
    if app is None:
        return str(filename or "")
    lowered = str(filename).lower()
    suffix = next(s for s in app.suffixes if lowered.endswith(s))
    return str(filename)[: -len(suffix)]
