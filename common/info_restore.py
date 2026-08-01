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

import configparser
import contextlib
from datetime import datetime, timedelta, timezone
import json
import logging
import os
from pathlib import Path
import shutil
import tempfile

logger = logging.getLogger("vpinfe.common.info_restore")

BACKUP_MARKER = ".vpinfe-"
COLLECTIONS_NAME = "collections.ini"
# Both files record the schema under a [vpinfe] / "vpinfe" section, so the rule for "can
# this build read it" is the same in each: no schema key means it predates versioning.
SCHEMA_SECTION = "vpinfe"
SCHEMA_KEY = "schema"


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
    """The schema a saved .info declares, or None when it predates versioning."""
    with open(path, encoding="utf-8") as handle:
        data = json.load(handle)
    section = data.get(SCHEMA_SECTION) if isinstance(data, dict) else None
    if not isinstance(section, dict):
        return None
    return int(section.get(SCHEMA_KEY) or 0) or None


def collections_schema(path):
    """The schema a saved collections.ini declares, or None when it predates versioning."""
    parser = configparser.ConfigParser()
    parser.read(path, encoding="utf-8")
    if SCHEMA_SECTION not in parser:
        return None
    return int(parser[SCHEMA_SECTION].get(SCHEMA_KEY, 0) or 0) or None


def newest_readable_backup(directory, filename, schema_reader, names=None):
    """The newest backup of `filename` this build can read, or None.

    A copy written by a newer VPinFE is stepped over rather than ending the search - the
    one behind it is usually what is wanted.
    """
    directory = Path(directory)
    if names is None:
        try:
            names = os.listdir(directory)
        except OSError:
            return None
    for name in backup_names(names, filename):
        candidate = directory / name
        try:
            if schema_reader(candidate) is None:
                return str(candidate)
        except Exception:
            logger.warning("Unreadable saved copy, skipping: %s", candidate)
    return None


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
        # A whole second, not the second field: replace(second=(s + 1) % 60) wraps 59 to
        # 0, and the name that is supposed to be newer then sorts 59 seconds older. These
        # names are the only ordering a restore has.
        when = (when or datetime.now(timezone.utc)) + timedelta(seconds=1)
        path = backup_path(info_path, when)
    shutil.copy2(info_path, path)
    return path


def replace_atomic(source, path):
    """Put `source` in place at `path` with no window where `path` is half written.

    A plain copy over the live file truncates it first. Restoring does that once per
    table across the whole library, and it is the operation somebody reaches for when
    things have already gone wrong - the worst one to leave a truncated file behind.
    """
    directory = os.path.dirname(path) or "."
    handle_fd, tmp = tempfile.mkstemp(dir=directory, prefix=".vpinfe_write_", suffix=".tmp")
    os.close(handle_fd)
    try:
        shutil.copy2(source, tmp)
        os.replace(tmp, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise


def write_json_atomic(path, data):
    """Write a .info so a reader sees either the old file or the new one, never half of one.

    A plain open(path, "w") truncates before it writes, so an interrupted write leaves a
    truncated file - and an unreadable .info is the one failure the library cannot shrug
    off.
    """
    directory = os.path.dirname(path) or "."
    # Must not look like a .info or a backup to anything scanning the folder.
    handle_fd, tmp = tempfile.mkstemp(dir=directory, prefix=".vpinfe_write_", suffix=".tmp")
    try:
        with os.fdopen(handle_fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=4)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise


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
    """The saved .info this build would put back in this folder, or None."""
    table_dir = Path(table_dir)
    return newest_readable_backup(
        table_dir, f"{table_dir.name}.info", backup_schema, names)


def restorable_collections_backup(config_dir):
    """The saved collections.ini this build would put back, or None."""
    return newest_readable_backup(config_dir, COLLECTIONS_NAME, collections_schema)


def restore_file(path, backup):
    """Put `backup` in place at `path`, keeping what is there now."""
    if os.path.exists(path):
        copy_aside(str(path))
    replace_atomic(backup, path)


def restore_library(table_root, table_name=None, config_dir=None,
                    progress_cb=None, log_cb=None):
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
    result = {"restored": 0, "nothing_to_restore": 0, "failed": 0, "failures": [],
              "collections_restored": False}

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
            restore_file(info_path, chosen)
        except OSError as exc:
            result["failed"] += 1
            result["failures"].append((table_dir.name, str(exc)))
            log(f"Left as it is, could not be restored: {table_dir.name}")
            continue
        result["restored"] += 1
        log(f"Restored: {table_dir.name}")

    # Collections live in the config directory, not a table folder, and a newer VPinFE
    # rewrites their membership onto ids this build cannot resolve. Same rules: newest
    # readable copy, keep what is there now, never delete.
    if config_dir:
        chosen = restorable_collections_backup(config_dir)
        if chosen:
            try:
                restore_file(Path(config_dir) / COLLECTIONS_NAME, chosen)
                result["collections_restored"] = True
                log("Restored your collections.")
            except OSError as exc:
                result["failed"] += 1
                result["failures"].append((COLLECTIONS_NAME, str(exc)))
                log("Left as it is, could not be restored: your collections")

    log(_summary(result))
    return result


def _tables(count):
    return f"{count} table" if count == 1 else f"{count} tables"


def _summary(result):
    if not result["restored"]:
        return "Nothing to restore - no table has info saved by a newer VPinFE."
    summary = (
        f"Restored {_tables(result['restored'])}. Their ratings, favorites, tags and play "
        "counts are back as this version recorded them."
    )
    if result["collections_restored"]:
        summary += " Your collections are back too."
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
