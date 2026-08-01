from __future__ import annotations

import ast
from pathlib import Path
from typing import Any, Dict

from common.tables.game_files import (
    DETECT_KEYS,
    GAME_FILES_KEY,
    default_game_file as _resolve_default,
    game_file_entries,
    recorded_default,
)
from common.tables.metaconfig import VPINFE_SECTION, MetaConfig


# Re-exported so the theme payload and the Manager UI agree with storage. Sourced
# from game_files rather than restated, since a second list drifts silently - it
# already did: these held the pre-rename names and were writing dead `detectssf`
# keys over the top of the real `detect_ssf` ones.
DETECTION_KEYS = DETECT_KEYS


def normalize_meta(meta: Any) -> Dict[str, Any]:
    if isinstance(meta, dict):
        return meta
    if hasattr(meta, "getConfig"):
        data = meta.getConfig()
        return data if isinstance(data, dict) else {}
    if hasattr(meta, "config") and isinstance(meta.config, dict):
        return meta.config
    return {}


def section(meta: Any, name: str) -> Dict[str, Any]:
    normalized = normalize_meta(meta)
    value = normalized.get(name, {})
    return value if isinstance(value, dict) else {}


def vpinfe_section(meta: Any) -> Dict[str, Any]:
    """The section VPinFE owns. Read through here rather than by name, so the name
    lives in one place."""
    return section(meta, VPINFE_SECTION)


def get_meta_value(meta: Any, section_name: str, key: str, fallback: Any = "") -> Any:
    sec = section(meta, section_name)
    value = sec.get(key, fallback)
    return fallback if value is None else value


def first_meta_value(meta: Any, *paths: tuple[str, str], default: Any = "") -> Any:
    for section_name, key in paths:
        value = get_meta_value(meta, section_name, key, None)
        if value not in ("", None):
            return value
    return default


def default_game_file(meta: Any, names: Any = None,
                      folder_name: str = "") -> tuple[str, Dict[str, Any]]:
    """(filename, entry) for the game file this table defaults to; ("", {}) when it has none.

    Returns both because the callers that need one usually need the other - a table row
    shows the filename and the version off the same game file - and resolving twice would
    be doing the same work to answer half the question each time.

    Callers holding a folder listing should pass it, so a recorded default that is no
    longer on disk falls through to one that is.
    """
    normalized = normalize_meta(meta)
    entries = game_file_entries(normalized)
    candidates = list(names) if names is not None else list(entries)
    name = _resolve_default(candidates, folder_name,
                            recorded_default(vpinfe_section(normalized)))
    entry = entries.get(name)
    return name, (entry if isinstance(entry, dict) else {})


def default_game_file_entry(meta: Any, names: Any = None, folder_name: str = "") -> Dict[str, Any]:
    """What the table's default game file says about itself, or {}."""
    return default_game_file(meta, names, folder_name)[1]


def normalize_rating(value: Any) -> int:
    try:
        normalized = int(float(value))
    except (TypeError, ValueError):
        normalized = 0
    return max(0, min(5, normalized))


def as_string_list(value: Any) -> list[str]:
    """A list-valued metadata field, whatever the .info actually held.

    These come back as lists from a normal metadata build, but a hand-edited or
    badly-written .info can hold a scalar - including a stringified list. One such
    table used to be enough to make every consumer's type assumption wrong; now it
    is contained here.

    A scalar becomes a one-item list rather than being parsed. Reading
    "['a', 'b']" back as two items would mean inventing a syntax for a file format
    that does not have one, so the odd value stays visible instead.
    """
    if value in ("", None):
        return []
    if isinstance(value, (list, tuple)):
        return [str(item) for item in value]
    return [str(value)]


def reorder_leading_article(title: Any) -> str:
    """Move a leading "The " article to the end so titles sort by their
    second word, e.g. "The Addams Family" -> "Addams Family, The".

    Idempotent: a title that has already been reordered (or never started
    with "The") is returned unchanged. Only the whole word "The" followed by
    more text is reordered ("Theatre of Magic" is left alone).
    """
    text = str(title or "").strip()
    if not text:
        return text
    parts = text.split(None, 1)
    if len(parts) == 2 and parts[0].lower() == "the":
        return f"{parts[1]}, {parts[0]}"
    return text


def table_title(table) -> str:
    meta = normalize_meta(getattr(table, "metaConfig", {}))
    vpinfe = vpinfe_section(meta)
    info = section(meta, "Info")
    if str(vpinfe.get("alt_vpsid", "") or "").strip():
        alt_title = str(vpinfe.get("alt_title", "") or "").strip()
        if alt_title:
            # A user-set alttitle is left exactly as entered - never reordered.
            return alt_title
    raw = str(info.get("Title", "") or get_meta_value(meta, "VPSdb", "name", "") or getattr(table, "tableDirName", "") or "").strip()
    return reorder_leading_article(raw)


def table_themes(table) -> list[str]:
    meta = normalize_meta(getattr(table, "metaConfig", {}))
    value = get_meta_value(meta, "Info", "Themes", None)
    if value:
        return value if isinstance(value, list) else [value]

    legacy = get_meta_value(meta, "VPSdb", "theme", "")
    if not legacy:
        return []
    if isinstance(legacy, list):
        return legacy
    try:
        parsed = ast.literal_eval(str(legacy))
        if isinstance(parsed, list):
            return parsed
    except (ValueError, SyntaxError):
        pass
    return [legacy]


def table_type(table) -> str:
    meta = normalize_meta(getattr(table, "metaConfig", {}))
    return str(first_meta_value(meta, ("Info", "Type"), ("VPSdb", "type"), default="") or "")


def table_manufacturer(table) -> str:
    meta = normalize_meta(getattr(table, "metaConfig", {}))
    return str(first_meta_value(meta, ("Info", "Manufacturer"), ("VPSdb", "manufacturer"), default="") or "")


def table_year(table) -> str:
    meta = normalize_meta(getattr(table, "metaConfig", {}))
    value = first_meta_value(meta, ("Info", "Year"), ("VPSdb", "year"), default="")
    return str(value) if value else ""


def table_rating(table) -> int:
    meta = normalize_meta(getattr(table, "metaConfig", {}))
    return normalize_rating(get_meta_value(meta, "User", "Rating", 0))


def table_frontend_dof_event(table) -> str:
    """The DOF effect a table asks for when selected, or "" to use the default."""
    meta = normalize_meta(getattr(table, "metaConfig", {}))
    return str(vpinfe_section(meta).get("frontend_dof_event", "") or "").strip()


def table_vps_id(table) -> str:
    meta = normalize_meta(getattr(table, "metaConfig", {}))
    alt_vpsid = str(vpinfe_section(meta).get("alt_vpsid", "") or "").strip()
    if alt_vpsid:
        return alt_vpsid
    return str(section(meta, "Info").get("VPSId", "") or "").strip()


def base_table_vps_id(table) -> str:
    return str(section(getattr(table, "metaConfig", {}), "Info").get("VPSId", "") or "").strip()


def get_or_create_user_meta(config: Dict[str, Any]) -> Dict[str, Any]:
    user = config.setdefault("User", {})
    user.setdefault("Rating", 0)
    user.setdefault("Favorite", 0)
    user.setdefault("LastRun", None)
    user.setdefault("StartCount", 0)
    user.setdefault("RunTime", 0)
    user.setdefault("Tags", [])
    return user


def get_or_create_game_file_user(config: dict[str, Any], filename: str) -> dict[str, Any]:
    """One game file's play record, created on its first launch.

    Counters only. A per-game-file rating and favorite are in the design but nothing
    sets them, and storing a field no producer fills invites a reader to trust it.
    """
    entry = config.setdefault(GAME_FILES_KEY, {}).setdefault(filename, {})
    user = entry.setdefault("user", {})
    user.setdefault("last_run", None)
    user.setdefault("start_count", 0)
    user.setdefault("run_time_seconds", 0)
    return user


def meta_file_path(table) -> Path:
    return Path(table.fullPathTable) / f"{table.tableDirName}.info"


def load_table_meta(table) -> Dict[str, Any]:
    meta_path = meta_file_path(table)
    if meta_path.exists():
        return normalize_meta(MetaConfig(str(meta_path)).data)
    return normalize_meta(getattr(table, "metaConfig", {}))


def persist_table_meta(table, config: Dict[str, Any]) -> None:
    meta_file = MetaConfig(str(meta_file_path(table)))
    upgraded = meta_file.pending_migration
    meta_file.data = config
    meta_file.writeConfig()
    table.metaConfig = config
    # Both flags were read during the scan, and this write is what makes them wrong.
    # Nothing is pending once the file is on disk, and a upgrade has just left a
    # restore point behind it. Without this the id backfill upgrades the whole library
    # at startup and every loaded table still claims it needs upgrading - which is what
    # the Tables page then reports, for as long as the process lives.
    table.info_pending_upgrade = False
    if upgraded:
        table.info_restorable = True
