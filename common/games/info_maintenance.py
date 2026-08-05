"""Upgrade a library of `.info` files, or put back what a newer build upgraded.

Neither walk stops on a bad file, and neither re-reads a `.vpx`. See
INFO-SCHEMA.local.md §5b/§5c.
"""

from __future__ import annotations

import logging
from pathlib import Path

from common.games.collection_store import (
    COLLECTIONS_NAME,
    restorable_collections_backup,
)
from common.games.info_migration import (
    CURRENT_SCHEMA,
    copy_aside,
    replace_atomic,
    restorable_backup,
)
from common.games.meta_config import InvalidMetaConfigError, MetaConfig
from common.jobs import JobReporter

logger = logging.getLogger("vpinfe.common.games.info_maintenance")


def game_dirs(game_root, game_name: str | None = None) -> list[Path]:
    """Game folders under the root. Not loadGames: that raises on the first bad `.info`."""
    root = Path(game_root)
    if not root.is_dir():
        return []
    if game_name:
        one = root / game_name
        return [one] if one.is_dir() else []
    return sorted(
        (d for d in root.iterdir() if d.is_dir() and not d.name.startswith(".")),
        key=lambda d: d.name.lower(),
    )


def _info_path(game_dir: Path) -> Path:
    return game_dir / f"{game_dir.name}.info"


def pending_upgrade(game_dir) -> bool:
    """Whether this folder's `.info` still holds the 2.x shape. False if it cannot be read."""
    game_dir = Path(game_dir)
    if not _info_path(game_dir).exists():
        return False
    try:
        return MetaConfig(str(_info_path(game_dir))).pending_migration
    except (InvalidMetaConfigError, OSError):
        return False


def upgrade_library(
    game_root,
    game_name: str | None = None,
    progress_cb=None,
    log_cb=None,
) -> dict:
    """Upgrade every table's `.info` in one pass.

    Startup already does the library, so this is the repair for what it did not reach.
    """
    reporter = JobReporter(logger, progress_cb=progress_cb, log_cb=log_cb)
    log = reporter.log

    folders = game_dirs(game_root, game_name)
    total = len(folders)
    result = {"upgraded": 0, "already_current": 0, "failed": 0, "failures": []}

    log("Upgrading .info files. Each one is backed up first, so this can be undone.")
    reporter.progress(0, total, "Starting")

    for index, game_dir in enumerate(folders, start=1):
        reporter.progress(index, total, game_dir.name)
        info_path = _info_path(game_dir)
        if not info_path.exists():
            result["already_current"] += 1
            continue
        try:
            meta = MetaConfig(str(info_path))
            if not meta.pending_migration:
                result["already_current"] += 1
                continue
            meta.writeConfig()
        except (InvalidMetaConfigError, OSError) as exc:
            result["failed"] += 1
            result["failures"].append((game_dir.name, str(exc)))
            log(f"Left alone, could not be read: {game_dir.name}")
            continue
        result["upgraded"] += 1
        log(f"Upgraded: {game_dir.name}")

    log(_upgrade_summary(result))
    return result


def restore_library(
    game_root,
    game_name: str | None = None,
    max_schema: int = CURRENT_SCHEMA,
    config_dir=None,
    progress_cb=None,
    log_cb=None,
) -> dict:
    """Put back the newest readable backup in every folder that has one.

    All or nothing: nobody chose which games upgraded, so nobody can choose which return.
    """
    reporter = JobReporter(logger, progress_cb=progress_cb, log_cb=log_cb)
    log = reporter.log

    folders = game_dirs(game_root, game_name)
    total = len(folders)
    result = {"restored": 0, "nothing_to_restore": 0, "failed": 0, "failures": [],
              "collections_restored": False}

    log("Restoring backups. Your current .info files are backed up first, so this can be "
        "undone too.")
    reporter.progress(0, total, "Starting")

    for index, game_dir in enumerate(folders, start=1):
        reporter.progress(index, total, game_dir.name)
        chosen = restorable_backup(game_dir, max_schema)
        if not chosen:
            result["nothing_to_restore"] += 1
            continue
        info_path = _info_path(game_dir)
        try:
            _restore_file(info_path, chosen)
        except OSError as exc:
            result["failed"] += 1
            result["failures"].append((game_dir.name, str(exc)))
            log(f"Left as it is, could not be restored: {game_dir.name}")
            continue
        result["restored"] += 1
        log(f"Restored: {game_dir.name}")

    # Collections live in the config directory rather than a game folder, and the id
    # migration rewrites them into something an older build cannot resolve.
    if config_dir:
        chosen = restorable_collections_backup(config_dir, max_schema)
        if chosen:
            try:
                _restore_file(Path(config_dir) / COLLECTIONS_NAME, chosen)
                result["collections_restored"] = True
                log("Restored your collections.")
            except OSError as exc:
                result["failed"] += 1
                result["failures"].append((COLLECTIONS_NAME, str(exc)))
                log("Left as it is, could not be restored: your collections")

    log(_restore_summary(result))
    return result


def _restore_file(path, backup) -> None:
    """Put `backup` in place at `path`, keeping what is there now."""
    if Path(path).exists():
        copy_aside(str(path))
    replace_atomic(backup, path)


def _games(count: int) -> str:
    return f"{count} table" if count == 1 else f"{count} tables"


def _files(count: int) -> str:
    return "1 .info file" if count == 1 else f"{count} .info files"


def _upgrade_summary(result: dict) -> str:
    if not result["upgraded"]:
        return "Nothing to upgrade - every .info file is already on the current format."
    summary = (
        f"Upgraded {_files(result['upgraded'])}. Ratings, favorites, tags and play "
        "counts came across unchanged, and a backup of each was saved."
    )
    if result["failed"]:
        summary += (
            f" {_games(result['failed'])} could not be read and were left exactly as "
            "they were."
        )
    return summary


def _restore_summary(result: dict) -> str:
    if not result["restored"] and not result["collections_restored"]:
        return "Nothing to restore - there are no backups."
    if not result["restored"]:
        return "Restored your collections."
    summary = (
        f"Restored {_files(result['restored'])}. Their ratings, favorites, tags and play "
        "counts are back as this version recorded them."
    )
    if result["collections_restored"]:
        summary += " Your collections are back too."
    if result["nothing_to_restore"]:
        summary += (
            f" {_games(result['nothing_to_restore'])} were never upgraded, so there was "
            "nothing to put back."
        )
    if result["failed"]:
        summary += (
            f" {_games(result['failed'])} could not be restored and were left as they are."
        )
    return summary
