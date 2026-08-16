"""Creating, editing and deleting collections, and the icons they carry.

The write side. `common.games.collections_service` is the read side - names, metadata,
membership - and both are needed here, so the shared helpers are imported rather than
kept twice. They were kept twice until 2026-08-05, under the same filename in two
packages, and two of the four copies had drifted apart.
"""

from __future__ import annotations

import re
from pathlib import Path

from common.games import game_index_service, game_repository

# Imported and re-exported: the collections page reaches both halves through this
# module, and these four were duplicated here until 2026-08-05.
# The sort vocabulary belongs to the store, and the page reads it from here rather than
# writing the names out again - which is how the editor came to offer 2.x spellings.
from common.games.collection_store import (  # noqa: F401  (import and export)
    DEFAULT_DIRECTION,
    DEFAULT_ORDER_BY,
    DIRECTION_LABELS,
    SORT_LABELS,
)
from common.games.collections_service import (  # noqa: F401  (import and export)
    collection_icon_url,
    ensure_collection_icons_dir,
    get_collection_image,
    get_collections_manager,
)
from managerui.paths import CONFIG_DIR

COLLECTION_ICONS_DIR = CONFIG_DIR / "collection_icons"
COLLECTION_IMAGE_KEY = "image"
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif"}





def list_collection_icons() -> list[str]:
    icon_dir = ensure_collection_icons_dir()
    return sorted(
        path.name for path in icon_dir.iterdir()
        if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS
    )


def _safe_icon_stem(filename: str) -> str:
    stem = Path(filename).stem.strip()
    stem = re.sub(r"[^A-Za-z0-9._-]+", "_", stem).strip("._-")
    return stem or "collection"


def save_collection_icon(filename: str, content: bytes) -> str:
    suffix = Path(filename).suffix.lower()
    if suffix not in IMAGE_EXTENSIONS:
        raise ValueError("Collection image must be an image file")

    icon_dir = ensure_collection_icons_dir()
    stem = _safe_icon_stem(filename)
    candidate = f"{stem}{suffix}"
    target = icon_dir / candidate
    counter = 1
    while target.exists():
        candidate = f"{stem}_{counter}{suffix}"
        target = icon_dir / candidate
        counter += 1

    target.write_bytes(content)
    return candidate


def _validated_icon_filename(filename: str | None) -> str:
    value = Path(filename or "").name.strip()
    if not value:
        return ""
    if Path(value).suffix.lower() not in IMAGE_EXTENSIONS:
        raise ValueError("Collection image must be an image file")
    if not (ensure_collection_icons_dir() / value).exists():
        raise FileNotFoundError(f"Collection image '{value}' was not found")
    return value


def _set_section_image(manager, name: str, filename: str | None) -> None:
    manager.set_image(name, _validated_icon_filename(filename))



def set_collection_image(name: str, filename: str | None) -> None:
    with get_collections_manager().mutate() as manager:
        if name not in manager:
            raise KeyError(f"Section '{name}' not found")
        _set_section_image(manager, name, filename)


def get_game_rows_for_collections(cached_games: list[dict] | None = None) -> list[dict]:
    return cached_games if cached_games is not None else game_index_service.scan_rows(reload=False)


def get_vpsdb_rows_for_filter_options(cached_vpsdb_rows: list[dict] | None = None) -> list[dict]:
    if cached_vpsdb_rows is not None:
        return cached_vpsdb_rows

    from common.games import game_service

    rows = game_service.load_vpsdb()
    if not rows and game_service.ensure_vpsdb_downloaded():
        rows = game_service.load_vpsdb()
    return rows


def get_game_name_map(cached_games: list[dict] | None = None) -> dict[str, str]:
    games = get_game_rows_for_collections(cached_games)
    return {
        game["vpinfe_id"]: game.get("name") or game["vpinfe_id"]
        for game in games
        if game.get("vpinfe_id")
    }


def get_game_collections_map() -> dict[str, list[str]]:
    return game_repository.collections_by_game_id()


def member_to_name(member_id: str, game_map: dict[str, str] | None = None) -> str:
    """Display name for a collection member, falling back to the raw id.

    An entry that has not been migrated yet, or points at a game that is not
    installed, has no name to show - so show what is recorded rather than nothing.
    """
    if game_map is None:
        game_map = get_game_name_map()
    return game_map.get(member_id, member_id)


def _as_values(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, tuple) or isinstance(value, set):
        return [str(item).strip() for item in value if str(item).strip()]
    return [part.strip() for part in str(value).split(",") if part.strip()]


def get_filter_options(cached_vpsdb_rows: list[dict] | None = None) -> dict[str, list[str]]:
    games = get_vpsdb_rows_for_filter_options(cached_vpsdb_rows)

    if not games:
        return {
            "letters": ["All"],
            "themes": ["All"],
            "types": ["All"],
            "manufacturers": ["All"],
            "years": ["All"],
            "ratings": ["All", "1", "2", "3", "4", "5"],
        }

    letters = set()
    themes = set()
    types = set()
    manufacturers = set()
    years = set()

    for game in games:
        name = game.get("name", "")
        if name:
            first_char = name[0].upper()
            if first_char.isalnum():
                letters.add(first_char)

        game_type = game.get("type", "") or game.get("tableType", "")
        if game_type:
            types.add(str(game_type).strip())

        manufacturer = game.get("manufacturer", "") or game.get("mfg", "")
        if manufacturer:
            manufacturers.add(str(manufacturer).strip())

        year = game.get("year", "")
        if year:
            years.add(str(year))

        themes.update(_as_values(game.get("theme", game.get("themes", []))))

    return {
        "letters": ["All"] + sorted(letters),
        "themes": ["All"] + sorted(themes),
        "types": ["All"] + sorted(types),
        "manufacturers": ["All"] + sorted(manufacturers),
        "years": ["All"] + sorted(years),
        "ratings": ["All", "1", "2", "3", "4", "5"],
    }


def delete_collection(name: str) -> None:
    with get_collections_manager().mutate() as manager:
        manager.delete_collection(name)


def rename_collection(name: str, new_name: str) -> None:
    with get_collections_manager().mutate() as manager:
        manager.rename_collection(name, new_name)


def create_game_collection(name: str, game_ids: list[str], image: str | None = None) -> None:
    with get_collections_manager().mutate() as manager:
        manager.add_collection(name, game_ids)
        if image:
            _set_section_image(manager, name, image)


def create_filter_collection(name: str, **filters) -> None:
    image = filters.pop(COLLECTION_IMAGE_KEY, None)
    with get_collections_manager().mutate() as manager:
        manager.add_filter_collection(name, **filters)
        if image:
            _set_section_image(manager, name, image)


def update_filter_collection(name: str, **filters) -> None:
    image = filters.pop(COLLECTION_IMAGE_KEY, None)
    with get_collections_manager().mutate() as manager:
        for key, value in filters.items():
            manager.set_filter(name, key, value)
        if image is not None:
            _set_section_image(manager, name, image)


# What a page press moves by in this collection. The empty key is "no opinion" - it has
# to be offered, or a collection could never go back to following the player.
PAGING_GROUP_LABELS = {
    "": "Follow my setting",
    "sort": "By the sort",
    "count": "By a fixed number",
}


def set_collection_order(name: str, by: str, direction: str,
                         paging_group: str | None = None) -> None:
    """How this collection is ordered, in the `order` block the resolver reads.

    Not as `sort_by`/`order_by` criteria: those are only a fallback for files written
    before the block existed, so writing them at a collection that has one - every Last
    Played does - changes the stored value and nothing on screen.

    `paging_group` of None means this collection has no opinion and follows the player's
    setting, which is not the same as choosing what the player currently has.
    """
    with get_collections_manager().mutate() as manager:
        manager.set_order(name, by, direction, paging_group)


def update_game_collection(name: str, game_ids: list[str], image: str | None = None) -> None:
    with get_collections_manager().mutate() as manager:
        manager.set_members(name, game_ids)
        if image is not None:
            _set_section_image(manager, name, image)


def search_games(term: str, cached_games: list[dict] | None = None, limit: int = 20) -> list[dict]:
    term = (term or "").strip().lower()
    if not term:
        return []
    return [
        game for game in get_game_rows_for_collections(cached_games)
        if term in (game.get("name") or "").lower()
    ][:limit]
