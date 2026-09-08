"""What the user set on a theme, kept where a theme update cannot reach it.

The values used to be written into the installed theme package, and updating a theme
deletes that package - so every update silently reset every option the user had chosen.
They live in their own directory now, one file per theme, and survive an update, a
reinstall and a delete.

Keyed by folder name rather than by the registry key, because only the folder name is
universal: a local or side-loaded theme has no registry entry, and `[Settings] theme`
stores the folder. For a registry theme the two strings are already the same, since the
installer renames the extracted folder to the key.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

from common.paths import CONFIG_DIR

logger = logging.getLogger("vpinfe.common.theme_options")

USER_OPTIONS_DIR = CONFIG_DIR / "theme_user_options"

VALUES_KEY = "values"
SOURCE_KEY = "source"


def sanitize(folder: str) -> str:
    """A folder name reduced to a safe filename stem, as plugin profiles already do."""
    cleaned = re.sub(r"[^A-Za-z0-9._ -]+", "-", str(folder or "").strip())
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" -.")
    return cleaned[:64]


def path_for(folder: str) -> Path | None:
    stem = sanitize(folder)
    return USER_OPTIONS_DIR / f"{stem}.json" if stem else None


def _read(path: Path) -> dict[str, Any]:
    try:
        with path.open(encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else {}
    except FileNotFoundError:
        return {}
    except (OSError, ValueError):
        logger.warning("Ignoring unreadable theme options at %s", path)
        return {}


def load(folder: str) -> dict[str, Any]:
    """The values the user set for this theme, or {} when they have set none."""
    path = path_for(folder)
    if path is None:
        return {}
    values = _read(path).get(VALUES_KEY)
    return dict(values) if isinstance(values, dict) else {}


def values_in_package(theme_dir: Path) -> dict[str, Any]:
    """The values a pre-3.0 build wrote into the theme's own schema file."""
    for name in ("options.json", "theme.json"):
        schema = _read(theme_dir / name)
        options = schema.get("options")
        if not isinstance(options, list):
            continue
        found = {}
        for option in options:
            if not isinstance(option, dict) or "value" not in option:
                continue
            key = str(option.get("key") or option.get("id") or "").strip()
            if key:
                found[key] = option["value"]
        if found:
            return found
    return {}


def migrate_from_packages(themes_dir: Path) -> list[str]:
    """Lift values out of installed theme packages, once, before anything updates them.

    Must run before `main.py` auto-installs and updates themes, or the release that
    fixes the data loss is the release that causes it: an update deletes the package
    these values are still sitting in. Existing user files are never overwritten - if
    one is there, this theme has already moved.
    """
    moved = []
    if not themes_dir.is_dir():
        return moved
    for theme_dir in sorted(p for p in themes_dir.iterdir() if p.is_dir()):
        folder = theme_dir.name
        path = path_for(folder)
        if path is None or path.exists():
            continue
        values = values_in_package(theme_dir)
        if not values:
            continue
        save(folder, values)
        moved.append(folder)
    if moved:
        logger.info("Moved theme options out of %s installed theme%s: %s",
                    len(moved), "" if len(moved) == 1 else "s", ", ".join(moved))
    return moved


def save(folder: str, values: dict[str, Any], source: str = "") -> Path | None:
    """Replace this theme's values. `source` is recorded, never read.

    It is written because a filename scheme is what would trap us later - changing one is
    a migration, a key inside a JSON object is not.
    """
    path = path_for(folder)
    if path is None:
        raise ValueError(f"Theme folder name is unusable as a filename: {folder!r}")
    existing = _read(path)
    payload = {SOURCE_KEY: source or existing.get(SOURCE_KEY, ""),
               VALUES_KEY: dict(values)}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
                    encoding="utf-8")
    return path
