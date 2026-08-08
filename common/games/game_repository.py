"""The library, held once and shared.

Every page and endpoint reads games from here rather than re-scanning, which is what
five callers each used to do. Re-reading a game replaces the object, so anything
holding the old one is stale - `game.changed` is announced for that reason.
"""

from __future__ import annotations

import logging
import threading
from pathlib import Path
from time import perf_counter
from typing import Any

from common import events
from common.games.collection_store import CollectionStore
from common.games.game_identity import ensure_unique_ids
from common.games.game_identity import game_id as vpinfe_id
from common.games.game_metadata import (
    as_string_list,
    default_table,
    first_meta_value,
    normalize_rating,
    reorder_leading_article,
    section,
    vpinfe_section,
)
from common.games.game_parser import GameParser
from common.games.info_migration import INFO_SCHEMA, schema_of
from common.paths import COLLECTIONS_PATH, get_games_path, get_ini_config

_LOCK = threading.Lock()
_PARSER: GameParser | None = None
logger = logging.getLogger("vpinfe.common.games.game_repository")


def ensure_games_loaded(reload: bool = False) -> list[Any]:
    global _PARSER
    started_at = perf_counter()
    with _LOCK:
        games_root = get_games_path()
        needs_new_parser = _PARSER is None or str(_PARSER.gamesRootFilePath) != games_root
        if needs_new_parser:
            _PARSER = GameParser(games_root, get_ini_config())
        elif reload:
            _PARSER.loadGames(reload=True)
        games = list(_PARSER.getAllGames())

    elapsed = perf_counter() - started_at
    logger.debug(
        "ensure_games_loaded reload=%s count=%s elapsed=%.3fs",
        reload,
        len(games),
        elapsed,
    )
    return games


def games_under(games_root: str, config=None) -> list[Any]:
    """The library at `games_root`, from the cache when that is the configured one.

    Five callers built a parser of their own and rescanned everything, which on a network
    share was the whole cold scan again each time. Most of them want the library the app
    already has; they just could not say so without assuming the root.

    A root that is not the configured one is genuinely a different library - a report run
    against another folder, a test - so it gets its own parse rather than quietly being
    answered with the wrong games.
    """
    wanted = str(games_root or "").strip()
    if not wanted or wanted == get_games_path():
        return ensure_games_loaded()
    return list(GameParser(wanted, config or get_ini_config()).getAllGames())


def refresh_games() -> list[Any]:
    return ensure_games_loaded(reload=True)


def info_maintenance_counts(reload: bool = False) -> dict[str, int]:
    """How many games could be upgraded, and how many have something to restore.

    Off the loaded library, which already read every .info and listed every folder.
    """
    games = ensure_games_loaded(reload=reload)
    return {
        "pending_upgrade": sum(1 for t in games if getattr(t, "info_pending_upgrade", False)),
        "restorable": sum(1 for t in games if getattr(t, "info_restorable", False)),
        # Written by a build newer than this one. Without this the page cannot tell "I
        # upgraded these" from "something newer did, and I cannot fully read them" - and
        # says the first, which is a lie the moment a schema 3 exists.
        "newer_than_us": sum(1 for t in games
                             if (schema_of(t.meta_config) or 0) > INFO_SCHEMA),
    }


def unreadable_games() -> list[dict[str, str]]:
    """Folders whose .info could not be read, so the game was left out of the library."""
    ensure_games_loaded()
    with _LOCK:
        if _PARSER is None:
            return []
        return [dict(row) for row in _PARSER.getUnreadableGames()]


def pending_upgrade_game_names() -> list[str]:
    """Folders whose .info the upgrade did not reach, for the list its dialog shows."""
    return sorted(
        (t.gameDirName for t in ensure_games_loaded()
         if getattr(t, "info_pending_upgrade", False)),
        key=str.lower,
    )


def newest_backup_stamp() -> str:
    """The most recent backup timestamp in the library, or ""."""
    stamps = [s for s in (getattr(t, "info_backup_stamp", "")
                          for t in ensure_games_loaded()) if s]
    return max(stamps) if stamps else ""


def restorable_game_names() -> list[str]:
    """Folders holding a saved copy of their .info, for the list a restore dialog shows."""
    return sorted(
        (t.gameDirName for t in ensure_games_loaded() if getattr(t, "info_restorable", False)),
        key=str.lower,
    )


def refresh_game(game_path: str) -> list[Any]:
    """Re-read one game folder, not the library.

    The whole-library reload this used to do is why setting a star rating on a big
    network share took minutes: every caller changes one folder and then paid to look
    at all of them.
    """
    normalized = str(Path(game_path).expanduser().resolve())
    started_at = perf_counter()
    with _LOCK:
        if _PARSER is None or not _PARSER.getGameCount():
            reloaded = None
        else:
            reloaded = _PARSER.reload_game(normalized)
            games = list(_PARSER.getAllGames())
    if reloaded is None:
        # Nothing loaded yet, so there is no single game to refresh - read the library.
        games = ensure_games_loaded(reload=True)

    logger.debug("refresh_game %s elapsed=%.3fs", normalized, perf_counter() - started_at)
    found = [game for game in games if str(Path(game.fullPathGame).resolve()) == normalized]

    # Announced here rather than at each caller: every path that changes one game already
    # comes through this to be re-read, so a new one cannot forget to say so.
    events.emit(events.GAME_CHANGED, game=found[0] if found else None, path=normalized)
    return found


def get_missing_games(reload: bool = False) -> list[dict[str, str]]:
    ensure_games_loaded(reload=reload)
    with _LOCK:
        if _PARSER is None:
            return []
        return [dict(row) for row in _PARSER.getMissingGames()]


def collections_by_game_id() -> dict[str, list[str]]:
    """Collection names keyed by the game id membership is recorded under.

    Only explicit-membership collections. A filter collection has no member list to
    key on - what belongs to it is decided per game when it is displayed.
    """
    mapping: dict[str, list[str]] = {}
    try:
        collections = CollectionStore(str(COLLECTIONS_PATH))
        for collection_name in collections.get_collections_name():
            if collections.is_filter_based(collection_name):
                continue
            try:
                for member_id in collections.get_members(collection_name):
                    mapping.setdefault(member_id, []).append(collection_name)
            except Exception:
                pass
    except Exception:
        pass
    return mapping


def game_to_row(game, collections_map: dict[str, list[str]] | None = None) -> dict[str, Any]:
    meta = game.meta_config or {}
    user = section(meta, "User")
    vpinfe = vpinfe_section(meta)
    game_name = Path(game.fullPathGame).name
    vpsid = first_meta_value(meta, ("Info", "VPSId"), default="")
    # The row describes one table - the game's default. A folder can hold several,
    # and the API lists them all separately; this is what the game-level views show.
    gf_name, gf = default_table(meta, folder_name=game_name)

    def gf_value(key, default=""):
        value = gf.get(key, None)
        return default if value in ("", None) else value

    row = {
        "name": (str(vpinfe.get("alt_title", "") or "").strip()
                 or reorder_leading_article(first_meta_value(meta, ("Info", "Title"), default=game_name) or "")),
        "filename": gf_name or Path(game.fullPathVPXfile).name,
        # vpsid and alt_vpsid correlate with VPSdb, VPinPlay and anything else keyed
        # by them. vpinfe_id is this install's own id (common/games/game_identity.py)
        # and is what identifies the game here - in the API, in events, in collection
        # membership. Empty until the game has been assigned one; reading never mints.
        "vpsid": vpsid,
        "vpinfe_id": vpinfe_id(game),
        "ipdb_id": first_meta_value(meta, ("Info", "IPDBId")),
        "pinball_primer_tut": first_meta_value(meta, ("Info", "PinballPrimerTut")),
        # Info carries what VPS knows; the table's own claim is the fallback and can
        # legitimately differ from it.
        "manufacturer": first_meta_value(meta, ("Info", "Manufacturer")) or gf_value("manufacturer"),
        "year": first_meta_value(meta, ("Info", "Year")) or gf_value("year"),
        "type": first_meta_value(meta, ("Info", "Type")) or gf_value("type"),
        "themes": as_string_list(first_meta_value(meta, ("Info", "Themes"), default=[])),
        # Authors are per table, never rolled up: multi-table folders often
        # name different authors in different ones.
        "authors": as_string_list(gf_value("authors", [])),
        "rom": gf_value("rom"),
        "version": gf_value("version"),
        "filehash": gf_value("file_hash"),
        "vbshash": gf_value("vbs_hash"),
        "detectnfozzy": gf_value("detect_nfozzy"),
        "detectfleep": gf_value("detect_fleep"),
        "detectssf": gf_value("detect_ssf"),
        "detectlut": gf_value("detect_lut"),
        "detectscorebit": gf_value("detect_scorbit"),
        "detectfastflips": gf_value("detect_fastflips"),
        "detectflex": gf_value("detect_flex"),
        "detectpinmame": gf_value("detect_pinmame"),
        "patch_applied": gf_value("patch_applied", False),
        "table_path": game.fullPathGame,
        "b2s_exists": bool(getattr(game, "b2sExists", False)),
        "pup_pack_exists": bool(getattr(game, "pupPackExists", False)),
        "serum_exists": bool(getattr(game, "altColorExists", False)),
        "vni_exists": bool(getattr(game, "vniExists", False)),
        "alt_sound_exists": bool(getattr(game, "altSoundExists", False)),
        "ini_exists": bool(getattr(game, "iniExists", False)),
        "music_exists": bool(getattr(game, "musicExists", False)),
        "delete_nvram_on_close": vpinfe.get("delete_nvram_on_close", False),
        "alt_launcher": str(vpinfe.get("alt_launcher", "") or "").strip(),
        "plugin_profile": str(vpinfe.get("plugin_profile", "") or "").strip(),
        "alt_title": str(vpinfe.get("alt_title", "") or "").strip(),
        "alt_vpsid": str(vpinfe.get("alt_vpsid", "") or "").strip(),
        "frontend_dof_event": str(vpinfe.get("frontend_dof_event", "") or "").strip(),
        "rating": normalize_rating(user.get("Rating", 0)),
        "collections": [],
    }
    if collections_map is not None:
        row["collections"] = _collections_for(row, collections_map)
    return row


def _collections_for(row: dict[str, Any], collections_map: dict[str, list[str]]) -> list[str]:
    """Which collections a row belongs to, tolerating entries not yet migrated.

    Matches CollectionStore.is_member. The migration leaves an entry alone when no
    game matched it - the game may simply not be installed yet - and it only runs
    once, so an entry can stay VPS-keyed indefinitely. Without the fallbacks the
    frontend would show that membership and the Manager UI would not.
    """
    for key in (row.get("vpinfe_id"), row.get("alt_vpsid"), row.get("vpsid")):
        if key and key in collections_map:
            return collections_map[key]
    return []


def get_game_rows(reload: bool = False) -> list[dict[str, Any]]:
    # A row is addressed by its game id, so every row has to have one - a game
    # imported since startup would otherwise carry an empty id and collide with
    # every other game that has none. Already-assigned libraries pay nothing:
    # this only touches disk for a game that has no id yet.
    games = ensure_unique_ids(ensure_games_loaded(reload=reload)).values()
    collections_map = collections_by_game_id()
    rows = [game_to_row(game, collections_map) for game in games]
    rows.sort(key=lambda row: (row.get("name") or "").lower())
    return rows


def get_game_name_map(reload: bool = False) -> dict[str, str]:
    """Display names keyed by game id, for showing what is in a collection."""
    return {
        row["vpinfe_id"]: row.get("name") or row["vpinfe_id"]
        for row in get_game_rows(reload=reload)
        if row.get("vpinfe_id")
    }
