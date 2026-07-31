"""Bring an unversioned 2.x `.info` up to schema 2.

The only migration there is: 2.x wrote no version, so a file either carries a schema
stamp or predates the idea. See INFO-SCHEMA.local.md for why each section moved.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
from datetime import UTC, datetime
from pathlib import Path

from common.tables.game_files import GAME_FILES_KEY, parse_authors
from common.timestamps import iso_from_asctime, iso_from_authored_date

logger = logging.getLogger("vpinfe.common.tables.info_migration")

SCHEMA_KEY = "schema"
CURRENT_SCHEMA = 2
BACKUP_MARKER = ".vpinfe-"

# What 2.x called each VPXFile field, against what it is called now. Matched
# case-insensitively: real files carry both `detectnfozzy` and `detectNfozzy`, and a
# case-sensitive lookup silently drops the flag.
_GAME_FILE_KEYS = {
    "filehash": "file_hash",
    "vbshash": "vbs_hash",
    "version": "version",
    "releasedate": "release_date",
    "savedate": "save_date",
    "saverev": "save_rev",
    "manufacturer": "manufacturer",
    "year": "year",
    "type": "type",
    "rom": "rom",
    "detectnfozzy": "detect_nfozzy",
    "detectfleep": "detect_fleep",
    "detectssf": "detect_ssf",
    "detectlut": "detect_lut",
    "detectscorebit": "detect_scorbit",     # the old name was a typo for Scorbit
    "detectfastflips": "detect_fastflips",
    "detectflex": "detect_flex",
    "detectpinmame": "detect_pinmame",
}

_VPINFE_KEYS = {
    "deletednvramonclose": "delete_nvram_on_close",
    "altlauncher": "alt_launcher",
    "pluginprofile": "plugin_profile",
    "alttitle": "alt_title",
    "altvpsid": "alt_vpsid",
}

_DROPPED_SECTIONS = ("VPXFile", "Medias")
_DROPPED_INFO_KEYS = ("Rom",)


def is_versioned(data) -> bool:
    """Whether this file has been through the migration.

    Only the section we write today counts. A `schema` in the old PascalCase section is
    a different number that meant something else - the shape of that section alone, from
    a 3.0 build before the rename - and reading it as "already migrated" leaves the file
    half converted: no game_files, and every consumer of them empty.
    """
    if not isinstance(data, dict):
        return False
    section = data.get("vpinfe")
    return isinstance(section, dict) and bool(section.get(SCHEMA_KEY))


def needs_migration(data) -> bool:
    """An unversioned file carrying anything 2.x wrote, or a migrated one 2.x wrote again.

    We never write VPXFile or Medias, so finding either in a versioned file is proof a 2.x
    build rebuilt it after the migration - and its game_files went stale the moment that
    happened. Checked ahead of the version stamp, which is the thing not to trust here.
    """
    if not isinstance(data, dict):
        return False
    if any(name in data for name in _DROPPED_SECTIONS):
        return True
    if is_versioned(data):
        return False
    user = data.get("User")
    if isinstance(user, dict) and "FrontendDOFEvent" in user:
        return True
    legacy = data.get("VPinFE")
    return isinstance(legacy, dict) and any(k.lower() in _VPINFE_KEYS for k in legacy)


def _rename(source: dict, mapping: dict) -> dict:
    renamed = {}
    for key, value in source.items():
        new_key = mapping.get(key.lower())
        if new_key:
            renamed[new_key] = value
    return renamed


def _game_file_entry(vpx_file: dict, authors) -> dict:
    entry = _rename(vpx_file, _GAME_FILE_KEYS)
    entry["release_date"] = iso_from_authored_date(entry.get("release_date", ""))
    entry["save_date"] = iso_from_asctime(entry.get("save_date", ""))
    entry["authors"] = parse_authors(authors)
    return entry


def migrate(data: dict) -> dict:
    """The 2.x file as schema 2. Pure: takes a loaded .info, returns a new one."""
    info = dict(data.get("Info") or {})
    user = dict(data.get("User") or {})
    legacy = data.get("VPinFE")
    legacy = dict(legacy) if isinstance(legacy, dict) else {}
    vpx_file = data.get("VPXFile")
    vpx_file = dict(vpx_file) if isinstance(vpx_file, dict) else {}

    # Authors were table-level, which only worked while a folder held one game file.
    # With exactly one, they are that file's - a real recorded fact, so it carries.
    authors = info.pop("Authors", None)
    for key in _DROPPED_INFO_KEYS:
        info.pop(key, None)

    vpinfe = _rename(legacy, _VPINFE_KEYS)
    # Anything else in there came from somewhere we don't know about; it stays as it is.
    vpinfe.update({k: v for k, v in legacy.items() if k.lower() not in _VPINFE_KEYS})
    # A file already holding the new section keeps it, and it wins: running this over
    # its own output has to be a no-op, or the second call eats the first.
    already = data.get("vpinfe")
    if isinstance(already, dict):
        vpinfe.update(already)
    vpinfe[SCHEMA_KEY] = CURRENT_SCHEMA

    # The DOF override is configuration, and User is the interop contract for play
    # history. It moves, and the old key goes with it.
    dof_event = user.pop("FrontendDOFEvent", None)
    if dof_event is not None:
        vpinfe["frontend_dof_event"] = dof_event

    game_files = dict(data.get(GAME_FILES_KEY) or {})
    filename = str(vpx_file.get("filename", "") or "").strip()
    if filename:
        # Refresh what VPXFile covers and leave the rest - hidden, source, play stats.
        # Nothing to keep on a first migration; everything to lose when 2.x wrote the
        # file again and this runs over an entry we already built.
        prior = game_files.get(filename)
        prior = prior if isinstance(prior, dict) else {}
        game_files[filename] = {**prior, **_game_file_entry(vpx_file, authors)}
        # Every theme so far assumes one table means one game file, so the file 2.x
        # described stays the one a single-game-file consumer gets.
        vpinfe.setdefault("default_game_file", filename)

    migrated = {"Info": info, "User": user, "vpinfe": vpinfe, GAME_FILES_KEY: game_files}
    known = {*_DROPPED_SECTIONS, "Info", "User", "VPinFE", "vpinfe", GAME_FILES_KEY}
    migrated.update({k: v for k, v in data.items() if k not in known})
    return migrated


def backup_path(info_path, when: datetime | None = None) -> str:
    """Where the pre-migration copy goes.

    Timestamped rather than .bak, so restore points accumulate instead of the last one
    winning. UTC and no colons, because Windows will not have them in a filename.
    """
    stamp = (when or datetime.now(UTC)).strftime("%Y%m%dT%H%M%SZ")
    return f"{info_path}{BACKUP_MARKER}{stamp}"


def backup_names(names, info_name: str) -> list[str]:
    """The pre-migration copies in a folder listing, newest first.

    Takes names rather than a path so this can ride a scan the caller is already doing:
    on a network share the listing is the expensive part, and the library walk has it.
    The timestamp is ISO 8601 basic, so lexical order is chronological.
    """
    prefix = info_name + BACKUP_MARKER
    return sorted((n for n in names if n.startswith(prefix)), reverse=True)


def restorable_backup(table_dir, max_schema: int = CURRENT_SCHEMA, names=None) -> str | None:
    """The backup this build would restore in this folder, or None.

    Newest first, and the first one whose schema this build can read wins. Older ones stay
    as deeper restore points, and a backup written by a *newer* build is stepped over
    rather than ending the search - the one behind it is usually what is wanted.

    Reads each candidate, so callers pass `names` when they have already listed the folder.
    Only folders that hold a backup pay for it, which for anyone who never converted is
    none of them.
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
            logger.warning("Unreadable backup, skipping: %s", candidate)
            continue
        if schema is None or schema <= max_schema:
            return str(candidate)
    return None


def backup_schema(path) -> int | None:
    """The schema a backup holds, or None when it predates versioning. Raises if unreadable."""
    with open(path, encoding="utf-8") as handle:
        data = json.load(handle)
    section = data.get("vpinfe") if isinstance(data, dict) else None
    if not isinstance(section, dict):
        return None
    return int(section.get(SCHEMA_KEY) or 0) or None


def _free_backup_path(info_path, when: datetime | None = None) -> str:
    path = backup_path(info_path, when)
    while os.path.exists(path):        # never overwrite a restore point
        when = (when or datetime.now(UTC))
        when = when.replace(second=(when.second + 1) % 60)
        path = backup_path(info_path, when)
    return path


def write_backup(info_path, original_text: str, when: datetime | None = None) -> str:
    """Copy the file aside before it is rewritten, and prove the copy is readable.

    A truncated backup is worse than none: it is the one file whose failure is only
    discovered at the moment somebody needs it.
    """
    json.loads(original_text)
    path = _free_backup_path(info_path, when)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(original_text)
    with open(path, encoding="utf-8") as handle:
        json.load(handle)
    return path


def copy_aside(info_path, when: datetime | None = None) -> str:
    """Keep the current file before a restore replaces it, whatever state it is in.

    Deliberately does not check the JSON the way write_backup does. A file too broken to
    parse is a file somebody is restoring *because* it is broken, and refusing to keep it
    would block the rescue to protect a copy nobody wants back.
    """
    path = _free_backup_path(info_path, when)
    shutil.copy2(info_path, path)
    return path
