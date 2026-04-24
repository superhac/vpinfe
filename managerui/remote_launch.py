from __future__ import annotations

import logging

from common.vpxcollections import VPXCollections

from managerui.paths import COLLECTIONS_PATH
from managerui.services import table_catalog


logger = logging.getLogger("vpinfe.manager.remote_launch")


def get_collections() -> list[str]:
    try:
        collections = VPXCollections(str(COLLECTIONS_PATH))
        names = collections.get_collections_name()
        logger.debug("Loaded collections: %s", names)
        return names
    except Exception as exc:
        logger.warning("Error loading collections: %s", exc)
        return []


def get_collection_vpsids(collection_name: str) -> set[str]:
    try:
        collections = VPXCollections(str(COLLECTIONS_PATH))
        return set(collections.get_vpsids(collection_name))
    except Exception:
        return set()


def is_filter_collection(collection_name: str) -> bool:
    try:
        collections = VPXCollections(str(COLLECTIONS_PATH))
        return collections.is_filter_based(collection_name)
    except Exception:
        return False


def get_collection_filters(collection_name: str):
    try:
        collections = VPXCollections(str(COLLECTIONS_PATH))
        return collections.get_filters(collection_name)
    except Exception:
        return None


def _normalize_rating(value) -> int:
    try:
        normalized = int(float(value))
    except (TypeError, ValueError):
        normalized = 0
    return max(0, min(5, normalized))


def _is_truthy(value) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def table_matches_filters(table: dict, filters) -> bool:
    if not filters:
        return False

    letter = filters.get("letter", "All")
    if letter != "All":
        table_name = table.get("name", "")
        if table_name and table_name[0].upper() != letter.upper():
            return False

    manufacturer = filters.get("manufacturer", "All")
    if manufacturer != "All" and table.get("manufacturer", "") != manufacturer:
        return False

    year = filters.get("year", "All")
    if year != "All" and str(table.get("year", "")) != str(year):
        return False

    table_type = filters.get("table_type", "All")
    if table_type != "All" and table.get("type", "") != table_type:
        return False

    theme = filters.get("theme", "All")
    if theme != "All":
        table_theme = table.get("theme", "")
        if isinstance(table_theme, list):
            if theme not in table_theme:
                return False
        elif table_theme != theme:
            return False

    rating = filters.get("rating", "All")
    if rating != "All":
        selected = []
        for raw_rating in str(rating).split(","):
            try:
                selected.append(_normalize_rating(raw_rating.strip()))
            except Exception:
                continue
        table_rating = _normalize_rating(table.get("rating", 0))
        if _is_truthy(filters.get("rating_or_higher", "false")):
            if not selected or table_rating < min(selected):
                return False
        elif table_rating not in set(selected):
            return False

    return True


def scan_tables_for_launch() -> list[dict]:
    return table_catalog.scan_launchable_tables()
