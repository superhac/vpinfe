from __future__ import annotations

import json
import logging

from common.collections_service import filter_tables_by_collection, get_collection_names, save_filter_collection
from common.media_paths import table_media_payload
from common.tablelistfilters import TableListFilters
from common.table_metadata import (
    DETECTION_KEYS,
    get_or_create_user_meta,
    load_table_meta,
    normalize_meta,
    normalize_rating,
    persist_table_meta,
    section,
    table_title,
)


logger = logging.getLogger("vpinfe.frontend.table_state")


def default_filter_state():
    return {
        "letter": None,
        "theme": None,
        "type": None,
        "manufacturer": None,
        "year": None,
        "rating": None,
        "rating_or_higher": False,
    }


def default_sort_order(sort_type):
    return "Descending"


def normalize_sort_order(order_by, sort_type="Alpha"):
    value = str(order_by or "").strip().lower()
    if value in ("ascending", "asc"):
        return "Ascending"
    if value in ("descending", "desc"):
        return "Descending"
    return default_sort_order(sort_type)


def _to_bool(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() == "true"
    return value == 1


def tables_json(tables) -> str:
    result = []
    for table in tables:
        meta = normalize_meta(table.metaConfig)

        vpinfe = section(meta, "VPinFE")
        info = section(meta, "Info")
        if str(vpinfe.get("altvpsid", "") or "").strip() and str(vpinfe.get("alttitle", "") or "").strip():
            info["Title"] = str(vpinfe.get("alttitle", "") or "").strip()
            meta["Info"] = info

        vpx = section(meta, "VPXFile")
        for key in DETECTION_KEYS:
            vpx[key] = _to_bool(vpx.get(key, False))
        vpx["altSoundExists"] = bool(table.altSoundExists)
        vpx["altColorExists"] = bool(table.altColorExists)
        vpx["pupPackExists"] = bool(table.pupPackExists)

        row = {
            "tableDirName": table.tableDirName,
            "fullPathTable": table.fullPathTable,
            "fullPathVPXfile": table.fullPathVPXfile,
            "pupPackExists": table.pupPackExists,
            "altColorExists": table.altColorExists,
            "altSoundExists": table.altSoundExists,
            "meta": meta,
        }
        row.update(table_media_payload(table))
        result.append(row)
    return json.dumps(result)


def apply_collection(api, collection):
    api.current_collection = collection
    filtered, filters = filter_tables_by_collection(api.allTables, collection)
    api.filteredTables = filtered
    if filters is None:
        api.current_filters = default_filter_state()
        return

    api.current_filters = {
        "letter": filters["letter"],
        "theme": filters["theme"],
        "type": filters["table_type"],
        "manufacturer": filters["manufacturer"],
        "year": filters["year"],
        "rating": filters.get("rating", "All"),
        "rating_or_higher": str(filters.get("rating_or_higher", "false")).lower() in ("1", "true", "yes", "on"),
    }
    api.current_sort = filters["sort_by"]
    api.current_order = normalize_sort_order(filters.get("order_by"), filters["sort_by"])
    api.apply_sort(filters["sort_by"], api.current_order)


def save_current_filter_collection(api, name, letter, theme, table_type, manufacturer, year, sort_by, rating, rating_or_higher, order_by="Descending"):
    save_filter_collection(name, letter, theme, table_type, manufacturer, year, rating, rating_or_higher, sort_by, order_by)
    return {"success": True, "message": f"Filter collection '{name}' saved successfully"}


def filter_options(tables):
    filters = TableListFilters(tables)
    return {
        "letters": filters.get_available_letters(),
        "themes": filters.get_available_themes(),
        "types": filters.get_available_types(),
        "manufacturers": filters.get_available_manufacturers(),
        "years": filters.get_available_years(),
    }


def apply_filters(api, letter=None, theme=None, table_type=None, manufacturer=None, year=None, rating=None, rating_or_higher=None):
    api.current_collection = None
    updates = {
        "letter": letter,
        "theme": theme,
        "type": table_type,
        "manufacturer": manufacturer,
        "year": year,
        "rating": rating,
    }
    for key, value in updates.items():
        if value is not None:
            api.current_filters[key] = value
    if rating_or_higher is not None:
        api.current_filters["rating_or_higher"] = str(rating_or_higher).strip().lower() in ("1", "true", "yes", "on")

    api.filteredTables = TableListFilters(api.allTables).apply_filters(
        letter=api.current_filters["letter"],
        theme=api.current_filters["theme"],
        table_type=api.current_filters["type"],
        manufacturer=api.current_filters["manufacturer"],
        year=api.current_filters["year"],
        rating=api.current_filters["rating"],
        rating_or_higher=api.current_filters["rating_or_higher"],
    )
    return len(api.filteredTables)


def apply_sort(tables, sort_type, order_by=None):
    reverse = normalize_sort_order(order_by, sort_type) == "Descending"
    if sort_type == "Alpha":
        tables.sort(key=lambda table: table_title(table).lower(), reverse=reverse)
    elif sort_type == "Newest":
        tables.sort(key=lambda table: table_title(table).lower())
        tables.sort(key=lambda table: table.creation_time if table.creation_time is not None else 0, reverse=reverse)
    elif sort_type == "LastRun":
        _sort_by_numeric_meta(tables, "LastRun", reverse)
    elif sort_type == "Highest StartCount":
        _sort_by_numeric_meta(tables, "StartCount", reverse)
    elif sort_type == "RunTime":
        _sort_by_numeric_meta(tables, "RunTime", reverse)
    return len(tables)


def _sort_by_numeric_meta(tables, field, reverse):
    tables.sort(key=lambda table: table_title(table).lower())
    tables.sort(key=lambda table: _numeric_meta_value(table, field), reverse=reverse)


def _numeric_meta_value(table, field):
    meta = normalize_meta(getattr(table, "metaConfig", {}))
    user = section(meta, "User")
    info = section(meta, "Info")
    try:
        value = int(user.get(field, info.get(field, -1 if field == "LastRun" else 0)))
    except (TypeError, ValueError):
        value = -1 if field == "LastRun" else 0
    return value


def get_table_rating(tables, index):
    try:
        table = tables[index]
    except Exception:
        return 0
    return normalize_rating(section(load_table_meta(table), "User").get("Rating", 0))


def set_table_rating(tables, index, rating):
    table = tables[index]
    config = load_table_meta(table)
    user = get_or_create_user_meta(config)
    normalized = normalize_rating(rating)
    user["Rating"] = normalized
    persist_table_meta(table, config)
    return {"success": True, "rating": normalized}
