"""Upgrade a library of `.info` files, or put back what a newer build upgraded.

Neither walk stops on a bad file, and neither re-reads a `.vpx`. See
INFO-SCHEMA.local.md §5b/§5c.
"""

from __future__ import annotations

import logging
from pathlib import Path

from common.jobs import JobReporter
from common.tables.info_migration import (
    CURRENT_SCHEMA,
    copy_aside,
    replace_atomic,
    restorable_backup,
)
from common.tables.metaconfig import InvalidMetaConfigError, MetaConfig

logger = logging.getLogger("vpinfe.common.tables.info_maintenance")


def table_dirs(table_root, table_name: str | None = None) -> list[Path]:
    """Table folders under the root. Not loadTables: that raises on the first bad `.info`."""
    root = Path(table_root)
    if not root.is_dir():
        return []
    if table_name:
        one = root / table_name
        return [one] if one.is_dir() else []
    return sorted(
        (d for d in root.iterdir() if d.is_dir() and not d.name.startswith(".")),
        key=lambda d: d.name.lower(),
    )


def _info_path(table_dir: Path) -> Path:
    return table_dir / f"{table_dir.name}.info"


def pending_upgrade(table_dir) -> bool:
    """Whether this folder's `.info` still holds the 2.x shape. False if it cannot be read."""
    table_dir = Path(table_dir)
    if not _info_path(table_dir).exists():
        return False
    try:
        return MetaConfig(str(_info_path(table_dir))).pending_migration
    except (InvalidMetaConfigError, OSError):
        return False


def upgrade_library(
    table_root,
    table_name: str | None = None,
    progress_cb=None,
    log_cb=None,
) -> dict:
    """Upgrade every table's `.info` in one pass.

    Startup already does the library, so this is the repair for what it did not reach.
    """
    reporter = JobReporter(logger, progress_cb=progress_cb, log_cb=log_cb)
    log = reporter.log

    folders = table_dirs(table_root, table_name)
    total = len(folders)
    result = {"upgraded": 0, "already_current": 0, "failed": 0, "failures": []}

    log("Upgrading .info files. Each one is backed up first, so this can be undone.")
    reporter.progress(0, total, "Starting")

    for index, table_dir in enumerate(folders, start=1):
        reporter.progress(index, total, table_dir.name)
        info_path = _info_path(table_dir)
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
            result["failures"].append((table_dir.name, str(exc)))
            log(f"Left alone, could not be read: {table_dir.name}")
            continue
        result["upgraded"] += 1
        log(f"Upgraded: {table_dir.name}")

    log(_upgrade_summary(result))
    return result


def restore_library(
    table_root,
    table_name: str | None = None,
    max_schema: int = CURRENT_SCHEMA,
    progress_cb=None,
    log_cb=None,
) -> dict:
    """Put back the newest readable backup in every folder that has one.

    All or nothing: nobody chose which tables upgraded, so nobody can choose which return.
    """
    reporter = JobReporter(logger, progress_cb=progress_cb, log_cb=log_cb)
    log = reporter.log

    folders = table_dirs(table_root, table_name)
    total = len(folders)
    result = {"restored": 0, "nothing_to_restore": 0, "failed": 0, "failures": []}

    log("Restoring backups. Your current .info files are backed up first, so this can be "
        "undone too.")
    reporter.progress(0, total, "Starting")

    for index, table_dir in enumerate(folders, start=1):
        reporter.progress(index, total, table_dir.name)
        chosen = restorable_backup(table_dir, max_schema)
        if not chosen:
            result["nothing_to_restore"] += 1
            continue
        info_path = _info_path(table_dir)
        try:
            if info_path.exists():
                copy_aside(str(info_path))
            replace_atomic(chosen, info_path)
        except OSError as exc:
            result["failed"] += 1
            result["failures"].append((table_dir.name, str(exc)))
            log(f"Left as it is, could not be restored: {table_dir.name}")
            continue
        result["restored"] += 1
        log(f"Restored: {table_dir.name}")

    log(_restore_summary(result))
    return result


def _tables(count: int) -> str:
    return f"{count} table" if count == 1 else f"{count} tables"


def _files(count: int) -> str:
    return "1 .info file" if count == 1 else f"{count} .info files"


def _upgrade_summary(result: dict) -> str:
    if not result["upgraded"]:
        return "Nothing to upgrade - every .info file is already on the current format."
    summary = (
        f"Upgraded {_files(result['upgraded'])}. Ratings, favourites, tags and play "
        "counts came across unchanged, and a backup of each was saved."
    )
    if result["failed"]:
        summary += (
            f" {_tables(result['failed'])} could not be read and were left exactly as "
            "they were."
        )
    return summary


def _restore_summary(result: dict) -> str:
    if not result["restored"]:
        return "Nothing to restore - there are no backups."
    summary = (
        f"Restored {_files(result['restored'])}. Their ratings, favourites, tags and play "
        "counts are back as this version recorded them."
    )
    if result["nothing_to_restore"]:
        summary += (
            f" {_tables(result['nothing_to_restore'])} were never upgraded, so there was "
            "nothing to put back."
        )
    if result["failed"]:
        summary += (
            f" {_tables(result['failed'])} could not be restored and were left as they are."
        )
    return summary
