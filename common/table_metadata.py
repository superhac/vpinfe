from __future__ import annotations

import ast
from pathlib import Path
from typing import Any, Dict

from common.metaconfig import MetaConfig


DETECTION_KEYS = (
    "detectnfozzy",
    "detectfleep",
    "detectssf",
    "detectlut",
    "detectscorebit",
    "detectfastflips",
    "detectflex",
)


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


def normalize_rating(value: Any) -> int:
    try:
        normalized = int(float(value))
    except (TypeError, ValueError):
        normalized = 0
    return max(0, min(5, normalized))


def is_truthy(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    normalized = str(value).strip().lower()
    if normalized == "":
        return default
    return normalized in {"1", "true", "yes", "on"}


def table_title(table) -> str:
    meta = normalize_meta(getattr(table, "metaConfig", {}))
    vpinfe = section(meta, "VPinFE")
    info = section(meta, "Info")
    if str(vpinfe.get("altvpsid", "") or "").strip():
        alt_title = str(vpinfe.get("alttitle", "") or "").strip()
        if alt_title:
            return alt_title
    return str(info.get("Title", "") or get_meta_value(meta, "VPSdb", "name", "") or getattr(table, "tableDirName", "") or "").strip()


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


def table_vps_id(table) -> str:
    meta = normalize_meta(getattr(table, "metaConfig", {}))
    alt_vpsid = str(section(meta, "VPinFE").get("altvpsid", "") or "").strip()
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
    user.setdefault("FrontendDOFEvent", "")
    return user


def meta_file_path(table) -> Path:
    return Path(table.fullPathTable) / f"{table.tableDirName}.info"


def persist_table_meta(table, config: Dict[str, Any]) -> None:
    meta_file = MetaConfig(str(meta_file_path(table)))
    meta_file.data = config
    meta_file.writeConfig()
    table.metaConfig = config
