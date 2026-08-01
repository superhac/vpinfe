"""Upgrade a library of `.info` files to schema 2, or put back what a newer build upgraded.

Both walk the table root one folder at a time and neither stops on a bad file. One
unreadable `.info` is exactly the state somebody is trying to get out of, so failing the
whole run over it would withhold the fix from the other 1,300 tables.

Upgrade is a format change only: no `.vpx` is re-read and nothing is downloaded. That is
what separates this from a metadata build, which upgrades too but pays for a full re-parse.
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

from common.jobs import JobReporter
from common.tables.info_migration import CURRENT_SCHEMA, copy_aside, restorable_backup
from common.tables.metaconfig import InvalidMetaConfigError, MetaConfig

logger = logging.getLogger("vpinfe.common.tables.info_maintenance")


def table_dirs(table_root, table_name: str | None = None) -> list[Path]:
    """Table folders under the root, in name order.

    Deliberately not TableParser.loadTables: that raises on the first unreadable `.info`,
    which is the library this module exists to repair.
    """
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
    """Upgrade every table's `.info` to the current schema in one pass.

    The lazy path upgrades a table when something writes it, so this is the same work
    brought forward - not a different upgrade.
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

    All or nothing by design: the user did not choose which tables upgraded, so they
    cannot be asked to choose which ones come back.
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
            shutil.copy2(chosen, info_path)
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


def _upgrade_summary(result: dict) -> str:
    if not result["upgraded"]:
        return "Nothing to upgrade - every .info file is already on the current format."
    summary = (
        f"Upgraded {_tables(result['upgraded'])}. Ratings, favourites, tags and play "
        "counts came across unchanged, and the old file is saved beside each one if you "
        "ever want to go back."
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
        f"Restored {_tables(result['restored'])}. Their ratings, favourites, tags and play "
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
