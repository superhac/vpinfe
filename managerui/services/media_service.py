from __future__ import annotations

import logging
import os
import shutil
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import quote

from common.metaconfig import MetaConfig
from common.table_repository import ensure_tables_loaded

from managerui.paths import CONFIG_DIR, get_tables_path


logger = logging.getLogger("vpinfe.manager.media_service")

_media_cache: Optional[List[Dict]] = None
_thumb_request_state: set[tuple[str, str, str]] = set()

CACHE_DIR = CONFIG_DIR / "cache"
THUMB_CACHE_ROOT = CACHE_DIR / "media_thumbs"
THUMB_SIZE = (512, 512)
THUMB_WARM_ROW_BATCH_SIZE = 25
THUMB_WARM_CHUNK_SIZE = 8

MEDIA_TYPES = [
    ("bg", "BG", "bg.png"),
    ("dmd", "DMD", "dmd.png"),
    ("table", "Table", "table.png"),
    ("fss", "FSS", "fss.png"),
    ("wheel", "Wheel", "wheel.png"),
    ("cab", "Cab", "cab.png"),
    ("realdmd", "Real DMD", "realdmd.png"),
    ("realdmd_color", "Real DMD Color", "realdmd-color.png"),
    ("flyer", "Flyer", "flyer.png"),
    ("table_video", "Table Video", "table.mp4"),
    ("bg_video", "BG Video", "bg.mp4"),
    ("dmd_video", "DMD Video", "dmd.mp4"),
    ("audio", "Audio", "audio.mp3"),
]
MEDIA_KEY_TO_FILENAME = {key: filename for key, _, filename in MEDIA_TYPES}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif"}
IMAGE_MEDIA_KEYS = [
    key for key, _, filename in MEDIA_TYPES
    if Path(filename).suffix.lower() in IMAGE_EXTENSIONS
]

TABLE_ATTR_TO_MEDIA_KEY = {
    "BGImagePath": "bg",
    "DMDImagePath": "dmd",
    "TableImagePath": "table",
    "FSSImagePath": "fss",
    "WheelImagePath": "wheel",
    "CabImagePath": "cab",
    "realDMDImagePath": "realdmd",
    "realDMDColorImagePath": "realdmd_color",
    "FlyerImagePath": "flyer",
    "TableVideoPath": "table_video",
    "BGVideoPath": "bg_video",
    "DMDVideoPath": "dmd_video",
    "AudioPath": "audio",
}


def get_media_cache() -> Optional[List[Dict]]:
    return _media_cache


def set_media_cache(rows: List[Dict]) -> None:
    global _media_cache
    _media_cache = rows


def invalidate_media_cache() -> None:
    global _media_cache
    _media_cache = None


def media_url(*parts: str) -> str:
    encoded = [quote(part.strip("/")) for part in parts if part]
    return "/" + "/".join(encoded)


def is_image_media_key(media_key: str) -> bool:
    filename = MEDIA_KEY_TO_FILENAME.get(media_key, "")
    return Path(filename).suffix.lower() in IMAGE_EXTENSIONS


def source_media_path(table_path: str, media_key: str) -> Optional[str]:
    filename = MEDIA_KEY_TO_FILENAME.get(media_key)
    if not filename:
        return None
    medias_path = os.path.join(table_path, "medias", filename)
    if os.path.exists(medias_path):
        return medias_path
    root_path = os.path.join(table_path, filename)
    if os.path.exists(root_path):
        return root_path
    return None


def _build_thumb_sig(source_path: str) -> str:
    st = os.stat(source_path)
    return f"{st.st_mtime_ns}_{st.st_size}"


def thumb_file_path(table_dir: str, media_key: str, source_path: str) -> Path:
    return THUMB_CACHE_ROOT / table_dir / f"{media_key}_{_build_thumb_sig(source_path)}.png"


def thumb_url(path: Path) -> str:
    rel = path.relative_to(THUMB_CACHE_ROOT).as_posix()
    return f"/media_thumbs/{rel}"


def get_cached_thumb_url(table_dir: str, media_key: str, source_path: str) -> Optional[str]:
    if not is_image_media_key(media_key) or not os.path.exists(source_path):
        return None
    try:
        path = thumb_file_path(table_dir, media_key, source_path)
        if path.exists():
            os.utime(path, None)
            return thumb_url(path)
    except Exception:
        return None
    return None


def thumb_request_key(table_dir: str, media_key: str, source_path: str) -> tuple[str, str, str]:
    try:
        signature = _build_thumb_sig(source_path)
    except Exception:
        signature = ""
    return table_dir, media_key, signature


def mark_thumb_requested(table_dir: str, media_key: str, source_path: str) -> bool:
    """Return True if this thumbnail request is new."""
    key = thumb_request_key(table_dir, media_key, source_path)
    if key in _thumb_request_state:
        return False
    _thumb_request_state.add(key)
    return True


def clear_thumb_request(table_dir: str, media_key: str, source_path: str) -> None:
    _thumb_request_state.discard(thumb_request_key(table_dir, media_key, source_path))


def ensure_thumb(table_dir: str, media_key: str, source_path: str) -> Optional[str]:
    if not is_image_media_key(media_key) or not os.path.exists(source_path):
        return None
    try:
        from PIL import Image, ImageOps
    except Exception:
        return None

    try:
        path = thumb_file_path(table_dir, media_key, source_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            os.utime(path, None)
            return thumb_url(path)

        for old in path.parent.glob(f"{media_key}_*.png"):
            if old != path:
                old.unlink(missing_ok=True)
        for old in path.parent.glob(f"{media_key}_*.jpg"):
            if old != path:
                old.unlink(missing_ok=True)

        with Image.open(source_path) as img:
            img = ImageOps.exif_transpose(img)
            has_alpha = (
                img.mode in ("RGBA", "LA")
                or (img.mode == "P" and "transparency" in img.info)
            )
            img = img.convert("RGBA" if has_alpha else "RGB")
            img.thumbnail(THUMB_SIZE, Image.Resampling.LANCZOS)
            img.save(path, format="PNG", optimize=True)
        os.utime(path, None)
        return thumb_url(path)
    except Exception:
        return None


def _table_meta_sections(table):
    raw = table.metaConfig or {}
    if not isinstance(raw, dict):
        raw = {}
    info = raw.get("Info", {}) if isinstance(raw.get("Info", {}), dict) else {}
    vpinfe = raw.get("VPinFE", {}) if isinstance(raw.get("VPinFE", {}), dict) else {}
    return info, vpinfe


def media_url_from_path(table_dir: str, source_path: str) -> Optional[str]:
    if not source_path:
        return None
    source = Path(source_path)
    if source.parent.name == "medias":
        return media_url("media_tables", table_dir, "medias", source.name)
    return media_url("media_tables", table_dir, source.name)


def scan_media_tables(reload: bool = False) -> List[Dict]:
    tables_path = get_tables_path()
    rows = []
    if not os.path.exists(tables_path):
        logger.warning("Tables path does not exist: %s. Skipping media scan.", tables_path)
        return []

    for table in ensure_tables_loaded(reload=reload):
        root = getattr(table, "fullPathTable", "") or ""
        if not root:
            continue
        current_dir = Path(root).name
        info, vpinfe = _table_meta_sections(table)
        name = ((vpinfe.get("alttitle") or info.get("Title") or current_dir) or "").strip()

        media_info = {}
        thumb_info = {}
        for attr_name, media_key in TABLE_ATTR_TO_MEDIA_KEY.items():
            source_path = getattr(table, attr_name, None)
            if source_path:
                media_info[media_key] = media_url_from_path(current_dir, source_path)
                thumb_info[media_key] = get_cached_thumb_url(current_dir, media_key, source_path)
            else:
                media_info[media_key] = None
                thumb_info[media_key] = None

        row = {
            "name": name,
            "table_dir": current_dir,
            "table_path": root,
            "manufacturer": info.get("Manufacturer", ""),
            "year": info.get("Year", ""),
            "type": info.get("Type", ""),
            "themes": info.get("Themes", []),
            "media": media_info,
            "thumbs": thumb_info,
            "thumb_errors": {},
        }
        for media_key, _, _ in MEDIA_TYPES:
            row[f"has_{media_key}"] = media_info.get(media_key) is not None
        rows.append(row)

    set_media_cache(rows)
    return rows


def replace_media_file(table_path: str, table_dir: str, media_key: str, uploaded_path: str) -> str:
    target_filename = MEDIA_KEY_TO_FILENAME[media_key]
    medias_dir = os.path.join(table_path, "medias")
    os.makedirs(medias_dir, exist_ok=True)
    target_path = os.path.join(medias_dir, target_filename)

    shutil.copy2(uploaded_path, target_path)

    info_file = os.path.join(table_path, f"{table_dir}.info")
    if os.path.exists(info_file):
        mc = MetaConfig(info_file)
        mc.addMedia(media_key, "user", target_path, "")

    return target_path


def update_cache_entry(table_dir: str, media_key: str, url_path: str, thumb: Optional[str] = None) -> None:
    if _media_cache is None:
        return
    for row in _media_cache:
        if row["table_dir"] == table_dir:
            row["media"][media_key] = url_path
            row.setdefault("thumbs", {})[media_key] = thumb
            row.setdefault("thumb_errors", {}).pop(media_key, None)
            row[f"has_{media_key}"] = url_path is not None
            break
