"""What a file is, judged by its name: which media kind, or none of them."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from common.games.media_service import IMAGE_EXTENSIONS
from common.media_specs import MEDIA_SPECS, media_filename_map

logger = logging.getLogger("vpinfe.manager.asset_registry")

# Archive containers are opened and inspected, never classified as a bare file.
ARCHIVE_EXTENSIONS = frozenset({".zip", ".vpxz", ".rar", ".7z"})

VIDEO_EXTENSIONS = frozenset({".mp4"})
AUDIO_EXTENSIONS = frozenset({".mp3", ".ogg"})
# Deliberately NOT folded into MEDIA_EXTENSIONS: a bare .txt must never classify
# as media - ROM and altsound archives carry alias.txt and friends. Doc
# extensions only match through an exact canonical name or a spec token.
DOC_EXTENSIONS = frozenset({".pdf", ".md", ".txt", ".html"})
MEDIA_EXTENSIONS = frozenset(IMAGE_EXTENSIONS) | VIDEO_EXTENSIONS | AUDIO_EXTENSIONS


@dataclass(frozen=True)
class AssetSpec:
    kind: str
    label: str
    icon: str
    extensions: tuple[str, ...]     # lowercase; () for marker/folder-detected kinds
    requires_game: bool
    requires_rom: bool
    allow_multiple: bool


def is_readme(name: str) -> bool:
    """Narrow on purpose: readme* (any extension) and .nfo. Never a blanket
    .txt - ROM and altsound archives carry alias.txt and its kin."""
    lower = name.lower()
    return lower.startswith("readme") or lower.endswith(".nfo")


ASSET_SPECS = (
    AssetSpec("table", "Table", "casino", (".vpx",), False, False, False),
    AssetSpec("game_info", "Metadata", "description", (), True, False, False),
    AssetSpec("backglass", "Backglass", "wallpaper", (".directb2s",), True, False, False),
    AssetSpec("ini", "Table INI", "tune", (".ini",), True, False, False),
    # A patch is a delta against one exact base table, not an installable artifact.
    # requires_game is doing real work here: applying it without the right base
    # produces a corrupt file rather than an error.
    AssetSpec("patch", "Table Patch", "difference", (".dif",), True, False, True),
    AssetSpec("rom", "ROM", "memory", (), True, False, True),
    AssetSpec("altcolor_serum", "Serum Color", "palette", (".crz", ".cromc"), True, True, True),
    AssetSpec("altcolor_vni", "VNI/PAL Color", "palette", (".vni", ".pal", ".pac"), True, True, True),
    AssetSpec("altsound", "AltSound", "volume_up", (), True, True, False),
    AssetSpec("pup_pack", "PUP Pack", "video_library", (), True, False, False),
    AssetSpec("music", "Music", "music_note", (), True, False, False),
    AssetSpec("media", "Media", "image", tuple(sorted(MEDIA_EXTENSIONS)), True, False, True),
    AssetSpec("readme", "Author's Notes", "description", (), True, False, True),
)

_SPECS_BY_KIND = {spec.kind: spec for spec in ASSET_SPECS}

# Canonical media filenames (bg.png, dmd.mp4, audio.mp3, ...) -> media kind.
_MEDIA_FILENAME_TO_KIND = {filename: kind for kind, filename in media_filename_map("table").items()}

# Spec tokens ("(Wheel) Name.png") -> media kind, image and video resolved by
# extension. Explicit, so spec-named files import by rule rather than by the
# keyword fallback happening to contain the right word.
def _bucket(ext: str) -> str:
    if ext in VIDEO_EXTENSIONS:
        return "video"
    if ext in AUDIO_EXTENSIONS:
        return "audio"
    if ext in DOC_EXTENSIONS:
        return "doc"
    return "image"


_TOKEN_TO_KIND: dict[str, dict[str, str]] = {}
for _spec in MEDIA_SPECS:
    if _spec.token:
        for _token in (_spec.token,) + _spec.alt_tokens:
            for _ext in _spec.family:
                _TOKEN_TO_KIND.setdefault(_token.lower(), {}).setdefault(
                    _bucket(_ext), _spec.kind)

# Keyword-in-stem fallbacks when a media file is not named canonically.
# Ordered; realdmd is handled ahead of this table so the scoreview keyword never claims a
# realdmd file. The keyword people actually type stays as it is - it is what they name
# files - while the slot it fills is scoreview.
_MEDIA_KEYWORDS: tuple[tuple[tuple[str, ...], str, str | None], ...] = (
    (("wheel",), "wheel", None),
    (("logo",), "logo", None),
    (("backglass", "b2s"), "backglass", "backglass_video"),
    (("dmd",), "scoreview", "scoreview_video"),
    (("playfield", "table", "pf"), "playfield", "playfield_video"),
    (("cabinet", "cab"), "cab", None),
    (("flyer",), "flyer", None),
    (("fss",), "playfield_fss", None),
)


def spec_for(kind: str) -> AssetSpec:
    """Return the AssetSpec for a kind key, raising KeyError if unknown."""
    return _SPECS_BY_KIND[kind]


def classify_bare_extension(filename: str) -> AssetSpec | None:
    """Classify a single non-archive file by its extension, or None if unrecognized."""
    ext = Path(filename).suffix.lower()
    if not ext or ext in ARCHIVE_EXTENSIONS:
        return None
    for spec in ASSET_SPECS:
        if ext in spec.extensions:
            return spec
    return None


def match_media_kind(filename: str) -> str | None:
    """Resolve a media file to its canonical media kind (backglass, wheel, ...), or None.

    Exact canonical filenames win; otherwise a keyword in the stem plus the extension
    family (image vs video vs audio) decides the slot.
    """
    ext = Path(filename).suffix.lower()
    if ext not in MEDIA_EXTENSIONS and ext not in DOC_EXTENSIONS:
        return None

    name = Path(filename).name.lower()
    if name in _MEDIA_FILENAME_TO_KIND:
        return _MEDIA_FILENAME_TO_KIND[name]

    # Spec naming: "(Token) Whatever.ext". The token decides the kind, the
    # extension family decides image vs video.
    if name.startswith("(") and ") " in name:
        token = name.split(") ", 1)[0] + ")"
        kinds = _TOKEN_TO_KIND.get(token)
        if kinds:
            family = _bucket(ext)
            hit = kinds.get(family)
            if hit:
                return hit

    # Past the explicit names, a doc extension never matches: the keyword
    # fallback on .txt would misfile alias.txt and its kin.
    if ext in DOC_EXTENSIONS:
        return None

    stem = Path(filename).stem.lower()

    if ext in AUDIO_EXTENSIONS:
        # audio is the only audio slot, so any recognized audio file lands there.
        return "audio"

    if "realdmd" in stem or "real dmd" in stem or "real-dmd" in stem:
        if ext in IMAGE_EXTENSIONS:
            return "real_dmd_color" if "color" in stem else "real_dmd"
        return None

    for keywords, image_kind, video_kind in _MEDIA_KEYWORDS:
        if any(kw in stem for kw in keywords):
            if ext in VIDEO_EXTENSIONS:
                return video_kind
            if ext in IMAGE_EXTENSIONS:
                return image_kind
    return None
