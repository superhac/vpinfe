from __future__ import annotations

import logging
import os
import shutil
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import quote

from common.games.game_metadata import reorder_leading_article, vpinfe_section
from common.games.game_repository import ensure_games_loaded
from common.games.info_file import MetaConfig
from common.media_specs import (
    MEDIA_SPECS,
    media_attr_key_map,
    media_filename_map,
    resolve_media_files,
)
from managerui.paths import CONFIG_DIR, get_games_path

logger = logging.getLogger("vpinfe.manager.media_service")

_media_cache: Optional[List[Dict]] = None
_thumb_request_state: set[tuple[str, str, str]] = set()

CACHE_DIR = CONFIG_DIR / "cache"
THUMB_CACHE_ROOT = CACHE_DIR / "media_thumbs"
THUMB_SIZE = (512, 512)
THUMB_WARM_ROW_BATCH_SIZE = 25
THUMB_WARM_CHUNK_SIZE = 8

# Canonical media kind keys. MEDIA_KEY_TO_FILENAME and _SPEC_BY_KEY are both built
# from MEDIA_SPECS, so `bg` and `dmd` here were a KeyError on upload and an empty
# filename on lookup - the two kinds people replace most. The labels stay as they are:
# BG and DMD is what the art is called, whatever the kind is called.
MEDIA_TYPES = [
    ("backglass", "BG", "bg.png"),
    ("scoreview", "DMD", "dmd.png"),
    ("playfield", "Table", "table.png"),
    ("playfield_fss", "FSS", "fss.png"),
    ("wheel", "Wheel", "wheel.png"),
    ("cab", "Cab", "cab.png"),
    ("real_dmd", "Real DMD", "realdmd.png"),
    ("real_dmd_color", "Real DMD Color", "realdmd-color.png"),
    ("flyer", "Flyer", "flyer.png"),
    ("playfield_video", "Table Video", "table.mp4"),
    ("backglass_video", "BG Video", "bg.mp4"),
    ("scoreview_video", "DMD Video", "dmd.mp4"),
    ("audio", "Audio", "audio.mp3"),
]
MEDIA_KEY_TO_FILENAME = media_filename_map("table")
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif"}
IMAGE_MEDIA_KEYS = [
    key for key, _, filename in MEDIA_TYPES
    if Path(filename).suffix.lower() in IMAGE_EXTENSIONS
]

GAME_ATTR_TO_MEDIA_KEY = media_attr_key_map("table")


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


_SPEC_BY_KEY = {spec.key: spec for spec in MEDIA_SPECS}


def source_media_path(game_path: str, media_key: str,
                      table_stem: str | None = None) -> str | None:
    """The file serving a media kind, through the one resolution chain - so the
    Manager UI and the scan can never disagree about which file that is."""
    if media_key not in _SPEC_BY_KEY:
        return None
    root = Path(game_path)
    try:
        game_contents = {e.name for e in os.scandir(root) if e.is_file()}
    except OSError:
        return None
    medias_dir = root / "medias"
    try:
        medias_contents = {e.name for e in os.scandir(medias_dir) if e.is_file()}
    except OSError:
        medias_contents = set()
    resolved = resolve_media_files(root, game_contents, medias_contents,
                                   "table", table_stem)
    path = resolved.get(media_key)
    return str(path) if path is not None else None


def _build_thumb_sig(source_path: str) -> str:
    st = os.stat(source_path)
    return f"{st.st_mtime_ns}_{st.st_size}"


def thumb_file_path(game_dir: str, media_key: str, source_path: str) -> Path:
    return THUMB_CACHE_ROOT / game_dir / f"{media_key}_{_build_thumb_sig(source_path)}.png"


def thumb_url(path: Path) -> str:
    rel = path.relative_to(THUMB_CACHE_ROOT).as_posix()
    return f"/media_thumbs/{rel}"


def get_cached_thumb_url(game_dir: str, media_key: str, source_path: str) -> Optional[str]:
    if not is_image_media_key(media_key) or not os.path.exists(source_path):
        return None
    try:
        path = thumb_file_path(game_dir, media_key, source_path)
        if path.exists():
            os.utime(path, None)
            return thumb_url(path)
    except Exception:
        return None
    return None


def thumb_request_key(game_dir: str, media_key: str, source_path: str) -> tuple[str, str, str]:
    try:
        signature = _build_thumb_sig(source_path)
    except Exception:
        signature = ""
    return game_dir, media_key, signature


def mark_thumb_requested(game_dir: str, media_key: str, source_path: str) -> bool:
    """Return True if this thumbnail request is new."""
    key = thumb_request_key(game_dir, media_key, source_path)
    if key in _thumb_request_state:
        return False
    _thumb_request_state.add(key)
    return True


def clear_thumb_request(game_dir: str, media_key: str, source_path: str) -> None:
    _thumb_request_state.discard(thumb_request_key(game_dir, media_key, source_path))


def ensure_thumb(game_dir: str, media_key: str, source_path: str) -> Optional[str]:
    if not is_image_media_key(media_key) or not os.path.exists(source_path):
        return None
    try:
        from PIL import Image, ImageOps
    except Exception:
        return None

    try:
        path = thumb_file_path(game_dir, media_key, source_path)
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


def _game_meta_sections(game):
    raw = game.meta_config or {}
    if not isinstance(raw, dict):
        raw = {}
    info = raw.get("Info", {}) if isinstance(raw.get("Info", {}), dict) else {}
    vpinfe = vpinfe_section(raw)
    return info, vpinfe


def media_url_from_path(game_dir: str, source_path: str) -> Optional[str]:
    if not source_path:
        return None
    source = Path(source_path)
    if source.parent.name == "medias":
        return media_url("media_games", game_dir, "medias", source.name)
    return media_url("media_games", game_dir, source.name)


def scan_media_games(reload: bool = False) -> List[Dict]:
    games_path = get_games_path()
    rows = []
    if not os.path.exists(games_path):
        logger.warning("Games path does not exist: %s. Skipping media scan.", games_path)
        return []

    for game in ensure_games_loaded(reload=reload):
        root = getattr(game, "fullPathGame", "") or ""
        if not root:
            continue
        current_dir = Path(root).name
        info, vpinfe = _game_meta_sections(game)
        name = ((vpinfe.get("alt_title") or "").strip()
                or reorder_leading_article(info.get("Title") or current_dir))

        media_info = {}
        thumb_info = {}
        for attr_name, media_key in GAME_ATTR_TO_MEDIA_KEY.items():
            source_path = getattr(game, attr_name, None)
            if source_path:
                media_info[media_key] = media_url_from_path(current_dir, source_path)
                thumb_info[media_key] = get_cached_thumb_url(current_dir, media_key, source_path)
            else:
                media_info[media_key] = None
                thumb_info[media_key] = None

        row = {
            "name": name,
            "game_dir": current_dir,
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


def replace_media_file(game_path: str, game_dir: str, media_key: str, uploaded_path: str) -> str:
    """Install an uploaded file as a game's media, keeping its real extension.

    The old behavior copied bytes to the canonical name unchanged, so a .jpg
    became JPEG bytes inside wheel.png - a file that lies. The name now keeps the
    source extension when the kind's family accepts it, and any family sibling
    with the same stem is removed from medias/ and the folder root, since an
    earlier-family leftover would shadow the new file in resolution order.
    """
    spec = _SPEC_BY_KEY[media_key]
    canonical = MEDIA_KEY_TO_FILENAME[media_key]
    stem, canonical_ext = os.path.splitext(canonical)
    ext = os.path.splitext(uploaded_path)[1].lower()
    if ext not in spec.family:
        ext = canonical_ext
    target_filename = stem + ext

    medias_dir = os.path.join(game_path, "medias")
    os.makedirs(medias_dir, exist_ok=True)
    target_path = os.path.join(medias_dir, target_filename)

    for sibling_ext in spec.family:
        for base in (medias_dir, game_path):
            sibling = os.path.join(base, stem + sibling_ext)
            if sibling != target_path and os.path.exists(sibling):
                os.remove(sibling)

    shutil.copy2(uploaded_path, target_path)

    info_file = os.path.join(game_path, f"{game_dir}.info")
    if os.path.exists(info_file):
        mc = MetaConfig(info_file)
        # No hash: one is only meaningful as a comparison against a remote, and there
        # is no remote here - the user handed us the bytes.
        mc.add_asset(target_path, "user")

    return target_path


def update_cache_entry(game_dir: str, media_key: str, url_path: str, thumb: Optional[str] = None) -> None:
    if _media_cache is None:
        return
    for row in _media_cache:
        if row["game_dir"] == game_dir:
            row["media"][media_key] = url_path
            row.setdefault("thumbs", {})[media_key] = thumb
            row.setdefault("thumb_errors", {}).pop(media_key, None)
            row[f"has_{media_key}"] = url_path is not None
            break
