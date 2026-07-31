"""Put back a `.info` file that a newer VPinFE converted.

A newer release rewrites each table's `.info` into a shape this one does not understand,
and keeps the original beside it first. That copy is useless unless the release somebody
downgrades *to* can find it - which is this module, and why it ships here rather than
there.

The filename convention is a contract between two releases and neither side may change it
alone:

    Attack from Mars (Bally 1995).info                            <- live
    Attack from Mars (Bally 1995).info.vpinfe-20260729T143022Z    <- saved copy

Which shape a saved copy holds is read out of its content, never its name. A file with no
`schema` key predates versioning and is one this build wrote; anything carrying one was
written by a newer build and is left alone.

Restoring is library-wide on purpose. Conversion happens per table as tables get used, so
the user never chose which ones converted and cannot be asked to choose which come back.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger("vpinfe.common.info_restore")

BACKUP_MARKER = ".vpinfe-"


def converted_by_newer(meta):
    """Whether this table's live .info was written by a newer VPinFE.

    The signal the offer to restore hangs on. Saved copies alone are not it: after a
    restore they are still lying in the folder, and offering to put back a file that is
    already in place reads as though the restore did not work.
    """
    if not isinstance(meta, dict):
        return False
    section = meta.get("vpinfe")
    return isinstance(section, dict) and bool(section.get("schema"))


def backup_names(names, info_name):
    """The saved copies in a folder listing, newest first.

    Takes names rather than a path so this can ride a scan the caller is already doing: on
    a network share the listing is the expensive part. The timestamp is ISO 8601 basic, so
    lexical order is chronological.
    """
    prefix = info_name + BACKUP_MARKER
    return sorted((n for n in names if n.startswith(prefix)), reverse=True)


def backup_schema(path):
    """The schema a saved copy declares, or None when it predates versioning."""
    with open(path, encoding="utf-8") as handle:
        data = json.load(handle)
    section = data.get("vpinfe") if isinstance(data, dict) else None
    if not isinstance(section, dict):
        return None
    return int(section.get("schema") or 0) or None


def backup_path(info_path, when=None):
    """Where a saved copy goes. UTC and no colons, because Windows will not have them."""
    stamp = (when or datetime.now(timezone.utc)).strftime("%Y%m%dT%H%M%SZ")
    return f"{info_path}{BACKUP_MARKER}{stamp}"


def copy_aside(info_path, when=None):
    """Keep the current file before a restore replaces it, whatever state it is in.

    Deliberately does not check that it parses. A file too broken to read is a file
    somebody is restoring *because* it is broken, and refusing to keep it would block the
    rescue to protect a copy nobody wants back.
    """
    path = backup_path(info_path, when)
    while os.path.exists(path):        # never overwrite a restore point
        when = when or datetime.now(timezone.utc)
        when = when.replace(second=(when.second + 1) % 60)
        path = backup_path(info_path, when)
    shutil.copy2(info_path, path)
    return path


def table_dirs(table_root, table_name=None):
    """Table folders under the root, in name order."""
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


def restorable_backup(table_dir, names=None):
    """The saved copy this build would put back in this folder, or None.

    Newest first, and the first one this build can actually read wins. A copy written by a
    newer VPinFE is stepped over rather than treated as the end of the list - the one
    behind it is usually exactly what is wanted.

    Reads each candidate, so callers pass `names` when they have already listed the folder.
    Only folders holding a saved copy pay for it, which for anyone who never ran a newer
    VPinFE is none of them.
    """
    table_dir = Path(table_dir)
    if names is None:
        try:
            names = os.listdir(table_dir)
        except OSError:
            return None
    info_name = f"{table_dir.name}.info"
    for name in backup_names(names, info_name):
        candidate = table_dir / name
        try:
            schema = backup_schema(candidate)
        except (OSError, ValueError):
            logger.warning("Unreadable saved copy, skipping: %s", candidate)
            continue
        if schema is None:
            return str(candidate)
    return None


def restore_library(table_root, table_name=None, progress_cb=None, log_cb=None):
    """Put back the newest readable copy in every folder that has one.

    Never stops on one bad folder: an unreadable file is the state somebody is trying to
    get out of, and failing the run would withhold the fix from every other table.
    """
    def log(message):
        logger.info(message)
        if log_cb:
            log_cb(message)

    folders = table_dirs(table_root, table_name)
    total = len(folders)
    result = {"restored": 0, "nothing_to_restore": 0, "failed": 0, "failures": []}

    log("Restoring table info from the copies saved before a newer VPinFE converted it. "
        "Your current info is kept first, so this can be undone too.")

    for index, table_dir in enumerate(folders, start=1):
        if progress_cb:
            try:
                progress_cb(index, total, table_dir.name)
            except Exception:
                logger.debug("Progress callback failed", exc_info=True)
        chosen = restorable_backup(table_dir)
        if not chosen:
            result["nothing_to_restore"] += 1
            continue
        info_path = table_dir / f"{table_dir.name}.info"
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

    log(_summary(result))
    return result


def _tables(count):
    return f"{count} table" if count == 1 else f"{count} tables"


def _summary(result):
    if not result["restored"]:
        return "Nothing to restore - no table has info saved by a newer VPinFE."
    summary = (
        f"Restored {_tables(result['restored'])}. Their ratings, favourites, tags and play "
        "counts are back as this version recorded them."
    )
    if result["nothing_to_restore"]:
        summary += (
            f" {_tables(result['nothing_to_restore'])} were never converted, so there was "
            "nothing to put back."
        )
    if result["failed"]:
        summary += (
            f" {_tables(result['failed'])} could not be restored and were left as they are."
        )
    return summary
