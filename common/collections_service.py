from __future__ import annotations

from common.paths import COLLECTIONS_PATH
from common.tablelistfilters import TableListFilters
from common.table_metadata import is_truthy
from common.vpxcollections import VPXCollections


def get_collections_manager() -> VPXCollections:
    return VPXCollections(str(COLLECTIONS_PATH))


def get_collection_names() -> list[str]:
    return get_collections_manager().get_collections_name()


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
