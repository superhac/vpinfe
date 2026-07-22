from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from common.media_paths import media_filename_map
from managerui.services.media_service import IMAGE_EXTENSIONS


logger = logging.getLogger("vpinfe.manager.asset_registry")

# Archive containers are opened and inspected, never classified as a bare file.
ARCHIVE_EXTENSIONS = frozenset({".zip", ".vpxz", ".rar", ".7z"})

VIDEO_EXTENSIONS = frozenset({".mp4"})
AUDIO_EXTENSIONS = frozenset({".mp3"})
MEDIA_EXTENSIONS = frozenset(IMAGE_EXTENSIONS) | VIDEO_EXTENSIONS | AUDIO_EXTENSIONS


@dataclass(frozen=True)
class AssetSpec:
    key: str
    label: str
    icon: str
    extensions: tuple[str, ...]     # lowercase; () for marker/folder-detected kinds
    requires_table: bool
    requires_rom: bool
    allow_multiple: bool


ASSET_SPECS = (
    AssetSpec("table", "Table", "casino", (".vpx",), False, False, False),
    AssetSpec("table_info", "Metadata", "description", (), True, False, False),
    AssetSpec("backglass", "Backglass", "wallpaper", (".directb2s",), True, False, False),
    AssetSpec("ini", "Table INI", "tune", (".ini",), True, False, False),
    AssetSpec("rom", "ROM", "memory", (), True, False, True),
    AssetSpec("altcolor_serum", "Serum Color", "palette", (".crz",), True, True, True),
    AssetSpec("altcolor_vni", "VNI/PAL Color", "palette", (".vni", ".pal", ".pac"), True, True, True),
    AssetSpec("altsound", "AltSound", "volume_up", (), True, True, False),
    AssetSpec("pup_pack", "PUP Pack", "video_library", (), True, False, False),
    AssetSpec("music", "Music", "music_note", (), True, False, False),
    AssetSpec("media", "Media", "image", tuple(sorted(MEDIA_EXTENSIONS)), True, False, True),
)

_SPECS_BY_KEY = {spec.key: spec for spec in ASSET_SPECS}

# Canonical media filenames (bg.png, dmd.mp4, audio.mp3, ...) -> media key.
_MEDIA_FILENAME_TO_KEY = {filename: key for key, filename in media_filename_map("table").items()}

# Keyword-in-stem fallbacks when a media file is not named canonically.
# Ordered; realdmd is handled ahead of this table so "dmd" never claims a realdmd file.
_MEDIA_KEYWORDS: tuple[tuple[tuple[str, ...], str, str | None], ...] = (
    (("wheel", "logo"), "wheel", None),
    (("backglass", "b2s"), "bg", "bg_video"),
    (("dmd",), "dmd", "dmd_video"),
    (("playfield", "table", "pf"), "table", "table_video"),
    (("cabinet", "cab"), "cab", None),
    (("flyer",), "flyer", None),
    (("fss",), "fss", None),
)


def spec_for(key: str) -> AssetSpec:
    """Return the AssetSpec for a kind key, raising KeyError if unknown."""
    return _SPECS_BY_KEY[key]


def classify_bare_extension(filename: str) -> AssetSpec | None:
    """Classify a single non-archive file by its extension, or None if unrecognized."""
    ext = Path(filename).suffix.lower()
    if not ext or ext in ARCHIVE_EXTENSIONS:
        return None
    for spec in ASSET_SPECS:
        if ext in spec.extensions:
            return spec
    return None


def match_media_key(filename: str) -> str | None:
    """Resolve a media file to its canonical media slot key (bg, wheel, ...), or None.

    Exact canonical filenames win; otherwise a keyword in the stem plus the extension
    family (image vs video vs audio) decides the slot.
    """
    ext = Path(filename).suffix.lower()
    if ext not in MEDIA_EXTENSIONS:
        return None

    name = Path(filename).name.lower()
    if name in _MEDIA_FILENAME_TO_KEY:
        return _MEDIA_FILENAME_TO_KEY[name]

    stem = Path(filename).stem.lower()

    if ext in AUDIO_EXTENSIONS:
        # audio is the only audio slot, so any recognized audio file lands there.
        return "audio"

    if "realdmd" in stem or "real dmd" in stem or "real-dmd" in stem:
        if ext in IMAGE_EXTENSIONS:
            return "realdmd_color" if "color" in stem else "realdmd"
        return None

    for keywords, image_key, video_key in _MEDIA_KEYWORDS:
        if any(kw in stem for kw in keywords):
            if ext in VIDEO_EXTENSIONS:
                return video_key
            if ext in IMAGE_EXTENSIONS:
                return image_key
    return None
