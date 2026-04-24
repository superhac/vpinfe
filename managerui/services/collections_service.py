from __future__ import annotations

from typing import Dict, List

from common.table_repository import get_table_rows
from common.vpxcollections import VPXCollections

from managerui.paths import COLLECTIONS_PATH


def get_collections_manager() -> VPXCollections:
    return VPXCollections(str(COLLECTIONS_PATH))


def get_table_rows_for_collections(cached_tables: list[dict] | None = None) -> list[dict]:
    return cached_tables if cached_tables is not None else get_table_rows(reload=False)


def get_table_name_map(cached_tables: list[dict] | None = None) -> Dict[str, str]:
    tables = get_table_rows_for_collections(cached_tables)
    return {table.get("id"): table.get("name", table.get("id")) for table in tables if table.get("id")}


def vpsid_to_name(vpsid: str, table_map: Dict[str, str] | None = None) -> str:
    if table_map is None:
        table_map = get_table_name_map()
    return table_map.get(vpsid, vpsid)


def get_filter_options(cached_tables: list[dict] | None = None) -> Dict[str, List[str]]:
    tables = get_table_rows_for_collections(cached_tables)

    if not tables:
        return {
            "letters": ["All"],
            "themes": ["All"],
            "types": ["All"],
            "manufacturers": ["All"],
            "years": ["All"],
            "ratings": ["All", "1", "2", "3", "4", "5"],
            "sort_options": ["Alpha", "Newest", "LastRun", "Highest StartCount"],
        }

    letters = set()
    themes = set()
    types = set()
    manufacturers = set()
    years = set()

    for table in tables:
        name = table.get("name", "")
        if name:
            first_char = name[0].upper()
            if first_char.isalnum():
                letters.add(first_char)

        table_type = table.get("type", "")
        if table_type:
            types.add(table_type)

        manufacturer = table.get("manufacturer", "")
        if manufacturer:
            manufacturers.add(manufacturer)

        year = table.get("year", "")
        if year:
            years.add(str(year))

        table_themes = table.get("themes", [])
        if isinstance(table_themes, list):
            themes.update(table_themes)
        elif table_themes:
            themes.add(table_themes)

    return {
        "letters": ["All"] + sorted(letters),
        "themes": ["All"] + sorted(themes),
        "types": ["All"] + sorted(types),
        "manufacturers": ["All"] + sorted(manufacturers),
        "years": ["All"] + sorted(years),
        "ratings": ["All", "1", "2", "3", "4", "5"],
        "sort_options": ["Alpha", "Newest", "LastRun", "Highest StartCount"],
    }


def delete_collection(name: str) -> None:
    manager = get_collections_manager()
    manager.delete_collection(name)
    manager.save()


def rename_collection(name: str, new_name: str) -> None:
    manager = get_collections_manager()
    manager.rename_collection(name, new_name)
    manager.save()


def create_vpsid_collection(name: str, vpsids: list[str]) -> None:
    manager = get_collections_manager()
    manager.add_collection(name, vpsids)
    manager.save()


def create_filter_collection(name: str, **filters) -> None:
    manager = get_collections_manager()
    manager.add_filter_collection(name, **filters)
    manager.save()


def update_filter_collection(name: str, **filters) -> None:
    manager = get_collections_manager()
    for key, value in filters.items():
        manager.config[name][key] = value
    manager.save()


def update_vpsid_collection(name: str, vpsids: list[str]) -> None:
    manager = get_collections_manager()
    manager.config[name]["vpsids"] = ",".join(vpsids)
    manager.save()


def search_tables(term: str, cached_tables: list[dict] | None = None, limit: int = 20) -> list[dict]:
    term = (term or "").strip().lower()
    if not term:
        return []
    return [
        table for table in get_table_rows_for_collections(cached_tables)
        if term in (table.get("name") or "").lower()
    ][:limit]
