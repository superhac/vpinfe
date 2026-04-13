from __future__ import annotations

import logging
import threading
from pathlib import Path
from time import perf_counter
from typing import Any, Dict, List, Optional

from platformdirs import user_config_dir

from common.iniconfig import IniConfig
from common.tableparser import TableParser
from common.vpxcollections import VPXCollections


_LOCK = threading.Lock()
_PARSER: Optional[TableParser] = None
logger = logging.getLogger("vpinfe.common.table_repository")
_CONFIG_DIR = Path(user_config_dir("vpinfe", "vpinfe"))
_CONFIG_PATH = _CONFIG_DIR / "vpinfe.ini"
_COLLECTIONS_PATH = _CONFIG_DIR / "collections.ini"


def _get_ini_config() -> IniConfig:
    return IniConfig(str(_CONFIG_PATH))


def _get_tables_root() -> str:
    cfg = _get_ini_config()
    try:
        tableroot = cfg.config.get("Settings", "tablerootdir", fallback="").strip()
        if tableroot:
            return str(Path(tableroot).expanduser())
    except Exception:
        pass
    return str(Path("~/tables").expanduser())


def ensure_tables_loaded(reload: bool = False) -> List[Any]:
    global _PARSER
    started_at = perf_counter()
    with _LOCK:
        tables_root = _get_tables_root()
        needs_new_parser = _PARSER is None or str(_PARSER.tablesRootFilePath) != tables_root
        if needs_new_parser:
            _PARSER = TableParser(tables_root, _get_ini_config())
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


def _meta_sections(table) -> tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any], Dict[str, Any]]:
    raw = table.metaConfig or {}
    if not isinstance(raw, dict):
        raw = {}
    return (
        raw.get("Info", {}) if isinstance(raw.get("Info", {}), dict) else {},
        raw.get("VPXFile", {}) if isinstance(raw.get("VPXFile", {}), dict) else {},
        raw.get("User", {}) if isinstance(raw.get("User", {}), dict) else {},
        raw.get("VPinFE", {}) if isinstance(raw.get("VPinFE", {}), dict) else {},
    )


def _get_meta_value(info: Dict[str, Any], vpx: Dict[str, Any], user: Dict[str, Any], vpinfe: Dict[str, Any], *paths, default=""):
    sources = {
        "Info": info,
        "VPXFile": vpx,
        "User": user,
        "VPinFE": vpinfe,
    }
    for section, key in paths:
        src = sources.get(section)
        if src and key in src and src[key] not in ("", None):
            return src[key]
    return default


def _normalize_rating(value: Any) -> int:
    try:
        normalized = int(float(value))
    except (TypeError, ValueError):
        normalized = 0
    return max(0, min(5, normalized))


def _collections_map() -> Dict[str, List[str]]:
    mapping: Dict[str, List[str]] = {}
    try:
        collections = VPXCollections(str(_COLLECTIONS_PATH))
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
    info, vpx, user, vpinfe = _meta_sections(table)
    table_name = Path(table.fullPathTable).name
    vpsid = _get_meta_value(info, vpx, user, vpinfe, ("Info", "VPSId"), default="")
    effective_id = _get_meta_value(info, vpx, user, vpinfe, ("VPinFE", "altvpsid"), ("Info", "VPSId"), default="")
    row = {
        "name": (_get_meta_value(info, vpx, user, vpinfe, ("VPinFE", "alttitle"), ("Info", "Title"), default=table_name) or "").strip(),
        "filename": _get_meta_value(info, vpx, user, vpinfe, ("VPXFile", "filename"), default=Path(table.fullPathVPXfile).name),
        "vpsid": vpsid,
        "id": effective_id or vpsid,
        "ipdb_id": _get_meta_value(info, vpx, user, vpinfe, ("Info", "IPDBId")),
        "manufacturer": _get_meta_value(info, vpx, user, vpinfe, ("Info", "Manufacturer"), ("VPXFile", "manufacturer")),
        "year": _get_meta_value(info, vpx, user, vpinfe, ("Info", "Year"), ("VPXFile", "year")),
        "type": _get_meta_value(info, vpx, user, vpinfe, ("Info", "Type"), ("VPXFile", "type")),
        "themes": _get_meta_value(info, vpx, user, vpinfe, ("Info", "Themes"), default=[]),
        "authors": _get_meta_value(info, vpx, user, vpinfe, ("Info", "Authors"), default=[]),
        "rom": _get_meta_value(info, vpx, user, vpinfe, ("VPXFile", "rom"), ("Info", "Rom")),
        "version": _get_meta_value(info, vpx, user, vpinfe, ("VPXFile", "version")),
        "filehash": _get_meta_value(info, vpx, user, vpinfe, ("VPXFile", "filehash")),
        "vbshash": _get_meta_value(info, vpx, user, vpinfe, ("VPXFile", "vbsHash")),
        "detectnfozzy": _get_meta_value(info, vpx, user, vpinfe, ("VPXFile", "detectnfozzy")),
        "detectfleep": _get_meta_value(info, vpx, user, vpinfe, ("VPXFile", "detectfleep")),
        "detectssf": _get_meta_value(info, vpx, user, vpinfe, ("VPXFile", "detectssf")),
        "detectlut": _get_meta_value(info, vpx, user, vpinfe, ("VPXFile", "detectlut")),
        "detectscorebit": _get_meta_value(info, vpx, user, vpinfe, ("VPXFile", "detectscorebit")),
        "detectfastflips": _get_meta_value(info, vpx, user, vpinfe, ("VPXFile", "detectfastflips")),
        "detectflex": _get_meta_value(info, vpx, user, vpinfe, ("VPXFile", "detectflex")),
        "patch_applied": _get_meta_value(info, vpx, user, vpinfe, ("VPXFile", "patch_applied"), default=False),
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
        "rating": _normalize_rating(user.get("Rating", 0)),
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
