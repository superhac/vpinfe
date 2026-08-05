"""Shared assets: files keyed by metadata, not by game or theme.

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

from common.media_specs import IMAGE_FAMILY

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
            # Empty values are placeholders, not aliases - honoring one would
            # erase a working slug.
            merged.update({manufacturer_slug(k): str(v)
                           for k, v in data.items()
                           if isinstance(v, str) and v.strip()})
    return merged


def _probe_layers(slug: str) -> str | None:
    if _assets_dir is None:
        return None
    for layer in _LAYERS:
        for ext in IMAGE_FAMILY:
            candidate = _assets_dir / _MANUFACTURER_DIR / layer / f"{slug}{ext}"
            if candidate.is_file():
                return f"/assets/{_MANUFACTURER_DIR}/{layer}/{slug}{ext}"
    return None


def _entry(name: str, aliases: dict[str, str]) -> dict:
    slug = manufacturer_slug(name)
    target = manufacturer_slug(aliases.get(slug, "")) or None
    effective = target or slug
    return {"name": name, "slug": slug, "aliased_to": target,
            "logo": _probe_layers(effective) if effective else None}


def manufacturer_logo_web_path(name: str) -> str | None:
    """The /assets/-relative web path of a manufacturer's logo, or None."""
    if _assets_dir is None or not str(name or "").strip():
        return None
    return _entry(name, _alias_map(_assets_dir))["logo"]


def manufacturer_report(names) -> list[dict]:
    """One row per distinct name: slug, effective alias, resolved logo.

    This is the lookup made visible - the answer to "what filename would this
    manufacturer find" without running the algorithm in your head, and the only
    way to see that a pack alias is redirecting past your own file.
    """
    aliases = _alias_map(_assets_dir) if _assets_dir is not None else {}
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


def write_manufacturer_reference(names) -> Path | None:
    """Generate manufacturers-reference.json beside the alias maps.

    The reference is for people: open it to learn what slug a name computes,
    what an alias currently redirects, and which names have no logo yet. The
    lookup never reads it, so it can never break anything.
    """
    if _assets_dir is None:
        return None
    report = manufacturer_report(names)
    if not report:
        return None
    path = _assets_dir / _MANUFACTURER_DIR / "manufacturers-reference.json"
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
