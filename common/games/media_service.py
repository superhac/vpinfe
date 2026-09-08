"""Finding a game's media for the pages, and forgetting it when the files change."""

from __future__ import annotations

import logging
import os
import shutil
from pathlib import Path
from urllib.parse import quote

from common.games.game_metadata import reorder_leading_article, vpinfe_section
from common.games.game_repository import all_games
from common.games.info_file import MetaConfig
from common.media_specs import (
    MEDIA_SPECS,
    media_attr_kind_map,
    media_filename_map,
    media_label_map,
    resolve_media_files,
)
from common.paths import CONFIG_DIR, get_games_path

logger = logging.getLogger("vpinfe.manager.media_service")

_media_cache: list[dict] | None = None
_thumb_request_state: set[tuple[str, str, str]] = set()

CACHE_DIR = CONFIG_DIR / "cache"
THUMB_CACHE_ROOT = CACHE_DIR / "media_thumbs"
THUMB_SIZE = (512, 512)
THUMB_WARM_ROW_BATCH_SIZE = 25
THUMB_WARM_CHUNK_SIZE = 8

MEDIA_FILENAME_BY_KIND = media_filename_map("table")
MEDIA_LABEL_BY_KIND = media_label_map()
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif"}

GAME_ATTR_TO_MEDIA_KIND = media_attr_kind_map("table")


def get_media_cache() -> list[dict] | None:
    return _media_cache


def set_media_cache(rows: list[dict]) -> None:
    global _media_cache
    _media_cache = rows


def invalidate_media_cache() -> None:
    global _media_cache
    _media_cache = None


def media_url(*parts: str) -> str:
    encoded = [quote(part.strip("/")) for part in parts if part]
    return "/" + "/".join(encoded)


def is_image_media_kind(kind: str) -> bool:
    filename = MEDIA_FILENAME_BY_KIND.get(kind, "")
    return Path(filename).suffix.lower() in IMAGE_EXTENSIONS


_SPEC_BY_KIND = {spec.kind: spec for spec in MEDIA_SPECS}


def source_media_path(game_dir: Path, kind: str,
                      table_stem: str | None = None) -> str | None:
    """The file serving a media kind, through the one resolution chain - so the
    Manager UI and the scan can never disagree about which file that is."""
    if kind not in _SPEC_BY_KIND:
        return None
    root = Path(game_dir)
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
    path = resolved.get(kind)
    return str(path) if path is not None else None


def _build_thumb_sig(source_path: str) -> str:
    st = os.stat(source_path)
    return f"{st.st_mtime_ns}_{st.st_size}"


def thumb_file_path(game_dir_name: str, kind: str, source_path: str) -> Path:
    return THUMB_CACHE_ROOT / game_dir_name / f"{kind}_{_build_thumb_sig(source_path)}.png"


def thumb_url(path: Path) -> str:
    rel = path.relative_to(THUMB_CACHE_ROOT).as_posix()
    return f"/media_thumbs/{rel}"


def get_cached_thumb_url(game_dir_name: str, kind: str, source_path: str) -> str | None:
    if not is_image_media_kind(kind) or not os.path.exists(source_path):
        return None
    try:
        path = thumb_file_path(game_dir_name, kind, source_path)
        if path.exists():
            os.utime(path, None)
            return thumb_url(path)
    except Exception:
        return None
    return None


def thumb_request_key(game_dir_name: str, kind: str, source_path: str) -> tuple[str, str, str]:
    try:
        signature = _build_thumb_sig(source_path)
    except Exception:
        signature = ""
    return game_dir_name, kind, signature


def mark_thumb_requested(game_dir_name: str, kind: str, source_path: str) -> bool:
    """Return True if this thumbnail request is new."""
    key = thumb_request_key(game_dir_name, kind, source_path)
    if key in _thumb_request_state:
        return False
    _thumb_request_state.add(key)
    return True


def clear_thumb_request(game_dir_name: str, kind: str, source_path: str) -> None:
    _thumb_request_state.discard(thumb_request_key(game_dir_name, kind, source_path))


def ensure_thumb(game_dir_name: str, kind: str, source_path: str) -> str | None:
    if not is_image_media_kind(kind) or not os.path.exists(source_path):
        return None
    try:
        from PIL import Image, ImageOps
    except Exception:
        return None

    try:
        path = thumb_file_path(game_dir_name, kind, source_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            os.utime(path, None)
            return thumb_url(path)

        for old in path.parent.glob(f"{kind}_*.png"):
            if old != path:
                old.unlink(missing_ok=True)
        for old in path.parent.glob(f"{kind}_*.jpg"):
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


def media_url_from_path(game_dir_name: str, source_path: str) -> str | None:
    if not source_path:
        return None
    source = Path(source_path)
    if source.parent.name == "medias":
        return media_url("media_games", game_dir_name, "medias", source.name)
    return media_url("media_games", game_dir_name, source.name)


def scan_media_games(reload: bool = False) -> list[dict]:
    games_path = get_games_path()
    rows = []
    if not os.path.exists(games_path):
        logger.warning("Games path does not exist: %s. Skipping media scan.", games_path)
        return []

    for game in all_games(reload=reload):
        root = getattr(game, "fullPathGame", "") or ""
        if not root:
            continue
        current_dir = Path(root).name
        info, vpinfe = _game_meta_sections(game)
        name = ((vpinfe.get("alt_title") or "").strip()
                or reorder_leading_article(info.get("Title") or current_dir))

        media_info = {}
        thumb_info = {}
        for attr_name, kind in GAME_ATTR_TO_MEDIA_KIND.items():
            source_path = getattr(game, attr_name, None)
            if source_path:
                media_info[kind] = media_url_from_path(current_dir, source_path)
                thumb_info[kind] = get_cached_thumb_url(current_dir, kind, source_path)
            else:
                media_info[kind] = None
                thumb_info[kind] = None

        row = {
            "name": name,
            "game_dir_name": current_dir,
            "game_dir": root,
            "manufacturer": info.get("Manufacturer", ""),
            "year": info.get("Year", ""),
            "type": info.get("Type", ""),
            "themes": info.get("Themes", []),
            "media": media_info,
            "thumbs": thumb_info,
            "thumb_errors": {},
        }
        # Every kind, not the ones a page happens to show: a sortable column binds to
        # has_<kind>, and which kinds get a column is the page's choice to make.
        for kind in MEDIA_FILENAME_BY_KIND:
            row[f"has_{kind}"] = media_info.get(kind) is not None
        rows.append(row)

    set_media_cache(rows)
    return rows


def replace_media_file(game_dir: Path, game_dir_name: str, kind: str,
                       uploaded_path: str) -> str:
    """Install an uploaded file as a game's media, keeping its real extension.

    The old behavior copied bytes to the canonical name unchanged, so a .jpg
    became JPEG bytes inside wheel.png - a file that lies. The name now keeps the
    source extension when the kind's family accepts it, and any family sibling
    with the same stem is removed from medias/ and the folder root, since an
    earlier-family leftover would shadow the new file in resolution order.
    """
    spec = _SPEC_BY_KIND[kind]
    canonical = MEDIA_FILENAME_BY_KIND[kind]
    stem, canonical_ext = os.path.splitext(canonical)
    ext = os.path.splitext(uploaded_path)[1].lower()
    if ext not in spec.family:
        ext = canonical_ext
    target_filename = stem + ext

    medias_dir = os.path.join(game_dir, "medias")
    os.makedirs(medias_dir, exist_ok=True)
    target_path = os.path.join(medias_dir, target_filename)

    for sibling_ext in spec.family:
        for base in (medias_dir, game_dir):
            sibling = os.path.join(base, stem + sibling_ext)
            if sibling != target_path and os.path.exists(sibling):
                os.remove(sibling)

    shutil.copy2(uploaded_path, target_path)

    info_file = os.path.join(game_dir, f"{game_dir_name}.info")
    if os.path.exists(info_file):
        mc = MetaConfig(info_file)
        # No hash: one is only meaningful as a comparison against a remote, and there
        # is no remote here - the user handed us the bytes.
        mc.add_asset(target_path, "user")

    return target_path


def update_cache_entry(game_dir_name: str, kind: str, url_path: str,
                       thumb: str | None = None) -> None:
    if _media_cache is None:
        return
    for row in _media_cache:
        if row["game_dir_name"] == game_dir_name:
            row["media"][kind] = url_path
            row.setdefault("thumbs", {})[kind] = thumb
            row.setdefault("thumb_errors", {}).pop(kind, None)
            row[f"has_{kind}"] = url_path is not None
            break
