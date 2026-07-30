"""Bring an unversioned 2.x `.info` up to schema 2.

The only migration there is: 2.x wrote no version, so a file either carries a schema
stamp or predates the idea. See INFO-SCHEMA.local.md for why each section moved.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime

from common.tables.game_files import GAME_FILES_KEY, parse_authors
from common.timestamps import iso_from_asctime, iso_from_authored_date

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
    """Whether this file has been through a schema, in either section name."""
    if not isinstance(data, dict):
        return False
    for name in ("vpinfe", "VPinFE"):
        section = data.get(name)
        if isinstance(section, dict) and section.get(SCHEMA_KEY):
            return True
    return False


def needs_migration(data) -> bool:
    """An unversioned file carrying anything 2.x wrote."""
    if not isinstance(data, dict) or is_versioned(data):
        return False
    if any(name in data for name in _DROPPED_SECTIONS):
        return True
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
        game_files[filename] = _game_file_entry(vpx_file, authors)
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


def write_backup(info_path, original_text: str, when: datetime | None = None) -> str:
    """Copy the file aside before it is rewritten, and prove the copy is readable.

    A truncated backup is worse than none: it is the one file whose failure is only
    discovered at the moment somebody needs it.
    """
    json.loads(original_text)
    path = backup_path(info_path, when)
    while os.path.exists(path):        # never overwrite a restore point
        when = (when or datetime.now(UTC))
        when = when.replace(second=(when.second + 1) % 60)
        path = backup_path(info_path, when)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(original_text)
    with open(path, encoding="utf-8") as handle:
        json.load(handle)
    return path
