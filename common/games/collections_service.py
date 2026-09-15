"""Collections as the pages and themes use them - names, icons, and what is in one."""

from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import quote

from common.games.collection_store import CollectionStore
from common.paths import COLLECTIONS_PATH, get_ini_config
from common.values import is_truthy

COLLECTION_ICONS_DIR = COLLECTIONS_PATH.parent / "collection_icons"
COLLECTION_IMAGE_KEY = "image"


def get_collections_manager() -> CollectionStore:
    return CollectionStore(str(COLLECTIONS_PATH))


def ensure_collection_icons_dir() -> Path:
    COLLECTION_ICONS_DIR.mkdir(parents=True, exist_ok=True)
    return COLLECTION_ICONS_DIR


# What a collection icon may be. Checked on the way in, because the file is served
# straight back out and the extension is what a browser reads it as.
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif"}


def _safe_icon_stem(filename: str) -> str:
    stem = Path(filename).stem.strip()
    stem = re.sub(r"[^A-Za-z0-9._-]+", "_", stem).strip("._-")
    return stem or "collection"


def save_collection_icon(filename: str, content: bytes) -> str:
    """Write an icon and answer the name it was stored under.

    In core rather than in one surface: an icon is a property of a collection, so every
    surface that edits one needs to write it. A name already taken gets a counter rather than being
    overwritten - two collections may reasonably both offer "logo.png".
    """
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


def collection_icon_path(filename: str | None) -> Path | None:
    """Where one icon is on disk, or None when the name escapes the icon folder."""
    name = Path(filename or "").name.strip()
    if not name:
        return None
    here = ensure_collection_icons_dir() / name
    return here if here.is_file() else None


def follow_rename_in_settings(old_name: str, new_name: str) -> None:
    """Move `general.startup_collection` along with the collection it names.

    The setting holds a name because a collection has no id to hold instead, so a rename
    left it pointing at a collection that no longer existed. The frontend caught the
    failure, logged it and showed the whole library - which looks like the setting was
    never set rather than like something broke.
    """
    store = get_ini_config()
    if str(store.value("general", "startup_collection") or "").strip() != old_name:
        return
    store.set_value("general", "startup_collection", new_name)
    store.save()


def forget_in_settings(name: str) -> None:
    """Clear `general.startup_collection` when the collection it names is deleted.

    The alternative is leaving it naming something gone, which shows the whole library
    and raises on every start. This shows the whole library and says so on the settings
    screen, which is the same outcome told honestly.
    """
    store = get_ini_config()
    if str(store.value("general", "startup_collection") or "").strip() != name:
        return
    store.set_value("general", "startup_collection", "")
    store.save()


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
            # The stored membership, whatever else the collection carries. Criteria and
            # named members are combinable, so reporting null for
            # anything that filters hid the members it also held.
            "game_count": len(manager.get_members(name)),
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
    rating_or_higher: object = False,
    sort_by: str = "Alpha",
    order_by: str = "desc",
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
