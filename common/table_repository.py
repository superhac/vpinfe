from __future__ import annotations

import logging
import threading
from time import perf_counter
from typing import Any, Dict, List, Optional

from pathlib import Path

from common.paths import COLLECTIONS_PATH, get_ini_config, get_tables_path
from common.table_metadata import first_meta_value, normalize_rating, section
from common.tableparser import TableParser
from common.vpxcollections import VPXCollections


_LOCK = threading.Lock()
_PARSER: Optional[TableParser] = None
logger = logging.getLogger("vpinfe.common.table_repository")


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


def _collections_map() -> Dict[str, List[str]]:
    mapping: Dict[str, List[str]] = {}
    try:
        collections = VPXCollections(str(COLLECTIONS_PATH))
        for collection_name in collections.get_collections_name():
            if collections.is_filter_based(collection_name):
                continue
            try:
                for vpsid in collections.get_vpsids(collection_name):
                    mapping.setdefault(vpsid, []).append(collection_name)
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
    effective_id = first_meta_value(meta, ("VPinFE", "altvpsid"), ("Info", "VPSId"), default="")
    row = {
        "name": (first_meta_value(meta, ("VPinFE", "alttitle"), ("Info", "Title"), default=table_name) or "").strip(),
        "filename": first_meta_value(meta, ("VPXFile", "filename"), default=Path(table.fullPathVPXfile).name),
        "vpsid": vpsid,
        "id": effective_id or vpsid,
        "ipdb_id": first_meta_value(meta, ("Info", "IPDBId")),
        "pinball_primer_tut": first_meta_value(meta, ("Info", "PinballPrimerTut")),
        "manufacturer": first_meta_value(meta, ("Info", "Manufacturer"), ("VPXFile", "manufacturer")),
        "year": first_meta_value(meta, ("Info", "Year"), ("VPXFile", "year")),
        "type": first_meta_value(meta, ("Info", "Type"), ("VPXFile", "type")),
        "themes": first_meta_value(meta, ("Info", "Themes"), default=[]),
        "authors": first_meta_value(meta, ("Info", "Authors"), default=[]),
        "rom": first_meta_value(meta, ("VPXFile", "rom"), ("Info", "Rom")),
        "version": first_meta_value(meta, ("VPXFile", "version")),
        "filehash": first_meta_value(meta, ("VPXFile", "filehash")),
        "vbshash": first_meta_value(meta, ("VPXFile", "vbsHash")),
        "detectnfozzy": first_meta_value(meta, ("VPXFile", "detectnfozzy")),
        "detectfleep": first_meta_value(meta, ("VPXFile", "detectfleep")),
        "detectssf": first_meta_value(meta, ("VPXFile", "detectssf")),
        "detectlut": first_meta_value(meta, ("VPXFile", "detectlut")),
        "detectscorebit": first_meta_value(meta, ("VPXFile", "detectscorebit")),
        "detectfastflips": first_meta_value(meta, ("VPXFile", "detectfastflips")),
        "detectflex": first_meta_value(meta, ("VPXFile", "detectflex")),
        "patch_applied": first_meta_value(meta, ("VPXFile", "patch_applied"), default=False),
        "table_path": table.fullPathTable,
        "pup_pack_exists": bool(getattr(table, "pupPackExists", False)),
        "serum_exists": bool(getattr(table, "altColorExists", False)),
        "vni_exists": bool(getattr(table, "vniExists", False)),
        "alt_sound_exists": bool(getattr(table, "altSoundExists", False)),
        "delete_nvram_on_close": vpinfe.get("deletedNVRamOnClose", False),
        "altlauncher": str(vpinfe.get("altlauncher", "") or "").strip(),
        "alttitle": str(vpinfe.get("alttitle", "") or "").strip(),
        "altvpsid": str(vpinfe.get("altvpsid", "") or "").strip(),
        "frontend_dof_event": str(user.get("FrontendDOFEvent", "") or "").strip(),
        "rating": normalize_rating(user.get("Rating", 0)),
        "collections": [],
    }
    if collections_map is not None:
        row["collections"] = collections_map.get(row.get("id", ""), [])
    return row


def get_table_rows(reload: bool = False) -> List[Dict[str, Any]]:
    tables = ensure_tables_loaded(reload=reload)
    collections_map = _collections_map()
    rows = [table_to_row(table, collections_map) for table in tables]
    rows.sort(key=lambda row: (row.get("name") or "").lower())
    return rows


def get_table_name_map(reload: bool = False) -> Dict[str, str]:
    return {
        row.get("id"): row.get("name", row.get("id"))
        for row in get_table_rows(reload=reload)
        if row.get("id")
    }
