from __future__ import annotations

import re
from typing import Dict, List
from pathlib import Path
from urllib.parse import quote

from common.vpxcollections import VPXCollections

from managerui.paths import COLLECTIONS_PATH, CONFIG_DIR
from managerui.services import table_index_service

COLLECTION_ICONS_DIR = CONFIG_DIR / "collection_icons"
COLLECTION_IMAGE_KEY = "image"
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif"}


def get_collections_manager() -> VPXCollections:
    return VPXCollections(str(COLLECTIONS_PATH))


def ensure_collection_icons_dir() -> Path:
    COLLECTION_ICONS_DIR.mkdir(parents=True, exist_ok=True)
    return COLLECTION_ICONS_DIR


def collection_icon_url(filename: str | None) -> str | None:
    filename = (filename or "").strip()
    if not filename:
        return None
    return f"/collection_icons/{quote(Path(filename).name)}"


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


def _set_section_image(section, filename: str | None) -> None:
    value = _validated_icon_filename(filename)
    if value:
        section[COLLECTION_IMAGE_KEY] = value
    elif COLLECTION_IMAGE_KEY in section:
        del section[COLLECTION_IMAGE_KEY]


def get_collection_image(name: str) -> str:
    manager = get_collections_manager()
    if name not in manager.config:
        return ""
    return manager.config[name].get(COLLECTION_IMAGE_KEY, "").strip()


def set_collection_image(name: str, filename: str | None) -> None:
    manager = get_collections_manager()
    if name not in manager.config:
        raise KeyError(f"Section '{name}' not found")
    _set_section_image(manager.config[name], filename)
    manager.save()


def get_table_rows_for_collections(cached_tables: list[dict] | None = None) -> list[dict]:
    return cached_tables if cached_tables is not None else table_index_service.scan_rows(reload=False)


def get_table_name_map(cached_tables: list[dict] | None = None) -> Dict[str, str]:
    tables = get_table_rows_for_collections(cached_tables)
    return {table.get("id"): table.get("name", table.get("id")) for table in tables if table.get("id")}


def get_vpsid_collections_map() -> Dict[str, List[str]]:
    mapping: Dict[str, List[str]] = {}
    try:
        collections = get_collections_manager()
        for collection_name in collections.get_collections_name():
            if collections.is_filter_based(collection_name):
                continue
            for vpsid in collections.get_vpsids(collection_name):
                mapping.setdefault(vpsid, []).append(collection_name)
    except Exception:
        pass
    return mapping


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
            "sort_options": ["Alpha", "Newest", "LastRun", "Highest StartCount", "RunTime"],
            "order_options": ["Descending", "Ascending"],
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
        "sort_options": ["Alpha", "Newest", "LastRun", "Highest StartCount", "RunTime"],
        "order_options": ["Descending", "Ascending"],
    }


def delete_collection(name: str) -> None:
    manager = get_collections_manager()
    manager.delete_collection(name)
    manager.save()


def rename_collection(name: str, new_name: str) -> None:
    manager = get_collections_manager()
    manager.rename_collection(name, new_name)
    manager.save()


def create_vpsid_collection(name: str, vpsids: list[str], image: str | None = None) -> None:
    manager = get_collections_manager()
    manager.add_collection(name, vpsids)
    if image:
        _set_section_image(manager.config[name], image)
    manager.save()


def create_filter_collection(name: str, **filters) -> None:
    image = filters.pop(COLLECTION_IMAGE_KEY, None)
    manager = get_collections_manager()
    manager.add_filter_collection(name, **filters)
    if image:
        _set_section_image(manager.config[name], image)
    manager.save()


def update_filter_collection(name: str, **filters) -> None:
    image = filters.pop(COLLECTION_IMAGE_KEY, None)
    manager = get_collections_manager()
    for key, value in filters.items():
        manager.config[name][key] = value
    if image is not None:
        _set_section_image(manager.config[name], image)
    manager.save()


def update_vpsid_collection(name: str, vpsids: list[str], image: str | None = None) -> None:
    manager = get_collections_manager()
    manager.config[name]["vpsids"] = ",".join(vpsids)
    if image is not None:
        _set_section_image(manager.config[name], image)
    manager.save()


def search_tables(term: str, cached_tables: list[dict] | None = None, limit: int = 20) -> list[dict]:
    term = (term or "").strip().lower()
    if not term:
        return []
    return [
        table for table in get_table_rows_for_collections(cached_tables)
        if term in (table.get("name") or "").lower()
    ][:limit]
