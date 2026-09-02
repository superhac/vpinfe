"""One read of the library, shared by every view."""

from __future__ import annotations

import logging
import time
from typing import Any

from common.games.asset_registry import ASSET_SPECS
from common.media_specs import media_family, media_label_map
from hubui import media_ownership
from hubui.api import HubClient

logger = logging.getLogger("vpinfe.hubui")

# The cell holds the *word*, never the mark. What a cell is worth filtering and sorting
# on is the state; how it is drawn is the column's business. Holding the drawn mark made
# the text filter match `<span class="hub-mark hub-mark--full">` - so typing "full" found
# rows and typing "All tables" found none.
#
# The words are `media_ownership`'s, which is the module that owns them. The grid used to
# keep its own five - splitting the folder-named file from the fixed-name slot - and that
# split is about our filename conventions rather than anything a reader has a concept
# for, which is the argument that module already makes.


# A video shows the frame at `#t=0.1` - metadata alone paints nothing, and the fragment
# is what makes the browser seek. Muted, or a hover cannot start it. `mediamap.py` uses
# the same two elements for the same reason; the sizing is the cell's.
_ART = "height:52px;max-width:100%;object-fit:contain"
_PICTURE = f'<img src="{{src}}" loading="lazy" style="{_ART}">'
_VIDEO = (f'<video src="{{src}}#t=0.1" preload="metadata" muted playsinline loop'
          f' style="{_ART}"></video>')


def _thumb(game_id: str, kind: str, entry: dict) -> str:
    """The art for a cell, and nothing where the kind has none: audio and rule sheets
    drew a broken icon while every present file was asked to be an `<img>`. The kind's
    name is not the test - `loading` is a video."""
    family = media_family(kind)
    if not entry.get("present") or family not in ("image", "video"):
        return ""
    src = f"/api/v1/games/{game_id}/media/{kind}"
    return (_VIDEO if family == "video" else _PICTURE).format(src=src)


def _glyph(entry: dict) -> str:
    """The word for this cell: what the filter matches and the sort orders on.

    Blank when nothing is there - a sparse matrix stays scannable and a column of
    "Missing" says nothing. A present file whose tier we cannot name still reads as
    present rather than vanishing: an unknown tier is a gap in our knowledge, not an
    absent file.
    """
    if not entry.get("present"):
        return ""
    return media_ownership.noun(entry.get("via"))


def _listed(section: dict, key: str) -> set[str]:
    """One of the hidden-kind lists, however the config layer handed it over - a list
    from JSON, or the comma string the ini holds."""
    value = section.get(key) or []
    if isinstance(value, str):
        value = value.split(",")
    return {str(item).strip() for item in value if str(item).strip()}


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
        self._collections: list[dict[str, Any]] | None = None
        # The by-file lens, read on first use rather than at load: most sessions never
        # switch to it, and it is a second walk of every folder.
        self._table_rows: list[dict[str, Any]] | None = None
        self._vps_entries: dict[str, dict[str, Any]] = {}
        self._vps_releases: dict[str, list[dict[str, Any]]] = {}
        self._overrides: dict[str, dict[str, Any]] = {}
        self._prefs: dict[str, dict[str, Any]] = {}
        self._config_schema: list[dict[str, Any]] | None = None
        self._kept: dict[str, set[str]] | None = None

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

    def placements(self, game_id: str, kind: str) -> dict:
        """Never cached: it reports conflicts, and a stale one would either hide a
        replacement or invent one."""
        return self._client.placements(game_id, kind)

    def media_overrides(self, game_id: str) -> dict:
        """Cached with the media it qualifies: both go stale on the same writes."""
        if game_id not in self._overrides:
            self._overrides[game_id] = self._client.media_overrides(game_id)
        return self._overrides[game_id]

    def media_detail(self, game_id: str, table_id: str | None, kind: str) -> dict:
        """Never cached: it is read when a slot is opened, which is exactly when
        someone has just changed the thing it describes."""
        return self._client.media_detail(game_id, table_id or "", kind)

    def browse_roots(self, game_id: str = "") -> list[dict]:
        return self._client.browse_roots(game_id)

    def browse(self, path: str) -> dict:
        return self._client.browse(path)

    def browsed_file_url(self, path: str) -> str:
        return self._client.browsed_file_url(path)

    def import_media(self, game_id: str, table_id: str | None, kind: str,
                     path: str) -> dict:
        result = self._client.import_media(game_id, table_id or "", kind, path)
        self.forget_media(game_id)
        return result

    def media_sources(self) -> list[dict]:
        return self._client.media_sources()

    def media_offers(self, vps_id: str, kind: str) -> list[dict]:
        return self._client.media_offers(vps_id, kind)

    def search_vps(self, query: str, limit: int = 12) -> list[dict]:
        return self._client.search_vps(query, limit)

    def fetch_media(self, game_id: str, table_id: str | None, kind: str, source: str,
                    vps_id: str, size: str = "") -> dict:
        result = self._client.fetch_media(game_id, table_id or "", kind, source,
                                          vps_id, size)
        self.forget_media(game_id)
        return result

    def retier_media(self, game_id: str, kind: str, from_table: str,
                     to_table: str) -> dict:
        """The file moves tier, so every tier's read is stale - the one it left and the
        one it arrived at both resolve differently now."""
        result = self._client.retier_media(game_id, kind, from_table, to_table)
        self.forget_media(game_id)
        return result

    def displaced_by(self, game_id: str, table_id: str, kind: str,
                     filename: str) -> list[str]:
        """Never cached: it is asked to decide a write, and a stale answer would either
        hide a replacement or invent one."""
        return self._client.displaced_by(game_id, table_id, kind, filename)

    def place_media(self, game_id: str, table_id: str, kind: str,
                    filename: str, data: bytes) -> dict:
        result = self._client.place_media(game_id, table_id, kind, filename, data)
        self.forget_media(game_id)
        return result

    def remove_media(self, game_id: str, table_id: str, kind: str) -> dict:
        result = self._client.remove_media(game_id, table_id, kind)
        self.forget_media(game_id)
        return result

    def set_table_hidden(self, game_id: str, table_id: str, hidden: bool) -> dict:
        result = self._client.set_table_hidden(game_id, table_id, hidden)
        self._forget_tables(game_id)
        return result

    def set_game_rating(self, game_id: str, rating: int) -> None:
        self._client.rate(game_id, rating)
        self._forget_game(game_id)

    def set_table_rating(self, game_id: str, table_id: str, rating: int) -> None:
        self._client.rate_table(game_id, table_id, rating)
        self._forget_tables(game_id)

    def set_game_favorite(self, game_id: str, favorite: bool) -> None:
        self._client.set_favorite(game_id, favorite)
        self._forget_game(game_id)

    def reset_play_record(self, game_id: str, table_id: str = "") -> None:
        self._client.reset_play_record(game_id, table_id)
        if table_id:
            self._forget_tables(game_id)
        else:
            self._forget_game(game_id)

    def _forget_game(self, game_id: str) -> None:
        """Re-read one game in place. The list is held for the page's life, so a write
        that changed a game and left the copy alone would report the old answer until
        something else refreshed it."""
        fresh = self._client.game(game_id)
        for index, game in enumerate(self.games):
            if game.get("id") == game_id:
                self.games[index] = fresh
                return

    def set_default_table(self, game_id: str, table_id: str) -> dict:
        result = self._client.set_default_table(game_id, table_id)
        self._forget_tables(game_id)
        return result

    def launch(self, game_id: str, file: str = "") -> None:
        """Play one of this game's tables. Empty file means the game's default."""
        self._client.launch(game_id, file)

    def config_schema(self) -> list[dict]:
        """Cached for the page's life: the schema is what this build declares, and it
        cannot change while the process is up."""
        if self._config_schema is None:
            self._config_schema = self._client.config_schema()
        return self._config_schema

    def config_values(self) -> dict:
        """Never cached - it is read when a settings page opens, which is exactly when
        somebody may have just changed it from somewhere else."""
        return self._client.config_values()

    def put_config(self, changes: dict) -> dict:
        self._kept = None
        return self._client.put_config(changes)

    def set_game_overrides(self, game_id: str, changes: dict) -> dict:
        """An override changes the name a game sorts under, so the whole list is stale,
        not just this game's row."""
        result = self._client.set_game_overrides(game_id, changes)
        self.load()
        return result

    def set_table_overrides(self, game_id: str, table_id: str, changes: dict) -> dict:
        result = self._client.set_table_overrides(game_id, table_id, changes)
        self._forget_tables(game_id)
        return result

    def _forget_tables(self, game_id: str) -> None:
        """Both lenses read tables, so both go stale when one changes."""
        self.tables.pop(game_id, None)
        self._table_rows = None

    def extract_script(self, game_id: str, table_id: str) -> None:
        """The tables read is now wrong: the sidecar is what the next read reports."""
        self._client.extract_script(game_id, table_id)
        self.tables.pop(game_id, None)
        self._table_rows = None

    def delete_script(self, game_id: str, table_id: str) -> None:
        self._client.delete_script(game_id, table_id)
        self.tables.pop(game_id, None)
        self._table_rows = None

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
        self._overrides.pop(game_id, None)
        self._client.forget_media(game_id)
        for key in [k for k in self.table_media if k[0] == game_id]:
            self.table_media.pop(key, None)

    def table_rows(self) -> list[dict[str, Any]]:
        """The by-file lens as it stands, or empty if nobody has read it yet.

        Deliberately does not fetch. This is read while a page is being drawn, which
        is on the event loop, and an HTTP call there is refused - so the fetch is
        `load_tables`, which a caller runs off the loop before it draws.
        """
        return self._table_rows or []

    def has_table_rows(self) -> bool:
        return self._table_rows is not None

    # --- collections ----------------------------------------------------------
    # Held, because render() runs on the event loop and the client refuses an HTTP call
    # there - the same reason the by-file lens is warmed rather than fetched. Every
    # write drops it, so what comes back next is the change and not the memory of it.

    def has_collections(self) -> bool:
        return self._collections is not None

    def load_collections(self) -> list[dict[str, Any]]:
        """Read the list. Off the event loop, and again after any write."""
        if self._collections is None:
            self._collections = self._client.collections()
        return self._collections

    def filter_axes(self) -> list[dict[str, Any]]:
        """The axes a rule can be written on. Read from core's registry, never listed
        here - section 2.15 makes that registry the only place an axis is named."""
        return self._client.filter_axes()

    def collections(self) -> list[dict[str, Any]]:
        """What `load_collections` last read. Empty before the first read rather than
        fetching here: this is called from render()."""
        return self._collections or []

    def collection_games(self, name: str) -> list[dict[str, Any]]:
        """What a collection resolves to now. For a manual one that is its members
        *that still exist* - a stored member naming a game this library does not have
        resolves to nothing, which is why this can be shorter than `game_count`."""
        return self._client.collection_games(name)

    def collection_members(self, name: str) -> dict:
        """Stored membership and the state of each - the lens an editor needs. Not
        cached: every write in the panel changes it."""
        return self._client.collection_members(name)

    def preview_filters(self, filters: dict | None, limit: int | None = None) -> dict:
        """What a rule would match, storing nothing."""
        return self._client.preview_filters(filters, limit)

    def exclude_from_collection(self, name: str, game_id: str, table: str = "") -> None:
        self._collections = None
        self._client.exclude_from_collection(name, game_id, table)

    def unexclude_from_collection(self, name: str, game_id: str,
                                  table: str | None = None) -> None:
        self._collections = None
        self._client.unexclude_from_collection(name, game_id, table)

    def keep_collection_result(self, name: str) -> dict:
        self._collections = None
        return self._client.keep_collection_result(name)

    def set_collection_image(self, name: str, path: str) -> dict:
        self._collections = None
        return self._client.set_collection_image(name, path)

    def clear_collection_image(self, name: str) -> None:
        self._collections = None
        self._client.clear_collection_image(name)

    def create_collection(self, name: str, filters: dict | None = None) -> dict:
        self._collections = None
        return self._client.create_collection(name, filters=filters)

    def patch_collection(self, name: str, changes: dict) -> dict:
        self._collections = None
        return self._client.patch_collection(name, changes)

    def delete_collection(self, name: str) -> None:
        self._collections = None
        self._client.delete_collection(name)

    def add_to_collection(self, name: str, game_id: str, table: str = "",
                          after_table: str | None = None) -> None:
        self._collections = None
        self._client.add_to_collection(name, game_id, table, after_table)

    def set_member_table(self, name: str, game_id: str, table: str = "",
                         was: str = "") -> None:
        self._collections = None
        self._client.set_member_table(name, game_id, table, was)

    def remove_from_collection(self, name: str, game_id: str,
                               table: str | None = None) -> None:
        self._collections = None
        self._client.remove_from_collection(name, game_id, table)

    def set_collection_order(self, name: str, games: list[str]) -> None:
        self._collections = None
        self._client.set_collection_order(name, games)

    def load_tables(self) -> list[dict[str, Any]]:
        """Read the by-file lens. Off the event loop, once per session."""
        if self._table_rows is None:
            self._table_rows = self._client.all_tables()
        return self._table_rows

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

    def tags(self) -> list[str]:
        """Every tag this library holds, which is the whole vocabulary - there is no
        registry of tags, so a tag no game carries does not exist."""
        seen: set[str] = set()
        for game in self.games:
            seen.update((game.get("user") or {}).get("tags") or [])
        return sorted(seen, key=str.lower)

    def tag_rows(self) -> list[dict[str, Any]]:
        """One row per tag: what it is, how many games carry it, and which tags it may
        be a spelling of.

        `same` is the case- and space-insensitive key. Entry does not fold case on
        purpose, so this is where two spellings of one word become findable - which is
        the whole reason the editor exists rather than being a rename box.
        """
        counts: dict[str, int] = {}
        for game in self.games:
            for tag in (game.get("user") or {}).get("tags") or []:
                counts[tag] = counts.get(tag, 0) + 1
        keys: dict[str, int] = {}
        for tag in counts:
            keys[" ".join(tag.split()).casefold()] = \
                keys.get(" ".join(tag.split()).casefold(), 0) + 1
        return [{"id": tag, "tag": tag, "games": count,
                 "same": " ".join(tag.split()).casefold(),
                 # Only where there is another spelling of it - a mark on every row
                 # would say nothing, and this is the row people are looking for.
                 "duplicate": keys[" ".join(tag.split()).casefold()] > 1}
                for tag, count in sorted(counts.items(), key=lambda kv: kv[0].lower())]

    def vps_search(self, term: str, limit: int = 40) -> list[dict]:
        return self._client.vps_search(term, limit)

    def kept_kinds(self) -> dict[str, set[str]]:
        """Which kinds of file this library collects, as {"media": {...}, "asset": {...}}.

        A library that keeps no toppers should not be told about toppers - not counted
        against them, not shown an empty tile, not offered one from the catalog. This
        answers what to enumerate; it never answers what exists. A file already on disk
        still resolves, and a table that will not launch still will not.

        Derived by subtracting what is hidden from what this build knows, because that
        is the direction that survives an upgrade: a kind added later is in nobody's
        hidden list, so it arrives switched on.

        Held for the page's life and dropped on a write, like the schema beside it: it
        is read on every panel draw and changes only when somebody changes it.
        """
        if self._kept is None:
            general = (self.config_values() or {}).get("general") or {}
            self._kept = {
                "media": set(media_label_map()) - _listed(general, "hidden_media_kinds"),
                "asset": ({spec.kind for spec in ASSET_SPECS}
                          - _listed(general, "hidden_asset_kinds")),
            }
        return self._kept

    def offered_media(self, game_id: str) -> dict[str, int]:
        """How many files the catalog lists for each of our media kinds, counting only
        the ones that are a file. A kind the catalog has only as a folder to browse
        answers zero, which is the whole reason the count is not `listed`."""
        offered: dict[str, int] = {}
        for kind in self._client.vps_state(game_id):
            # Media only. `backglass` names a picture here and a .directb2s among the
            # assets, and it is the second that VPS lists - counted against the tile it
            # would have marked the wrong thing with the wrong number.
            if kind.get("held_in") != "media":
                continue
            for name in (kind.get("ours") or []):
                offered[name] = int(kind.get("obtainable") or 0)
        return offered

    def vps_details(self, game_id: str) -> list[dict]:
        """Where this game's details disagree with the entry it is matched to."""
        return self._client.vps_details(game_id)

    def adopt_vps_details(self, game_id: str) -> None:
        self._client.adopt_vps_details(game_id)
        self._forget_games()

    def set_table_source(self, game_id: str, table_id: str, vps_file_id: str) -> None:
        self._client.set_table_source(game_id, table_id, vps_file_id)
        self._forget_games()

    def vps_releases(self, vps_id: str) -> list[dict]:
        """Held like the entry is: the catalog does not change while the page is open,
        and the picker is reopened per table on a game that has several."""
        if vps_id not in self._vps_releases:
            self._vps_releases[vps_id] = self._client.vps_releases(vps_id)
        return self._vps_releases[vps_id]

    def vps_entry(self, vps_id: str) -> dict:
        """Held for the page's life: the catalog does not change while it is open, and
        a panel redraw would otherwise re-read the same entry on every keystroke."""
        if vps_id not in self._vps_entries:
            self._vps_entries[vps_id] = self._client.vps_entry(vps_id)
        return self._vps_entries[vps_id]

    def merge_tags(self, sources: list[str], into: str) -> int:
        """Rename is one source into a new name; merge is several into one."""
        changed = self._client.merge_tags(sources, into)
        self._forget_games()
        return changed

    def delete_tag(self, tag: str) -> int:
        changed = self._client.delete_tag(tag)
        self._forget_games()
        return changed

    def _forget_games(self) -> None:
        """Re-read the whole list, for a write that touched more of it than one game.

        The list is held for the page's life and `_forget_game` replaces one entry, so a
        sweep across the library left every copy stale - the write landed and the screen
        showed what it had before. The third time that shape has bitten: a cached list
        needs telling whenever something other than it does the writing.
        """
        self.games = self._client.games()

    def set_game_tags(self, game_id: str, tags: list[str]) -> None:
        self._client.set_tags(game_id, tags)
        self._forget_game(game_id)

    def asset_keys(self) -> list[str]:
        """The asset kinds this library reports, in registry order where it knows them.

        The games resource has an asset vocabulary of its own - `settings` for the
        table INI, one `alt_color` covering Serum and VNI - so the keys are taken from
        what it sends rather than from `asset_registry`.
        """
        seen: set[str] = set()
        for game in self.games:
            seen.update(game.get("assets") or {})
        return sorted(seen)

    def kinds(self) -> list[str]:
        seen: set[str] = set()
        for entries in self.media.values():
            seen.update(entries)
        return sorted(seen)

    def preferences(self, scope: str) -> dict[str, Any]:
        """A stored preference, as it stands.

        Cached, and deliberately does not fetch: this is read while a grid is being
        built, which is on the event loop, where an HTTP call is refused. `warm` does
        the reading, off the loop, before anything draws.
        """
        return self._prefs.get(scope) or {}

    def warm(self, *scopes: str) -> None:
        """Read these preferences. Off the event loop, once per session."""
        for scope in scopes:
            if scope not in self._prefs:
                try:
                    self._prefs[scope] = self._client.preferences(scope) or {}
                except Exception:
                    logger.warning("hub ui: could not read %s", scope, exc_info=True)
                    self._prefs[scope] = {}

    def put_preferences(self, scope: str, value: dict[str, Any]) -> None:
        """Write it, and keep the cache honest without a round trip to prove it."""
        self._client.put_preferences(scope, value)
        self._prefs[scope] = value

    def game_rows(self) -> list[dict[str, Any]]:
        rows = []
        for game in self.games:
            game_id = game["id"]
            entries = self.media.get(game_id, {})
            rows.append({
                "id": game_id,
                "name": game.get("name") or "",
                "manufacturer": game.get("manufacturer") or "",
                "year": game.get("year") or "",
                "game_type": game.get("type") or "",
                # No rom or version: both were the default table's reported as the
                # game's, the columns that showed them are gone, and nothing has read
                # them since. HUBUI section 14.2a.
                "table_count": int(game.get("table_count") or 0),
                "rating": game.get("rating") or 0,
                "themes": ", ".join(game.get("themes") or []),
                # One field per asset kind, the same shape as media below. What used
                # to sit here was a single "Assets" count computed from `entries` -
                # the *media* map - so the column read as assets and counted media,
                # beside a Media group showing the same thing per kind.
                **{f"asset_{key}": bool(entry.get("present"))
                   for key, entry in (game.get("assets") or {}).items()},
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
