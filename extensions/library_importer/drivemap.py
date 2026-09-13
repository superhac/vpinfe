"""Finding where a foreign library's recorded paths actually are.

A source records the paths of the machine it ran on. `C:\\vPinball\\visualpinball\\Tables`
is a real answer on a Windows cabinet and means nothing on the machine reading the share,
so every table looks absent and an import brings across artwork and no games.

The share is usually mounted somewhere that contains those paths, though - somebody
mounts the drive, or the folder above the library. So rather than asking where each one
went, this looks: from the folder the source was found in, walk up, and try the recorded
path's trailing segments against each ancestor. A hit that exists on disk is the answer;
no hit is reported as one, because a guess here silently imports the wrong files.

Bounded on purpose. Ancestors are walked to a small depth and the search stops at the
first directory that exists, so this costs a handful of stat calls and never a scan.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path, PureWindowsPath

logger = logging.getLogger(__name__)

# How far above the source to look. A share is mounted at the library, the folder above
# it, or the drive; past that we would be searching somebody's whole filesystem for a
# folder name that happens to match.
ANCESTORS = 3

_DRIVE = re.compile(r"^[A-Za-z]:[\\/]")


def looks_foreign(recorded: str) -> bool:
    """Whether this path was written somewhere other than here.

    A drive letter or a backslash means Windows wrote it. Said explicitly rather than
    inferred from "it does not exist", because a path that is simply missing is a
    different problem with a different answer.
    """
    wanted = str(recorded or "").strip()
    return bool(_DRIVE.match(wanted)) or "\\" in wanted


def segments(recorded: str) -> list[str]:
    """The recorded path's parts, with the drive dropped."""
    parts = [one for one in PureWindowsPath(str(recorded or "").strip()).parts
             if one and not _DRIVE.match(one) and one not in ("\\", "/")]
    return parts


@dataclass(frozen=True)
class Found:
    """Where a recorded path is, and the prefix pair that says how it was worked out."""

    path: str = ""
    recorded_prefix: str = ""
    local_prefix: str = ""

    def __bool__(self) -> bool:
        return bool(self.path)


def _child(base: Path, name: str) -> Path | None:
    """The entry called `name` under `base`, whatever case it is really in.

    A source records the case its own filesystem accepted, which is not necessarily the
    case on disk - `visualpinball` here is `VisualPinball`. On a case-insensitive mount
    the difference is invisible until the day the library is on one that is not, so the
    real name is what gets used.
    """
    folded = name.lower()
    try:
        entries = [one for one in base.iterdir() if one.is_dir()]
    except OSError:
        entries = []
    exact = next((one for one in entries if one.name == name), None)
    if exact is not None:
        return exact
    # Asked of the listing rather than answered by `is_dir()`. A case-insensitive mount
    # says yes to the recorded spelling, so trusting it stores a name that is not the
    # one on disk - fine here, wrong the day the library moves to a filesystem that
    # cares.
    return next((one for one in entries if one.name.lower() == folded), None)


def _walk(base: Path, parts: list[str]) -> Path | None:
    for part in parts:
        found = _child(base, part)
        if found is None:
            return None
        base = found
    return base


def resolve(recorded: str, source_root: Path | str) -> Found:
    """Where a recorded path is on this machine, or nothing.

    Longest suffix first: `vPinball/visualpinball/Tables` under a mount that holds
    `vPinball` beats a bare `Tables` under one that happens to hold a folder by that
    name, and the more of the recorded path that matches the likelier it is the same
    place.
    """
    wanted = str(recorded or "").strip()
    if not wanted:
        return Found()

    here = Path(source_root)
    if not looks_foreign(wanted):
        return Found(path=wanted) if Path(wanted).is_dir() else Found()

    parts = segments(wanted)
    if not parts:
        return Found()

    ancestors = [here, *list(here.parents)[:ANCESTORS]]
    for depth in range(len(parts), 0, -1):
        tail = parts[-depth:]
        for base in ancestors:
            found = _walk(base, tail)
            if found is not None:
                # The pair comes from the match rather than being worked out again
                # afterwards: two derivations of one fact is how they disagree.
                head = parts[:len(parts) - depth]
                recorded_prefix = str(PureWindowsPath(
                    PureWindowsPath(wanted).drive + "\\", *head)) if head or \
                    PureWindowsPath(wanted).drive else ""
                logger.debug("Mapped %s to %s", wanted, found)
                return Found(path=str(found), recorded_prefix=recorded_prefix,
                             local_prefix=str(base))
    return Found()
