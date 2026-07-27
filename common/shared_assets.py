"""Shared assets: files keyed by metadata, not by table or theme.

A manufacturer logo belongs to hundreds of tables and outlives any one theme,
so it lives in its own root - [Settings] assetsdir, defaulting to assets/
under the config dir - served at /assets/. Two layers, like table media:
manufacturers/default/ holds a downloaded pack, manufacturers/user/ holds the
user's own files and wins. Nothing ships in the tree.

Lookup goes through a slug of the manufacturer name with corporate suffixes
dropped, so "Williams Electronics" and "Williams" find the same file. The
exceptions no rule can cover ("D. Gottlieb & Co.") belong in an alias map:
manufacturers.json in either layer, {"name or slug": "canonical-slug"},
user layer winning.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from common.media_paths import IMAGE_FAMILY

_MANUFACTURER_DIR = "manufacturers"
_LAYERS = ("user", "default")
_ALIAS_FILE = "manufacturers.json"

# Corporate boilerplate that varies between VPSdb entries for one brand.
_SUFFIX_TOKENS = {
    "mfg", "manufacturing", "corp", "corporation", "co", "company",
    "inc", "incorporated", "ltd", "limited", "electronics", "industries",
}

_assets_dir: Path | None = None


def configure_shared_assets(assets_dir: str | Path | None) -> None:
    global _assets_dir
    _assets_dir = Path(assets_dir) if assets_dir else None


def resolve_assets_dir(configured: str, config_dir: str | Path) -> Path:
    return Path(configured) if configured.strip() else Path(config_dir) / "assets"


def manufacturer_slug(name: str) -> str:
    words = re.split(r"[^a-z0-9]+", str(name or "").lower())
    kept = [w for w in words if w and w not in _SUFFIX_TOKENS]
    return "-".join(kept or [w for w in words if w])


def _alias_map(assets_dir: Path) -> dict[str, str]:
    merged: dict[str, str] = {}
    for layer in reversed(_LAYERS):  # default first, user overwrites
        path = assets_dir / _MANUFACTURER_DIR / layer / _ALIAS_FILE
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(data, dict):
            merged.update({manufacturer_slug(k): str(v)
                           for k, v in data.items() if isinstance(v, str)})
    return merged


def manufacturer_logo_web_path(name: str) -> str | None:
    """The /assets/-relative web path of a manufacturer's logo, or None."""
    if _assets_dir is None or not str(name or "").strip():
        return None
    slug = manufacturer_slug(name)
    slug = manufacturer_slug(_alias_map(_assets_dir).get(slug, slug))
    if not slug:
        return None
    for layer in _LAYERS:
        for ext in IMAGE_FAMILY:
            candidate = _assets_dir / _MANUFACTURER_DIR / layer / f"{slug}{ext}"
            if candidate.is_file():
                return f"/assets/{_MANUFACTURER_DIR}/{layer}/{slug}{ext}"
    return None
