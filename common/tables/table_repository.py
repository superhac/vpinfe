from __future__ import annotations

import logging
import threading
from time import perf_counter
from typing import Any, Dict, List, Optional

from pathlib import Path

from common.paths import COLLECTIONS_PATH, get_ini_config, get_tables_path
from common.tables.table_identity import ensure_unique_ids
from common.tables.table_identity import table_id as vpinfe_id
from common.tables.table_metadata import (
    as_string_list,
    default_game_file,
    first_meta_value,
    normalize_rating,
    reorder_leading_article,
    section,
)
from common.tables.tableparser import TableParser
from common.tables.vpxcollections import VPXCollections


_LOCK = threading.Lock()
_PARSER: Optional[TableParser] = None
logger = logging.getLogger("vpinfe.common.tables.table_repository")


def ensure_tables_loaded(reload: bool = False) -> List[Any]:
    global _PARSER
    started_at = perf_counter()
    with _LOCK:
        tables_root = get_tables_path()
        needs_new_parser = _PARSER is None or str(_PARSER.tablesRootFilePath) != tables_root
        if needs_new_parser:
            _PARSER = TableParser(tables_root, get_ini_config())
        elif reload:
            _PARSER.loadTables(reload=True)
        tables = list(_PARSER.getAllTables())

    elapsed = perf_counter() - started_at
    logger.debug(
        "ensure_tables_loaded reload=%s count=%s elapsed=%.3fs",
        reload,
        len(tables),
        elapsed,
    )
    return tables


def refresh_tables() -> List[Any]:
    return ensure_tables_loaded(reload=True)


def refresh_table(table_path: str) -> List[Any]:
    normalized = str(Path(table_path).expanduser().resolve())
    tables = refresh_tables()
    return [table for table in tables if str(Path(table.fullPathTable).resolve()) == normalized]


def get_missing_tables(reload: bool = False) -> List[Dict[str, str]]:
    ensure_tables_loaded(reload=reload)
    with _LOCK:
        if _PARSER is None:
            return []
        return [dict(row) for row in _PARSER.getMissingTables()]


def collections_by_table_id() -> Dict[str, List[str]]:
    """Collection names keyed by the table id membership is recorded under.

    Only explicit-membership collections. A filter collection has no member list to
    key on - what belongs to it is decided per table when it is displayed.
    """
    mapping: Dict[str, List[str]] = {}
    try:
        collections = VPXCollections(str(COLLECTIONS_PATH))
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


def table_to_row(table, collections_map: Optional[Dict[str, List[str]]] = None) -> Dict[str, Any]:
    meta = table.metaConfig or {}
    info = section(meta, "Info")
    user = section(meta, "User")
    vpinfe = section(meta, "VPinFE")
    table_name = Path(table.fullPathTable).name
    vpsid = first_meta_value(meta, ("Info", "VPSId"), default="")
    # The row describes one game file - the table's default. A folder can hold several,
    # and the API lists them all separately; this is what the table-level views show.
    gf_name, gf = default_game_file(meta, folder_name=table_name)

    def gf_value(key, default=""):
        value = gf.get(key, None)
        return default if value in ("", None) else value

    row = {
        "name": (str(vpinfe.get("alt_title", "") or "").strip()
                 or reorder_leading_article(first_meta_value(meta, ("Info", "Title"), default=table_name) or "")),
        "filename": gf_name or Path(table.fullPathVPXfile).name,
        # vpsid and altvpsid correlate with VPSdb, VPinPlay and anything else keyed
        # by them. vpinfe_id is this install's own id (common/table_identity.py) and
        # is what identifies the table here - in the API, in events, in collection
        # membership. Empty until the table has been assigned one; reading never mints.
        "vpsid": vpsid,
        "vpinfe_id": vpinfe_id(table),
        "ipdb_id": first_meta_value(meta, ("Info", "IPDBId")),
        "pinball_primer_tut": first_meta_value(meta, ("Info", "PinballPrimerTut")),
        # Info carries what VPS knows; the game file's own claim is the fallback and can
        # legitimately differ from it.
        "manufacturer": first_meta_value(meta, ("Info", "Manufacturer")) or gf_value("manufacturer"),
        "year": first_meta_value(meta, ("Info", "Year")) or gf_value("year"),
        "type": first_meta_value(meta, ("Info", "Type")) or gf_value("type"),
        "themes": as_string_list(first_meta_value(meta, ("Info", "Themes"), default=[])),
        # Authors are per game file, never rolled up: multi-game-file folders often
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
        "table_path": table.fullPathTable,
        "b2s_exists": bool(getattr(table, "b2sExists", False)),
        "pup_pack_exists": bool(getattr(table, "pupPackExists", False)),
        "serum_exists": bool(getattr(table, "altColorExists", False)),
        "vni_exists": bool(getattr(table, "vniExists", False)),
        "alt_sound_exists": bool(getattr(table, "altSoundExists", False)),
        "ini_exists": bool(getattr(table, "iniExists", False)),
        "music_exists": bool(getattr(table, "musicExists", False)),
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


def _collections_for(row: Dict[str, Any], collections_map: Dict[str, List[str]]) -> List[str]:
    """Which collections a row belongs to, tolerating entries not yet migrated.

    Matches VPXCollections.is_member. The migration leaves an entry alone when no
    table matched it - the table may simply not be installed yet - and it only runs
    once, so an entry can stay VPS-keyed indefinitely. Without the fallbacks the
    frontend would show that membership and the Manager UI would not.
    """
    for key in (row.get("vpinfe_id"), row.get("alt_vpsid"), row.get("vpsid")):
        if key and key in collections_map:
            return collections_map[key]
    return []


def get_table_rows(reload: bool = False) -> List[Dict[str, Any]]:
    # A row is addressed by its table id, so every row has to have one - a table
    # imported since startup would otherwise carry an empty id and collide with
    # every other table that has none. Already-assigned libraries pay nothing:
    # this only touches disk for a table that has no id yet.
    tables = ensure_unique_ids(ensure_tables_loaded(reload=reload)).values()
    collections_map = collections_by_table_id()
    rows = [table_to_row(table, collections_map) for table in tables]
    rows.sort(key=lambda row: (row.get("name") or "").lower())
    return rows


def get_table_name_map(reload: bool = False) -> Dict[str, str]:
    """Display names keyed by table id, for showing what is in a collection."""
    return {
        row["vpinfe_id"]: row.get("name") or row["vpinfe_id"]
        for row in get_table_rows(reload=reload)
        if row.get("vpinfe_id")
    }
