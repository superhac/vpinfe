"""Every table in the library, as its own lens on it.

A game's row cannot tell its tables apart - that is the whole of what this is for. A
folder holding four .vpx files collapses to one row under Games, and the questions that
are actually about a file (which is the default, which is out of date, which has its
own art) have nowhere to be asked.

Not a replacement for the game lens. Identity and shared media are the game's, and
saying so four times over is worse than saying it once. These are peers: the library
seen by folder, or seen by launchable file.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Query

from . import models, scopes
from .auth import requires

logger = logging.getLogger("vpinfe.httpapi.tables")

router = APIRouter(prefix="/tables", tags=["tables"])


@router.get("", summary="Every table in the library",
            dependencies=[requires(scopes.GAMES_READ)])
def list_tables(limit: int = Query(0, ge=0), offset: int = Query(0, ge=0),
                game: str = Query("")) -> models.TableRowList:
    """One row per launchable file, each carrying the game it belongs to.

    The game's name and maker ride along rather than being a lookup the caller has to
    make: this list is read to be shown, and a table named only by its filename is the
    thing the games lens already fails at.
    """
    from .games import _catalog, _tables, game_to_row

    found: list[dict] = []
    for game_id, entry in _catalog().items():
        if game or "":
            if game != game_id:
                continue
        row = game_to_row(entry)
        meta = getattr(entry, "meta_config", {}) or {}
        info = meta.get("Info") if isinstance(meta.get("Info"), dict) else {}
        for table in _tables(entry, row):
            if not table.get("id"):
                continue
            found.append({
                "id": table["id"],
                "game_id": game_id,
                "game": str(info.get("Name", "") or row.get("name", "") or ""),
                "manufacturer": str(info.get("Manufacturer", "") or ""),
                "year": str(info.get("Year", "") or ""),
                "filename": table.get("filename") or "",
                "version": table.get("version") or "",
                "authors": table.get("authors") or [],
                # The rom this file actually resolves to, alias followed. One of the
                # few things that genuinely differs between two tables of one game.
                "rom": str((table.get("dependencies") or {})
                           .get("pinmame", {}).get("effective", "") or ""),
                "default": bool(table.get("default")),
                "hidden": bool(table.get("hidden")),
                "available": bool(table.get("available")),
                "absent_since": table.get("absent_since"),
                "app": table.get("app") or "",
            })

    found.sort(key=lambda item: (item["game"].lower(), item["filename"].lower()))
    total = len(found)
    window = found[offset:offset + limit] if limit else found[offset:]
    return {"total": total, "offset": offset, "count": len(window), "tables": window}
