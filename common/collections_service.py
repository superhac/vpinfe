from __future__ import annotations

from pathlib import Path
from urllib.parse import quote

from common.paths import COLLECTIONS_PATH
from common.tablelistfilters import TableListFilters
from common.table_metadata import is_truthy
from common.vpxcollections import VPXCollections

COLLECTION_ICONS_DIR = COLLECTIONS_PATH.parent / "collection_icons"
COLLECTION_IMAGE_KEY = "image"


def get_collections_manager() -> VPXCollections:
    return VPXCollections(str(COLLECTIONS_PATH))


def ensure_collection_icons_dir() -> Path:
    COLLECTION_ICONS_DIR.mkdir(parents=True, exist_ok=True)
    return COLLECTION_ICONS_DIR


def get_collection_names() -> list[str]:
    return get_collections_manager().get_collections_name()


def collection_icon_url(filename: str | None) -> str:
    filename = Path(filename or "").name.strip()
    if not filename:
        return ""
    return f"/collection_icons/{quote(filename)}"


def get_collection_image(collection: str) -> str:
    manager = get_collections_manager()
    if collection not in manager.config:
        return ""
    return manager.config[collection].get(COLLECTION_IMAGE_KEY, "").strip()


def get_collection_image_url(collection: str) -> str:
    return collection_icon_url(get_collection_image(collection))


def get_collections_metadata() -> list[dict]:
    manager = get_collections_manager()
    rows = []
    for name in manager.get_collections_name():
        is_filter = manager.is_filter_based(name)
        image = manager.config[name].get(COLLECTION_IMAGE_KEY, "").strip()
        rows.append({
            "name": name,
            "type": "filter" if is_filter else "vpsid",
            "is_filter": is_filter,
            "image": image,
            "image_url": collection_icon_url(image),
            "table_count": None if is_filter else len(manager.get_vpsids(name)),
        })
    return rows


def filter_tables_by_collection(tables, collection: str):
    manager = get_collections_manager()
    if manager.is_filter_based(collection):
        filters = manager.get_filters(collection)
        filtered = TableListFilters(tables).apply_filters(
            letter=filters["letter"],
            theme=filters["theme"],
            table_type=filters["table_type"],
            manufacturer=filters["manufacturer"],
            year=filters["year"],
            rating=filters.get("rating", "All"),
            rating_or_higher=filters.get("rating_or_higher", "false"),
        )
        return filtered, filters
    return manager.filter_tables(tables, collection), None


def save_filter_collection(
    name: str,
    letter: str = "All",
    theme: str = "All",
    table_type: str = "All",
    manufacturer: str = "All",
    year: str = "All",
    rating: str = "All",
    rating_or_higher=False,
    sort_by: str = "Alpha",
) -> None:
    manager = get_collections_manager()
    manager.add_filter_collection(
        name,
        letter,
        theme,
        table_type,
        manufacturer,
        year,
        rating,
        "true" if is_truthy(rating_or_higher) else "false",
        sort_by,
    )
    manager.save()
