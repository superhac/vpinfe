from __future__ import annotations

import ast
from pathlib import Path
from typing import Any, Dict

from common.games.ids import new_id
from common.games.info_file import VPINFE_SECTION, MetaConfig
from common.games.tables import (
    DETECT_KEYS,
    TABLE_FILENAME_KEY,
    TABLE_ID_KEY,
    TABLES_KEY,
    entry_for_filename,
    recorded_default,
    rekey_by_id,
    table_entries,
    table_filenames,
)
from common.games.tables import (
    default_table as _resolve_default,
)

# Re-exported so the theme payload and the Manager UI agree with storage. Sourced
# from the tables module rather than restated, since a second list drifts silently -
# it already did: these held the old spellings and were writing dead `detectssf`
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


def default_table(meta: Any, names: Any = None,
                      folder_name: str = "") -> tuple[str, Dict[str, Any]]:
    """(filename, entry) for the table this game defaults to; ("", {}) when it has none.

    Returns both because the callers that need one usually need the other - a row on the
    games list shows the filename and the version off the same table - and resolving
    twice would be doing the same work to answer half the question each time.

    Callers holding a folder listing should pass it, so a recorded default that is no
    longer on disk falls through to one that is.
    """
    normalized = normalize_meta(meta)
    entries = table_entries(normalized)
    candidates = list(names) if names is not None else table_filenames(entries)
    name = _resolve_default(candidates, folder_name,
                            recorded_default(vpinfe_section(normalized), entries))
    return name, entry_for_filename(entries, name)[1]


def default_table_entry(meta: Any, names: Any = None, folder_name: str = "") -> Dict[str, Any]:
    """What the game's default table says about itself, or {}."""
    return default_table(meta, names, folder_name)[1]


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
    game used to be enough to make every consumer's type assumption wrong; now it
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


def game_title(game) -> str:
    meta = normalize_meta(getattr(game, "metaConfig", {}))
    vpinfe = vpinfe_section(meta)
    info = section(meta, "Info")
    alt_title = str(vpinfe.get("alt_title", "") or "").strip()
    if alt_title:
        # A user-set alt_title wins on its own - it does not require an alt_vpsid -
        # and is left exactly as entered, never reordered.
        return alt_title
    raw = str(info.get("Title", "") or get_meta_value(meta, "VPSdb", "name", "") or getattr(game, "gameDirName", "") or "").strip()
    return reorder_leading_article(raw)


def game_themes(game) -> list[str]:
    meta = normalize_meta(getattr(game, "metaConfig", {}))
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


def game_type(game) -> str:
    meta = normalize_meta(getattr(game, "metaConfig", {}))
    return str(first_meta_value(meta, ("Info", "Type"), ("VPSdb", "type"), default="") or "")


def game_manufacturer(game) -> str:
    meta = normalize_meta(getattr(game, "metaConfig", {}))
    return str(first_meta_value(meta, ("Info", "Manufacturer"), ("VPSdb", "manufacturer"), default="") or "")


def game_year(game) -> str:
    meta = normalize_meta(getattr(game, "metaConfig", {}))
    value = first_meta_value(meta, ("Info", "Year"), ("VPSdb", "year"), default="")
    return str(value) if value else ""


def game_rating(game) -> int:
    meta = normalize_meta(getattr(game, "metaConfig", {}))
    return normalize_rating(get_meta_value(meta, "User", "Rating", 0))


def game_frontend_dof_event(game) -> str:
    """The DOF effect a game asks for when selected, or "" to use the default."""
    meta = normalize_meta(getattr(game, "metaConfig", {}))
    return str(vpinfe_section(meta).get("frontend_dof_event", "") or "").strip()


def game_vps_id(game) -> str:
    meta = normalize_meta(getattr(game, "metaConfig", {}))
    alt_vpsid = str(vpinfe_section(meta).get("alt_vpsid", "") or "").strip()
    if alt_vpsid:
        return alt_vpsid
    return str(section(meta, "Info").get("VPSId", "") or "").strip()


def base_game_vps_id(game) -> str:
    return str(section(getattr(game, "metaConfig", {}), "Info").get("VPSId", "") or "").strip()


def get_or_create_user_meta(config: Dict[str, Any]) -> Dict[str, Any]:
    user = config.setdefault("User", {})
    user.setdefault("Rating", 0)
    user.setdefault("Favorite", 0)
    user.setdefault("LastRun", None)
    user.setdefault("StartCount", 0)
    user.setdefault("RunTime", 0)
    user.setdefault("Tags", [])
    return user


def get_or_create_table_user(config: dict[str, Any], filename: str) -> dict[str, Any]:
    """One table's play record, created on its first launch.

    Counters only. A per-table rating and favorite are in the design but nothing
    sets them, and storing a field no producer fills invites a reader to trust it.
    """
    entries = rekey_by_id(config.setdefault(TABLES_KEY, {}))
    config[TABLES_KEY] = entries
    found_id, entry = entry_for_filename(entries, filename)
    if not entry:
        found_id = new_id()
        entry = {TABLE_ID_KEY: found_id, TABLE_FILENAME_KEY: filename}
        entries[found_id] = entry
    user = entry.setdefault("user", {})
    user.setdefault("last_run", None)
    user.setdefault("start_count", 0)
    user.setdefault("run_time_seconds", 0)
    return user


def meta_file_path(game) -> Path:
    return Path(game.fullPathGame) / f"{game.gameDirName}.info"


def load_game_meta(game) -> Dict[str, Any]:
    meta_path = meta_file_path(game)
    if meta_path.exists():
        return normalize_meta(MetaConfig(str(meta_path)).data)
    return normalize_meta(getattr(game, "metaConfig", {}))


def persist_game_meta(game, config: Dict[str, Any]) -> None:
    meta_file = MetaConfig(str(meta_file_path(game)))
    upgraded = meta_file.pending_migration
    meta_file.data = config
    meta_file.writeConfig()
    game.metaConfig = config
    # Both flags were read during the scan, and this write is what makes them wrong.
    # Nothing is pending once the file is on disk, and an upgrade has just left a
    # restore point behind it. Without this the id backfill upgrades the whole library
    # at startup and every loaded game still claims it needs upgrading - which is what
    # the Manager UI then reports, for as long as the process lives.
    game.info_pending_upgrade = False
    if upgraded:
        game.info_restorable = True
