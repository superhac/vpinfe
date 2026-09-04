"""Launching a game from the Remote page, including from a collection."""

from __future__ import annotations

import logging

from common.games import collection_filters
from common.games.collection_store import CollectionStore
from common.values import is_truthy
from managerui.paths import COLLECTIONS_PATH
from managerui.services import game_catalog

logger = logging.getLogger("vpinfe.manager.remote_launch")


def get_collections() -> list[str]:
    try:
        collections = CollectionStore(str(COLLECTIONS_PATH))
        names = collections.get_collections_name()
        logger.debug("Loaded collections: %s", names)
        return names
    except Exception as exc:
        logger.warning("Error loading collections: %s", exc)
        return []


def get_collection_members(collection_name: str) -> set[str]:
    try:
        collections = CollectionStore(str(COLLECTIONS_PATH))
        return set(collections.get_members(collection_name))
    except Exception:
        return set()


def is_filter_collection(collection_name: str) -> bool:
    try:
        collections = CollectionStore(str(COLLECTIONS_PATH))
        return collections.is_filter_based(collection_name)
    except Exception:
        return False


def get_collection_filters(collection_name: str):
    try:
        collections = CollectionStore(str(COLLECTIONS_PATH))
        return collections.get_filters(collection_name)
    except Exception:
        return None


def _normalize_rating(value) -> int:
    try:
        normalized = int(float(value))
    except (TypeError, ValueError):
        normalized = 0
    return max(0, min(5, normalized))


def game_matches_filters(game: dict, filters) -> bool:
    if not filters:
        return False

    letter = filters.get("letter", "All")
    if letter != "All":
        game_name = game.get("name", "")
        if game_name and game_name[0].upper() != letter.upper():
            return False

    manufacturer = filters.get("manufacturer", "All")
    if manufacturer != "All" and game.get("manufacturer", "") != manufacturer:
        return False

    year = filters.get("year", "All")
    if year != "All" and str(game.get("year", "")) != str(year):
        return False

    game_type = collection_filters.criterion(filters, "game_type", "All")
    if game_type != "All" and game.get("type", "") != game_type:
        return False

    theme = filters.get("theme", "All")
    if theme != "All":
        game_theme = game.get("theme", "")
        if isinstance(game_theme, list):
            if theme not in game_theme:
                return False
        elif game_theme != theme:
            return False

    rating = filters.get("rating", "All")
    if rating != "All":
        selected = []
        for raw_rating in str(rating).split(","):
            try:
                selected.append(_normalize_rating(raw_rating.strip()))
            except Exception:
                continue
        game_rating = _normalize_rating(game.get("rating", 0))
        if is_truthy(filters.get("rating_or_higher", "false")):
            if not selected or game_rating < min(selected):
                return False
        elif game_rating not in set(selected):
            return False

    return True


def scan_games_for_launch() -> list[dict]:
    return game_catalog.scan_launchable_games()
