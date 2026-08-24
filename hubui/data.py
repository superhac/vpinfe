"""One read of the library, shared by every view."""

from __future__ import annotations

import logging
import time
from typing import Any

from hubui.api import HubClient

logger = logging.getLogger("vpinfe.hubui")

# One character per resolution tier, so a cell says *why* this file is the one being
# used, not merely that something is. Filled reads as more specific. Blank is missing,
# because a sparse matrix is scannable and a full one is not.
TIER_GLYPHS = {
    "table": "\u25cf",      # this table's own file
    "game": "\u25d0",       # named for the folder, shared by the game's tables
    "default": "\u25cb",    # the fixed-name slot, where vpinmediadb writes
}
SET_GLYPH = "\u25c8"
FALLBACK_GLYPH = "\u25cc"

TIER_LEGEND = "\u25cf table  \u25d0 game  \u25cb default  \u25c8 set  \u25cc borrowed"


def _thumb(game_id: str, kind: str, entry: dict) -> str:
    if not entry.get("present"):
        return ""
    return (f'<img src="/api/v1/games/{game_id}/media/{kind}" loading="lazy" '
            f'style="height:52px;max-width:100%;object-fit:contain">')


def _glyph(entry: dict) -> str:
    if not entry.get("present"):
        return ""
    tier = entry.get("via") or ""
    if tier.startswith("set:"):
        return SET_GLYPH
    if tier.startswith("fallback:"):
        return FALLBACK_GLYPH
    # A present file whose tier we cannot name still shows as present rather than
    # vanishing - an unknown tier is a gap in our knowledge, not an absent file.
    return TIER_GLYPHS.get(tier, "\u2713")


class Library:
    """Games, their media and their tables, fetched once per page load.

    Games and Assets are the same data shaped two ways, so they share this rather than
    each paying the per-game media call. Nothing here is cached across page loads: a
    hub whose library changed underneath us would otherwise serve a stale grid.
    """

    def __init__(self, client: HubClient) -> None:
        self._client = client
        self.games: list[dict[str, Any]] = []
        self.media: dict[str, dict[str, Any]] = {}
        self.table_media: dict[tuple[str, str], dict[str, Any]] = {}
        self.tables: dict[str, list[dict[str, Any]]] = {}

    def load(self) -> None:
        started = time.perf_counter()
        self.games = self._client.games()
        for game in self.games:
            self.media[game["id"]] = self._client.media(game["id"])
        logger.info("hub ui: read %d games in %.2fs", len(self.games),
                    time.perf_counter() - started)

    def media_for(self, game_id: str, table_id: str | None) -> dict[str, Any]:
        """The shared media, or one build's. `None` is the game, which is already read.

        Cached per build because the lens is a control someone flips back and forth,
        and a folder holds a handful of tables at most.
        """
        if not table_id:
            # Fetched when missing rather than read blindly, so dropping the entry
            # after a write is all invalidation has to do.
            if game_id not in self.media:
                self.media[game_id] = self._client.media(game_id)
            return self.media[game_id]
        key = (game_id, table_id)
        if key not in self.table_media:
            self.table_media[key] = self._client.table_media(game_id, table_id)
        return self.table_media[key]

    def place_media(self, game_id: str, table_id: str, kind: str,
                    filename: str, data: bytes) -> dict:
        result = self._client.place_media(game_id, table_id, kind, filename, data)
        self.forget_media(game_id)
        return result

    def remove_media(self, game_id: str, table_id: str, kind: str) -> dict:
        result = self._client.remove_media(game_id, table_id, kind)
        self.forget_media(game_id)
        return result

    def forget_table(self, game_id: str, table_id: str) -> dict:
        """Drop a gone table's record. The tables list is what changes, and the media
        cache with it - a per-build read keyed on that table is now describing nothing."""
        result = self._client.forget_table(game_id, table_id)
        self.tables.pop(game_id, None)
        self.forget_media(game_id)
        return result

    def forget_media(self, game_id: str) -> None:
        """Every tier, not just the one written: a shared file changes what each build
        resolves, so leaving the per-build reads cached would show the old answer."""
        self.media.pop(game_id, None)
        self._client.forget_media(game_id)
        for key in [k for k in self.table_media if k[0] == game_id]:
            self.table_media.pop(key, None)

    def tables_for(self, game_id: str) -> list[dict[str, Any]]:
        """Fetched when something asks, not with the library.

        Prefetching tables doubled the read to 294 requests for 147 games, and only the
        workbench - one game at a time - ever needs them.
        """
        if game_id not in self.tables:
            self.tables[game_id] = self._client.tables(game_id)
        return self.tables[game_id]

    def kinds_present(self) -> list[str]:
        """Kinds any game in this library actually has.

        Seven of the twenty are empty across the whole testbed, and a column that is
        blank for every row costs width and tells nobody anything. The user can still
        add them back - the column picker holds every kind, this only sets the default.
        """
        seen: set[str] = set()
        for entries in self.media.values():
            seen.update(kind for kind, entry in entries.items() if entry.get("present"))
        return [kind for kind in self.kinds() if kind in seen]

    def kinds(self) -> list[str]:
        seen: set[str] = set()
        for entries in self.media.values():
            seen.update(entries)
        return sorted(seen)

    def game_rows(self) -> list[dict[str, Any]]:
        rows = []
        for game in self.games:
            game_id = game["id"]
            entries = self.media.get(game_id, {})
            present = sum(1 for entry in entries.values() if entry.get("present"))
            rows.append({
                "id": game_id,
                "name": game.get("name") or "",
                "manufacturer": game.get("manufacturer") or "",
                "year": game.get("year") or "",
                "game_type": game.get("type") or "",
                "rom": game.get("rom") or "",
                "version": game.get("version") or "",
                "rating": game.get("rating") or 0,
                "themes": ", ".join(game.get("themes") or []),
                "assets": f"{present}/{len(entries)}" if entries else "-",
                # Sortable companion to `assets`, which is a label and sorts as text.
                "coverage": present,
                # One field per kind, so media reads as columns over game rows. Blank
                # rather than a cross when absent: a sparse matrix stays scannable,
                # a full one does not.
                **{f"media_{kind}": _glyph(entry) for kind, entry in entries.items()},
                # The same cell, drawn as a picture. Both live on the row so switching
                # renderer is a redraw rather than a reload - which is the whole point
                # of separating what a field holds from how it is shown.
                **{f"thumb_{kind}": _thumb(game_id, kind, entry)
                   for kind, entry in entries.items()},
            })
        return rows
