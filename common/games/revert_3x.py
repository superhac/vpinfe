"""Take 3.0's own state off an install so the next start migrates from scratch.

A test instrument rather than a recovery aid: a one-time migration whose marker is
already set does nothing and says nothing, so a 2->3 test that has run once stops
testing.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import urllib.request
from pathlib import Path

from common.games.collection_store import COLLECTIONS_NAME, COLLECTIONS_NAME_INI
from common.games.info_file import ASSETS_KEY, VPINFE_SECTION
from common.games.info_maintenance import game_dirs, restore_library
from common.games.info_migration import (
    backup_names,
    copy_aside,
    needs_migration,
    restorable_backup,
)
from common.games.tables import TABLES_KEY
from common.jobs import JobReporter

logger = logging.getLogger("vpinfe.common.games.revert_3x")

# 3.0 wrote these and 2.x reads none of them. Named one at a time on purpose: a sweep
# for anything backup-shaped also eats the hand-made .bak-repro files kept beside them.
# `watching.json` is 3.0 data with no 2.x original: a reset library that kept it would
# measure new findings against an install that no longer exists.
CONFIG_FILES = ("vpinfe.json", COLLECTIONS_NAME, "devices.json", "manager-ui-state.json",
                "watching.json")
CONFIG_DIRS = ("theme_user_options",)

# Whose `.vpinfe-*` copies are ours to remove. The ini pair is what the conversion to
# JSON set aside; the JSON pair is what a restore keeps before it replaces one.
BACKED_UP_NAMES = ("vpinfe.ini", "vpinfe.json", COLLECTIONS_NAME_INI, COLLECTIONS_NAME)

# Copied aside before removal, and deliberately absent from BACKED_UP_NAMES so the copy
# outlives the reset. Everything else here is regenerable or has a 2.x original to fall
# back on; the device registry has neither once it holds a device that cannot announce
# itself. A phone is entered by hand, nothing re-announces it, and the [mobile] import
# that could have rebuilt one is marker-guarded and has already run.
KEPT_BEFORE_REMOVAL = ("devices.json",)

# What an atomic write leaves behind if it was killed between mkstemp and os.replace.
WRITE_TEMP_PREFIX = ".vpinfe_write_"
WRITE_TEMP_SUFFIX = ".tmp"

# Which of the two baselines the reset produced, reported rather than left to infer.
RESTORED_FROM_2X = "restored_from_2x"
FRESH_INSTALL = "fresh_install"

# Only the unversioned backups are 2.x originals. The default would happily pick a
# schema 2 copy that an earlier --restore-info left in the folder.
MAX_2X_SCHEMA = 0

# The `.info` sections 3.0 introduced. 2.x wrote `VPinFE`, `VPXFile` and `Medias`, all
# three of which the migration renames or supersedes, so any of these in a file 2.x has
# not since written over is proof 3.0 made it.
OUR_SECTIONS = (VPINFE_SECTION, TABLES_KEY, ASSETS_KEY)


class InstanceRunningError(RuntimeError):
    """VPinFE is up, so the reset would be undone before anyone saw it."""


def running_instance(hub_port: int, timeout: float = 1.0) -> bool:
    """Whether a VPinFE is serving on this install's hub port.

    Reads the discovery document rather than only opening the socket, so an unrelated
    program on that port cannot block a reset. A listening socket dies with the process
    that holds it, so there is no stale port to be fooled by.
    """
    try:
        with urllib.request.urlopen(
                f"http://127.0.0.1:{int(hub_port)}/api/v1/", timeout=timeout) as handle:
            document = json.load(handle)
    except (OSError, ValueError):
        return False
    return isinstance(document, dict) and document.get("name") == "VPinFE"


def reset(game_root, config_dir, *, hub_port: int, config_only: bool = False,
          dry_run: bool = False, progress_cb=None, log_cb=None) -> dict:
    """Remove 3.0's state. Raises InstanceRunningError when VPinFE is running.

    A live instance holds the settings and the collections in memory and writes them
    back complete with their markers, so the refusal is not caution. A dry run is
    allowed either way: it writes nothing.
    """
    config_dir = Path(config_dir)
    reporter = JobReporter(logger, progress_cb=progress_cb, log_cb=log_cb)

    live = running_instance(hub_port)
    if live and not dry_run:
        raise InstanceRunningError(
            f"VPinFE is answering on port {hub_port}. Stop it and run this again - a "
            "reset under a running instance is written straight back over.")

    result = {
        "dry_run": dry_run, "config_only": config_only, "instance_running": live,
        "config_removed": [], "config_kept": [], "restored": 0, "deleted_info": [],
        "removed_backups": 0,
        "failed": 0, "failures": [],
        # Never deleted, so this answer is the same before and after.
        "end_state": (RESTORED_FROM_2X if (config_dir / "vpinfe.ini").exists()
                      else FRESH_INSTALL),
    }
    if live:
        reporter.log(f"VPinFE is answering on port {hub_port}, so a real run would refuse.")

    if not config_only:
        _reset_library(game_root, result, reporter, dry_run)
    _reset_config(config_dir, result, dry_run)

    for line in _summary(result):
        reporter.log(line)
    return result


def _reset_library(game_root, result: dict, reporter: JobReporter, dry_run: bool) -> None:
    restorable, ours = _library_plan(game_root)
    result["deleted_info"] = sorted(game_dir.name for game_dir in ours)

    if dry_run:
        result["restored"] = len(restorable)
        return

    outcome = restore_library(game_root, max_schema=MAX_2X_SCHEMA,
                              progress_cb=reporter.progress_cb)
    result["restored"] = outcome["restored"]
    result["failed"] += outcome["failed"]
    result["failures"] += outcome["failures"]

    for game_dir in ours:
        _remove(game_dir / f"{game_dir.name}.info", result)
    # After the restore, not before: the unversioned copy is what it reads, and
    # replace_atomic copies rather than moves, so its source is still here afterwards.
    for game_dir in game_dirs(game_root):
        result["removed_backups"] += _sweep(game_dir, f"{game_dir.name}.info", result)


def _reset_config(config_dir: Path, result: dict, dry_run: bool) -> None:
    targets = _config_targets(config_dir)
    if dry_run:
        result["config_removed"] = sorted(path.name for path in targets)
        result["config_kept"] = sorted(name for name in KEPT_BEFORE_REMOVAL
                                       if (config_dir / name).exists())
        return
    result["config_kept"] = _keep_aside(config_dir, result)
    result["config_removed"] = sorted(path.name for path in targets
                                      if _remove(path, result))


def _keep_aside(config_dir: Path, result: dict) -> list[str]:
    """Copy what cannot be rebuilt, before the removal that follows. Returns the copies.

    A failure here is reported and does not stop the reset: the copy is a courtesy, and
    refusing to reset because one could not be made would strand the user in the state
    they are trying to leave.
    """
    kept = []
    for name in KEPT_BEFORE_REMOVAL:
        source = config_dir / name
        if not source.exists():
            continue
        try:
            kept.append(Path(copy_aside(source)).name)
        except OSError as exc:
            result["failed"] += 1
            result["failures"].append((name, str(exc)))
    return sorted(kept)


def _library_plan(game_root) -> tuple[list[Path], list[Path]]:
    """Which folders get their 2.x `.info` back, and which lose the one 3.0 made.

    A folder with no unversioned backup and a 2.x-shaped `.info` is left alone: nothing
    of 3.0's has been written into it, so there is nothing here to take out.
    """
    restorable, ours = [], []
    for game_dir in game_dirs(game_root):
        info_path = game_dir / f"{game_dir.name}.info"
        if not info_path.exists():
            continue
        if restorable_backup(game_dir, MAX_2X_SCHEMA):
            restorable.append(game_dir)
        elif _written_by_3x(info_path):
            ours.append(game_dir)
    return restorable, ours


def _written_by_3x(info_path: Path) -> bool:
    """Whether 3.0 wrote this `.info`, by a section only 3.0 writes.

    Not the schema stamp: the id backfill writes `{"vpinfe": {"game_id": ...}}` into a
    folder that had no `.info` at all, and that file carries no stamp. Unreadable
    answers no - this removes what it can identify, and a file too broken to parse is
    the one thing here nobody can re-enter.
    """
    try:
        with info_path.open(encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        logger.warning("Could not read %s; leaving it alone", info_path)
        return False
    if not isinstance(data, dict) or needs_migration(data):
        return False        # 2.x has written this since, so its own shape is in there
    return any(name in data for name in OUR_SECTIONS)


def _config_targets(config_dir: Path) -> list[Path]:
    """Everything under the config directory this removes, by name."""
    try:
        names = os.listdir(config_dir)
    except OSError:
        return []
    targets = [config_dir / name for name in CONFIG_FILES + CONFIG_DIRS
               if (config_dir / name).exists()]
    for owned in BACKED_UP_NAMES:
        targets += [config_dir / name for name in backup_names(names, owned)]
    return targets + [config_dir / name for name in names if _is_write_temp(name)]


def _is_write_temp(name: str) -> bool:
    return name.startswith(WRITE_TEMP_PREFIX) and name.endswith(WRITE_TEMP_SUFFIX)


def _sweep(folder: Path, owned: str, result: dict) -> int:
    """Every copy of `owned` this build made, plus any half-written temp file."""
    try:
        names = os.listdir(folder)
    except OSError:
        return 0
    doomed = backup_names(names, owned) + [name for name in names if _is_write_temp(name)]
    return sum(_remove(folder / name, result) for name in doomed)


def _remove(path: Path, result: dict) -> int:
    """Delete a file or a whole directory. Returns 1 when it went, 0 when it could not."""
    try:
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()
    except OSError as exc:
        result["failed"] += 1
        result["failures"].append((path.name, str(exc)))
        return 0
    return 1


def _summary(result: dict) -> list[str]:
    """What went, or would go. The same shape either way, so a dry run reads as the plan
    for the run that follows it."""
    dry = result["dry_run"]
    lines = [f"{'Would remove' if dry else 'Removed'} "
             f"{len(result['config_removed'])} item(s) from the config directory: "
             f"{', '.join(result['config_removed']) or 'nothing'}"]
    if result["config_kept"]:
        # Named, because a copy nobody is told about is one nobody restores from.
        lines.append(
            f"{'Would keep' if dry else 'Kept'} a copy of what cannot be rebuilt: "
            f"{', '.join(result['config_kept'])}")
    if not result["config_only"]:
        lines.append(
            f"{'Would restore' if dry else 'Restored'} {result['restored']} .info "
            f"file(s) from their 2.x backups, leaving no VPinFE backup copy anywhere "
            "in the library")
        if result["deleted_info"]:
            # The one thing here nobody can re-enter: a rating, a favorite and a play
            # count accumulated under 3.0. Named rather than counted, before and after.
            lines.append(
                f"{'Would delete' if dry else 'Deleted'} the .info 3.0 made for "
                f"{len(result['deleted_info'])} game(s) with no 2.x backup: "
                f"{', '.join(result['deleted_info'])}")
    lines.append(
        "This install keeps its vpinfe.ini, so the next start reads its 2.x settings."
        if result["end_state"] == RESTORED_FROM_2X else
        "This install has no vpinfe.ini, so the next start is a first run.")
    if result["failed"]:
        lines.append(f"{result['failed']} item(s) could not be removed and were left "
                     "as they are.")
    return lines
