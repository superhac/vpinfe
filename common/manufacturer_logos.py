"""Manufacturer logos: art keyed by a game's manufacturer, not by the game or a theme.

A logo belongs to hundreds of tables and outlives any one theme, so it lives in a folder
of its own - `media.manufacturer_logos_dir`, defaulting to manufacturer_logos/ under the
config dir - served at /manufacturers/<slug>/logo. Two layers, like table media: default/
holds a downloaded pack, user/ holds the user's own files and wins. Nothing ships in the
tree.

Lookup goes through a slug of the manufacturer name with corporate suffixes dropped, so
"Williams Electronics" and "Williams" find the same file. The exceptions no rule can
cover ("D. Gottlieb & Co.") belong in an alias map: manufacturers.json in either layer,
{"name or slug": "canonical-slug"}, user layer winning.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from pathlib import Path

from common.media_specs import IMAGE_FAMILY

_LAYERS = ("user", "default")
_ALIAS_FILE = "manufacturers.json"
_REFERENCE_FILE = "manufacturers-reference.json"
DEFAULT_FOLDER = "manufacturer_logos"

# Corporate boilerplate that varies between VPSdb entries for one brand.
_SUFFIX_TOKENS = {
    "mfg", "manufacturing", "corp", "corporation", "co", "company",
    "inc", "incorporated", "ltd", "limited", "electronics", "industries",
}

_folder: Path | None = None


def configure_manufacturer_logos(folder: str | Path | None) -> None:
    global _folder
    _folder = Path(folder) if folder else None


def resolve_logos_dir(configured: str, config_dir: str | Path) -> Path:
    return Path(configured) if configured.strip() else Path(config_dir) / DEFAULT_FOLDER


def layer_dirs(folder: Path) -> list[Path]:
    return [folder / layer for layer in _LAYERS]


def manufacturer_slug(name: str) -> str:
    words = re.split(r"[^a-z0-9]+", str(name or "").lower())
    kept = [w for w in words if w and w not in _SUFFIX_TOKENS]
    return "-".join(kept or [w for w in words if w])


def _alias_map(folder: Path) -> dict[str, str]:
    merged: dict[str, str] = {}
    for layer in reversed(_LAYERS):  # default first, user overwrites
        try:
            data = json.loads((folder / layer / _ALIAS_FILE).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(data, dict):
            # Empty values are placeholders, not aliases - honoring one would
            # erase a working slug.
            merged.update({manufacturer_slug(k): str(v)
                           for k, v in data.items()
                           if isinstance(v, str) and v.strip()})
    return merged


def manufacturer_logo_file(slug: str) -> Path | None:
    """The file a slug's logo is, user layer first, or None."""
    if _folder is None or not slug or slug != manufacturer_slug(slug):
        return None
    for layer in _LAYERS:
        for ext in IMAGE_FAMILY:
            candidate = _folder / layer / f"{slug}{ext}"
            if candidate.is_file():
                return candidate
    return None


def _entry(name: str, aliases: dict[str, str]) -> dict:
    slug = manufacturer_slug(name)
    target = manufacturer_slug(aliases.get(slug, "")) or None
    effective = target or slug
    found = manufacturer_logo_file(effective) if effective else None
    return {"name": name, "slug": slug, "aliased_to": target,
            "logo": f"/manufacturers/{effective}/logo" if found else None}


def manufacturer_logo_url(name: str) -> str | None:
    """The URL a manufacturer's logo is served at, or None when there is no logo."""
    if _folder is None or not str(name or "").strip():
        return None
    return _entry(name, _alias_map(_folder))["logo"]


def manufacturer_report(names: Iterable[object]) -> list[dict]:
    """One row per distinct name: slug, effective alias, resolved logo.

    This is the lookup made visible - the answer to "what filename would this
    manufacturer find" without running the algorithm in your head, and the only
    way to see that a pack alias is redirecting past your own file.
    """
    aliases = _alias_map(_folder) if _folder is not None else {}
    distinct = sorted({str(n).strip() for n in names if str(n or "").strip()},
                      key=str.lower)
    return [_entry(name, aliases) for name in distinct]


def vps_manufacturer_names(vpsdb_path: str | Path) -> list[str]:
    """Every distinct manufacturer string in a cached vpsdb.json."""
    try:
        data = json.loads(Path(vpsdb_path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    if not isinstance(data, list):
        return []
    return sorted({str(t.get("manufacturer", "")).strip() for t in data
                   if isinstance(t, dict) and str(t.get("manufacturer", "")).strip()},
                  key=str.lower)


def write_manufacturer_reference(names: Iterable[object]) -> Path | None:
    """Generate manufacturers-reference.json beside the two layers.

    The reference is for people: open it to learn what slug a name computes,
    what an alias currently redirects, and which names have no logo yet. The
    lookup never reads it, so it can never break anything.
    """
    if _folder is None:
        return None
    report = manufacturer_report(names)
    if not report:
        return None
    path = _folder / _REFERENCE_FILE
    payload = {
        "about": ("Generated by VPinFE from VPSdb. Do not edit - regenerated on "
                  "sync, and never read by the logo lookup. To alias a name, "
                  "copy it into manufacturers.json in the user/ folder."),
        "manufacturers": report,
    }
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    except OSError:
        return None
    return path
