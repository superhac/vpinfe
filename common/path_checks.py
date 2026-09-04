"""Whether a setting that names something on disk actually finds it.

A path in the config is the one kind of setting that can be perfectly well-formed and
still wrong, and it fails much later - at launch, as a file-not-found, on the machine
nobody is sitting at. Asking the question when it is typed is the whole point.

Answered on the machine the setting belongs to. One install cannot stat another's disk, so
this is never asked about somebody else's path - a caller names a setting and the
install holding it answers.
"""

from __future__ import annotations

import os
from pathlib import Path

from common import config_schema
from common.launcher_path import resolve_launcher_path

# What the answer can be. `unset` is not a failure: most of these are optional, and a
# blank one means "use the default", which is a choice rather than a mistake.
UNSET = "unset"
OK = "ok"
MISSING = "missing"
WRONG_KIND = "wrong_kind"
NOT_EXECUTABLE = "not_executable"

_WANTED = {
    "file": "a file",
    "dir": "a folder",
    "exe": "a program",
}


def check(kind: str, raw: str) -> tuple[str, str]:
    """One path against what its setting says it should be: (state, reason).

    The reason is written for the person who typed it, so it says what was found rather
    than what was expected - "that is a folder" is the useful half when the field wanted
    a file, because the path is right there to compare against.
    """
    value = str(raw or "").strip()
    if not value:
        return UNSET, ""
    if kind not in config_schema.PATH_KINDS:
        return UNSET, ""

    here = Path(value).expanduser()
    if kind == "exe":
        # What a person picks on macOS is an .app, which is a directory. The launcher
        # walks into the bundle, so this asks about the same file it would run.
        here = resolve_launcher_path(value)

    if not here.exists():
        return MISSING, "Nothing is at that path."

    if kind == "dir":
        if not here.is_dir():
            return WRONG_KIND, "That is a file, and this wants a folder."
        return OK, ""

    if here.is_dir():
        return WRONG_KIND, f"That is a folder, and this wants {_WANTED[kind]}."

    if kind == "exe" and not os.access(here, os.X_OK):
        # Its own state rather than "missing": the path is right and the file is there,
        # which is a permissions problem and not a typo, and they are fixed differently.
        return NOT_EXECUTABLE, "That file is not executable."

    return OK, ""


def check_option(option, value) -> tuple[str, str]:
    """The same, for a schema option that may not be a path at all."""
    return check(getattr(option, "path", ""), value)


def path_options() -> tuple:
    """Every setting that names something on disk, in schema order."""
    return tuple(option for option in config_schema.CONFIG_OPTIONS
                 if option.path and not option.internal)
