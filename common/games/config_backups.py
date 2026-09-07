"""Copies of the files an app keeps its settings in.

Only the app knows which file its settings are in; moving a file is core's, which does
it for every kind already. So the app names them and this copies them.

Named, timestamped, and a copy of what is there now taken before a restore - restoring
the wrong one is a mistake somebody makes once, and without that copy it is the last one
they get to make.
"""

from __future__ import annotations

import logging
import re
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from common.paths import CONFIG_DIR

logger = logging.getLogger("vpinfe.common.games.config_backups")

BACKUPS_DIR = CONFIG_DIR / "backups" / "app_config"

# What a person may call one. Anything else would end up in a filename.
_LABEL = re.compile(r"[^A-Za-z0-9._-]+")
# `<stem>--<when>--<reason>[--<label>].<ext>`. Two dashes, because a stem may hold one.
# The reason may be hyphenated - `before-restore` is one - but never doubly, so it
# cannot run past the `--` that starts the label.
_PARTS = re.compile(r"^(?P<stem>.+?)--(?P<when>\d{8}T\d{6}Z)"
                    r"--(?P<reason>[a-z]+(?:-[a-z]+)*)"
                    r"(?:--(?P<label>.*))?$")

BEFORE_RESTORE = "before-restore"
MANUAL = "manual"


@dataclass(frozen=True)
class Backup:
    name: str
    path: str
    taken_at: str
    reason: str
    label: str = ""
    size: int = 0


def _safe(label: str) -> str:
    return _LABEL.sub("-", str(label or "").strip()).strip("-.")[:64]


def _home(launcher_id: str) -> Path:
    """One folder per launcher. Two launchers on one machine each have their own ini,
    and copies of both in one folder would be told apart by a filename alone."""
    return BACKUPS_DIR / (_safe(launcher_id) or "unknown")


def take(launcher_id: str, files: dict[str, str], *, reason: str = MANUAL,
         label: str = "") -> list[Backup]:
    """A copy of every file the app named, or nothing where none of them is there yet."""
    home = _home(launcher_id)
    when = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    taken: list[Backup] = []
    for path in dict.fromkeys(files.values()):
        source = Path(path).expanduser()
        if not source.is_file():
            continue
        parts = [source.stem, when, reason]
        if _safe(label):
            parts.append(_safe(label))
        target = home / f"{'--'.join(parts)}{source.suffix}"
        home.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        taken.append(_described(target))
    return taken


def held(launcher_id: str) -> list[Backup]:
    """Every copy this launcher has, newest first."""
    home = _home(launcher_id)
    if not home.is_dir():
        return []
    found = [_described(path) for path in home.iterdir() if path.is_file()]
    return sorted(found, key=lambda one: one.taken_at, reverse=True)


def restore(launcher_id: str, name: str, files: dict[str, str]) -> Backup | None:
    """Put a copy back, over a copy of what is there now.

    Returns the safety copy it took first, so a caller can say what it did rather than
    only that it did it.
    """
    home = _home(launcher_id)
    source = home / Path(str(name or "")).name
    if not source.is_file() or source.parent != home:
        raise FileNotFoundError(f"No copy called {name!r}.")

    target = _target_for(source, files)
    if target is None:
        raise ValueError("That copy does not match any file this app keeps.")

    safety = take(launcher_id, {"": str(target)}, reason=BEFORE_RESTORE)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    logger.info("Restored %s over %s", source.name, target)
    return safety[0] if safety else None


def _target_for(source: Path, files: dict[str, str]) -> Path | None:
    """Which of the app's files this copy came from, by the stem it was taken under."""
    found = _PARTS.match(source.stem)
    stem = found.group("stem") if found else source.stem
    for path in files.values():
        candidate = Path(path).expanduser()
        if candidate.stem == stem and candidate.suffix == source.suffix:
            return candidate
    return None


def _described(path: Path) -> Backup:
    found = _PARTS.match(path.stem)
    when = found.group("when") if found else ""
    return Backup(
        name=path.name,
        path=str(path),
        taken_at=(f"{when[:4]}-{when[4:6]}-{when[6:8]}T{when[9:11]}:"
                  f"{when[11:13]}:{when[13:15]}Z" if when else ""),
        reason=(found.group("reason") if found else ""),
        label=(found.group("label") or "" if found else ""),
        size=path.stat().st_size if path.is_file() else 0,
    )
