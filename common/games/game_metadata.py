"""Reading a game's `.info`, whichever schema wrote it.

Callers ask for a value, not for a schema version: a file written by 2.x and one
written today answer the same questions here.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

from common.games.ids import new_id
from common.games.info_file import VPINFE_SECTION, MetaConfig
from common.games.tables import (
    DETECT_KEYS,
    TABLE_FILENAME_KEY,
    TABLE_ID_KEY,
    TABLES_KEY,
    entry_filename,
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


def normalize_meta(meta: Any) -> dict[str, Any]:
    if isinstance(meta, dict):
        return meta
    if hasattr(meta, "get_config"):
        data = meta.get_config()
        return data if isinstance(data, dict) else {}
    if hasattr(meta, "config") and isinstance(meta.config, dict):
        return meta.config
    return {}


def section(meta: Any, name: str) -> dict[str, Any]:
    normalized = normalize_meta(meta)
    value = normalized.get(name, {})
    return value if isinstance(value, dict) else {}


def vpinfe_section(meta: Any) -> dict[str, Any]:
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
                      folder_name: str = "") -> tuple[str, dict[str, Any]]:
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


def default_table_entry(meta: Any, names: Any = None, folder_name: str = "") -> dict[str, Any]:
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
    meta = normalize_meta(getattr(game, "meta_config", {}))
    vpinfe = vpinfe_section(meta)
    info = section(meta, "Info")
    alt_title = str(vpinfe.get("alt_title", "") or "").strip()
    if alt_title:
        # A user-set alt_title wins on its own - it does not require an alt_vpsid -
        # and is left exactly as entered, never reordered.
        return alt_title
    raw = str(info.get("Title", "") or get_meta_value(meta, "VPSdb", "name", "") or getattr(game, "gameDirName", "") or "").strip()
    return reorder_leading_article(raw)


def game_tags(game) -> list[str]:
    """The user's own words for a game. A set on the way out: `Tags` is a JSON list and
    nothing has stopped one holding the same word twice."""
    meta = normalize_meta(getattr(game, "meta_config", {}))
    said = section(meta, "User").get("Tags") or []
    if not isinstance(said, list):
        said = [said]
    seen, out = set(), []
    for tag in (str(item).strip() for item in said):
        if tag and tag not in seen:
            seen.add(tag)
            out.append(tag)
    return out


def normalize_tag(text: str) -> str:
    """One tag, as it is stored. Trimmed, and internal runs collapsed - `Wide  Body `
    must not become a second tag. Case is left alone on purpose: Chris, 2026-09-01,
    the picker surfaces close matches and the user decides."""
    return " ".join(str(text or "").split())


def set_game_tags(game, tags) -> list[str]:
    """Write the whole set, returning what was stored.

    A whole-value write, like the rating: the set is the resource. Normalized and
    de-duplicated here rather than at a call site, so every writer agrees.
    """
    stored: list[str] = []
    seen: set[str] = set()
    for tag in tags or []:
        said = normalize_tag(tag)
        if said and said not in seen:
            seen.add(said)
            stored.append(said)
    config = load_game_meta(game)
    get_or_create_user_meta(config)["Tags"] = stored
    persist_game_meta(game, config)
    game.meta_config = config
    return stored


def game_themes(game) -> list[str]:
    meta = normalize_meta(getattr(game, "meta_config", {}))
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
    meta = normalize_meta(getattr(game, "meta_config", {}))
    return str(first_meta_value(meta, ("Info", "Type"), ("VPSdb", "type"), default="") or "")


def game_manufacturer(game) -> str:
    meta = normalize_meta(getattr(game, "meta_config", {}))
    return str(first_meta_value(meta, ("Info", "Manufacturer"), ("VPSdb", "manufacturer"), default="") or "")


def game_year(game) -> str:
    meta = normalize_meta(getattr(game, "meta_config", {}))
    value = first_meta_value(meta, ("Info", "Year"), ("VPSdb", "year"), default="")
    return str(value) if value else ""


def game_rating(game) -> int:
    meta = normalize_meta(getattr(game, "meta_config", {}))
    return normalize_rating(get_meta_value(meta, "User", "Rating", 0))


def game_last_run(game) -> int:
    """When the game was last played, as the epoch integer `User.LastRun` is specced as.

    0 for a game with no play on record. Both the `played` axis and the `last_played`
    order read this one accessor, so a game the filter admits is always one the sort
    has a date to place.
    """
    meta = normalize_meta(getattr(game, "meta_config", {}))
    try:
        return int(get_meta_value(meta, "User", "LastRun", 0) or 0)
    except (TypeError, ValueError):
        return 0


def set_game_rating(game, rating: Any) -> int:
    """Write `User.Rating`, returning what was stored.

    Re-reads from disk first, so a rating set from one surface does not overwrite
    whatever another wrote to the same `.info` while this copy was held.
    """
    config = load_game_meta(game)
    get_or_create_user_meta(config)["Rating"] = normalize_rating(rating)
    persist_game_meta(game, config)
    game.meta_config = config
    return normalize_rating(rating)



def play_record(meta: Any) -> dict[str, Any]:
    """A game's play record, in the shapes a consumer wants rather than the file's.

    `User` is VPX's own section and keeps its own: LastRun an epoch integer, RunTime in
    minutes. The names match the collection sort axes, which are already the outward
    vocabulary for these.
    """
    from common.timestamps import epoch_to_iso

    user = section(meta, "User")
    return {
        "rating": int(user.get("Rating", 0) or 0),
        "favorite": bool(user.get("Favorite", 0)),
        "tags": user.get("Tags") or [],
        "last_played": epoch_to_iso(user.get("LastRun")) or None,
        "play_count": int(user.get("StartCount", 0) or 0),
        # The seconds we keep, not the minutes multiplied back up - that only ever
        # returned whole minutes, and inflated ones at that.
        "play_time_seconds": run_time_seconds(meta),
    }


def table_rating(table: dict) -> int:
    """One table's own rating, and 0 for the many that have none.

    The game's is the headline (INFO-SCHEMA section 8.1: both levels, game primary), so
    an unrated table is the normal case rather than a gap - it means "the game's rating
    stands", never "nobody liked it".
    """
    return normalize_rating((table.get("user") or {}).get("rating", 0))


def set_game_favorite(game, favorite: Any) -> bool:
    """Write `User.Favorite`, returning what was stored.

    A real boolean. The field has been in the tree since the initial checkin and
    every write until now was a zero-fill, so `0` is the only value any .info has
    ever held - and the reader coerces, so an old one still reads false.

    Re-read from disk first, for the reason `set_game_rating` gives.
    """
    stored = bool(favorite)
    config = load_game_meta(game)
    get_or_create_user_meta(config)["Favorite"] = stored
    persist_game_meta(game, config)
    game.meta_config = config
    return stored


def set_table_rating(game, filename: str, rating: Any) -> int:
    """Write one table's rating, returning what was stored.

    Re-read from disk first, for the reason `set_game_rating` gives: two surfaces write
    the same `.info`, and the one holding the older copy would otherwise win.
    """
    config = load_game_meta(game)
    get_or_create_table_user(config, filename)["rating"] = normalize_rating(rating)
    persist_game_meta(game, config)
    game.meta_config = config
    return normalize_rating(rating)


def reset_game_play_record(game) -> dict[str, Any]:
    """Put a game's counters back to nothing, leaving what was entered alone.

    Rating, favorite and tags are opinions somebody set; the counters are a record of
    what happened. Resetting is the common correction - a table launched twenty times
    while it was being tested reads as a favourite forever otherwise - and it is the
    one that needs no arithmetic from the user.
    """
    config = load_game_meta(game)
    user = get_or_create_user_meta(config)
    user["LastRun"] = None
    user["StartCount"] = 0
    user["RunTime"] = 0
    # The seconds are the record and `User.RunTime` is the minutes VPX keeps, so
    # zeroing the minutes alone leaves `run_time_seconds` answering for a reset game.
    vpinfe_section(config).pop("run_time_seconds", None)
    persist_game_meta(game, config)
    game.meta_config = config
    return play_record(config)


def reset_table_play_record(game, filename: str) -> dict[str, Any]:
    """The same, for one table's own counters."""
    config = load_game_meta(game)
    entry = get_or_create_table_user(config, filename)
    entry["last_run"] = None
    entry["start_count"] = 0
    entry["run_time_seconds"] = 0
    persist_game_meta(game, config)
    game.meta_config = config
    return {"last_played": None, "play_count": 0, "play_time_seconds": 0}


def table_play_record(table: dict) -> dict[str, Any]:
    """One table's own play record. Counters only - a rating is entered rather than
    accumulated, so it sits beside this record and not in it."""
    user = table.get("user") or {}
    return {
        "last_played": user.get("last_run") or None,
        "play_count": int(user.get("start_count", 0) or 0),
        "play_time_seconds": int(user.get("run_time_seconds", 0) or 0),
    }

def table_descriptor(table: dict, *, default_id: str = "") -> dict[str, Any]:
    """One table as both play lenses report it.

    A game folder holds several tables and each answers for itself, so this is the whole
    of what a table is on the wire rather than a few fields borrowed from its game. Built
    once here because the REST lens and the theme payload have to agree.

    The .vpx's `companyname`, `companyyear` and `playfieldvariant` are deliberately absent.
    Measured across 162 real tables they are populated in **none** of them - authors fill
    in the filename, the version and the release date, and leave VPX's company fields
    alone. The first two would also duplicate the game's, which VPSdb does populate, and
    `playfieldvariant` is a rendering mode rather than SS/EM, so publishing it as `type`
    beside the game's `type` would put two unrelated meanings behind one word.
    """
    def parsed(key):
        """Null rather than "" so "not parsed" is distinct from "parsed as blank"."""
        return str(table.get(key, "") or "").strip() or None

    return {
        "id": str(table.get(TABLE_ID_KEY, "") or ""),
        "filename": entry_filename(table),
        "version": str(table.get("version", "") or ""),
        "rom": str(table.get("rom", "") or ""),
        # The sha256 of the .vpx. What lets two installs sharing a filesystem agree they
        # hold the same file without comparing paths, which differ by mount point.
        "file_hash": str(table.get("file_hash", "") or ""),
        "default": bool(default_id) and table.get(TABLE_ID_KEY) == default_id,
        "hidden": table.get("hidden") is True,
        # Top level, where the game's rating is too, so the two lenses read alike.
        "rating": table_rating(table),
        "release_date": parsed("release_date"),
        "authors": table.get("authors") or [],
        "detects": {key.removeprefix("detect_"): bool(table.get(key, False))
                    for key in DETECTION_KEYS},
        "user": table_play_record(table),
    }


def game_frontend_dof_event(game) -> str:
    """The DOF effect a game asks for when selected, or "" to use the default."""
    meta = normalize_meta(getattr(game, "meta_config", {}))
    return str(vpinfe_section(meta).get("frontend_dof_event", "") or "").strip()


def game_vps_id(game) -> str:
    meta = normalize_meta(getattr(game, "meta_config", {}))
    alt_vpsid = str(vpinfe_section(meta).get("alt_vpsid", "") or "").strip()
    if alt_vpsid:
        return alt_vpsid
    return str(section(meta, "Info").get("VPSId", "") or "").strip()


def base_game_vps_id(game) -> str:
    return str(section(getattr(game, "meta_config", {}), "Info").get("VPSId", "") or "").strip()


def get_or_create_user_meta(config: dict[str, Any]) -> dict[str, Any]:
    user = config.setdefault("User", {})
    user.setdefault("Rating", 0)
    user.setdefault("Favorite", False)
    user.setdefault("LastRun", None)
    user.setdefault("StartCount", 0)
    user.setdefault("RunTime", 0)
    user.setdefault("Tags", [])
    return user


def run_time_seconds(meta: Any) -> int:
    """The play time recorded against a game, in seconds.

    Seeded from `User.RunTime` for a game last played before the seconds were kept, so
    an existing library carries its history forward instead of restarting at nothing.
    """
    vpinfe = vpinfe_section(meta)
    if "run_time_seconds" in vpinfe:
        return _as_int(vpinfe.get("run_time_seconds"))
    return _as_int(section(meta, "User").get("RunTime")) * 60


def _as_int(value, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def get_or_create_vpinfe_meta(config: dict[str, Any]) -> dict[str, Any]:
    """The section VPinFE owns, to write into. `vpinfe_section` normalizes and may copy,
    so it reads but does not write."""
    return config.setdefault(VPINFE_SECTION, {})


def get_or_create_table_user(config: dict[str, Any], filename: str) -> dict[str, Any]:
    """One table's play record, created on its first launch.

    The counters are written here; `rating` is written by `set_table_rating` and is the
    only entered value in the block. Favorite is still in the design with no producer,
    and storing a field nothing fills invites a reader to trust it.
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


def load_game_meta(game) -> dict[str, Any]:
    meta_path = meta_file_path(game)
    if meta_path.exists():
        return normalize_meta(MetaConfig(str(meta_path)).data)
    return normalize_meta(getattr(game, "meta_config", {}))


def persist_game_meta(game, config: dict[str, Any]) -> None:
    meta_file = MetaConfig(str(meta_file_path(game)))
    upgraded = meta_file.pending_migration
    meta_file.data = config
    meta_file.write_config()
    game.meta_config = config
    # Both flags were read during the scan, and this write is what makes them wrong.
    # Nothing is pending once the file is on disk, and an upgrade has just left a
    # restore point behind it. Without this the id backfill upgrades the whole library
    # at startup and every loaded game still claims it needs upgrading - which is what
    # the Manager UI then reports, for as long as the process lives.
    game.info_pending_upgrade = False
    if upgraded:
        game.info_restorable = True
