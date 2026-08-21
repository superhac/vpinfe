"""Who put a file in a game folder, as far as anyone recorded.

Not the same question as tier. Tier says why a file is the one being used and is derived
from its name every run; origin can only be known because something wrote it down. Art
hand-placed at the fixed name reads as tier `default` exactly like a download.

The ledger is the only source cheap enough per request. Proving a file is the one
vpinmediadb publishes means hashing it, which belongs in a pass that can take its time.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

logger = logging.getLogger("vpinfe.common.games.asset_origin")

ASSETS_KEY = "assets"
UNKNOWN = "unknown"


def _key(game_dir: Path, path: Path) -> str:
    """The ledger's own key shape: folder-relative, forward slashes."""
    try:
        return os.path.relpath(str(path), str(game_dir)).replace(os.sep, "/")
    except ValueError:
        return path.name


def ledger(game_dir: str | Path) -> dict[str, str]:
    """Every recorded path in this folder, and the host that placed it. Read straight
    from the file: MetaConfig migrates and can rewrite, and this wants one section."""
    game_dir = Path(game_dir)
    info = game_dir / f"{game_dir.name}.info"
    try:
        data = json.loads(info.read_text(encoding="utf-8"))
    except Exception:
        return {}
    entries = data.get(ASSETS_KEY)
    if not isinstance(entries, dict):
        return {}
    out = {}
    for key, entry in entries.items():
        source = (entry or {}).get("source") if isinstance(entry, dict) else None
        host = str((source or {}).get("host", "") or "").strip()
        if host:
            out[str(key)] = host
    return out


def origin_of(recorded: dict[str, str], game_dir: str | Path, path: Path | None) -> str:
    """Who placed this file, or "unknown" - a real answer, not a gap. A copied folder,
    a regenerated .info or art fetched with another tool all leave no record."""
    if path is None:
        return ""
    return recorded.get(_key(Path(game_dir), path), UNKNOWN)
