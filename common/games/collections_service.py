"""Collections as the pages and themes use them - names, icons, and what is in one."""

from __future__ import annotations

from pathlib import Path
from urllib.parse import quote

from common.games.collection_store import CollectionStore
from common.paths import COLLECTIONS_PATH
from common.values import is_truthy

COLLECTION_ICONS_DIR = COLLECTIONS_PATH.parent / "collection_icons"
COLLECTION_IMAGE_KEY = "image"


def get_collections_manager() -> CollectionStore:
    return CollectionStore(str(COLLECTIONS_PATH))


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
    if collection not in manager:
        return ""
    return manager.get_image(collection)


def get_collection_image_url(collection: str) -> str:
    return collection_icon_url(get_collection_image(collection))


def get_collections_metadata() -> list[dict]:
    manager = get_collections_manager()
    rows = []
    for name in manager.get_collections_name():
        is_filter = manager.is_filter_based(name)
        image = manager.get_image(name)
        rows.append({
            "name": name,
            "type": "filter" if is_filter else "vpsid",
            "is_filter": is_filter,
            "image": image,
            "image_url": collection_icon_url(image),
            "game_count": None if is_filter else len(manager.get_members(name)),
        })
    return rows


def save_filter_collection(
    name: str,
    letter: str = "All",
    theme: str = "All",
    game_type: str = "All",
    manufacturer: str = "All",
    year: str = "All",
    rating: str = "All",
    rating_or_higher=False,
    sort_by: str = "Alpha",
    order_by: str = "Descending",
) -> None:
    with get_collections_manager().mutate() as manager:
        manager.add_filter_collection(
            name,
            letter,
            theme,
            game_type,
            manufacturer,
            year,
            rating,
            "true" if is_truthy(rating_or_higher) else "false",
            sort_by,
            order_by,
        )
