"""The library seen by media file rather than by game.

Its own subject, not a lens on the games grid. A matrix of games against kinds answers
coverage well and can hold one fact per cell; a file has several, and the question
"everything a stranger placed" spans twenty columns there and one here.

The row that matters is the one with nothing in it. A selection under Games is a
selection of games whatever column you filtered, so the kind is never part of what a
bulk action is given - which is why filling gaps in bulk has had nowhere to live.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from nicegui import run, ui

from common.media_specs import media_label_map
from console import confirm, grid, media_ownership, views
from console.api import ApiClient
from console.games import view_control

logger = logging.getLogger("vpinfe.console.media")

SCOPE = "console.media.columns"

_ORPHAN = media_ownership.tier_for(media_ownership.ORPHAN).noun
_UNUSED = media_ownership.tier_for(media_ownership.UNUSED).noun
_MISSING = media_ownership.tier_for(media_ownership.MISSING).noun

# Why a file on disk is not the one being used, blank while it is doing its job. The
# blank is a choice like any other in the funnel, and it needs a word there because
# "match the empty ones" is not something a checkbox can say by being unlabelled.
_REASON = {media_ownership.ORPHAN: _ORPHAN, media_ownership.UNUSED: _UNUSED}
_REASON_CHOICES = ([{"value": "", "label": "In use"}]
                   + [{"value": word, "label": word}
                      for word in (_MISSING, _ORPHAN, _UNUSED)])

_SOURCE_CHOICES = ([{"value": name, "label": name}
                    for name in media_ownership.source_names()]
                   + [{"value": "", "label": "No file"}])


def _standing_in(via: str) -> str:
    """What is covering an empty slot on the cabinet, said short.

    Worth a column because this lens reads "Missing" against a machine that is visibly
    showing something, and both are true: the file belongs to another slot.
    """
    if via.startswith("set:"):
        return f"Set: {via.split(':', 1)[1]}"
    if via.startswith("fallback:"):
        kind = via.split(":", 1)[1]
        return media_label_map().get(kind, kind)
    return ""



def rows(found: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The API's media, flattened for a grid.

    Three facts kept apart, because one column carrying two of them is what made a row
    read as a contradiction: `used_by` counts tables and only ever describes a file,
    `reason` speaks only when a file is not the one being used, and `path` says which
    file, name and folder together.
    """
    return [{**row,
             # One path, not a name and a folder: `medias/` or the game folder is two
             # values across a whole library, which is a column that says the same
             # thing on nearly every row.
             "path": row.get("path") or "",
             "used_by": row.get("serves"),
             "reason": _REASON.get(str(row.get("via") or ""),
                                   "" if row.get("present") else _MISSING),
             "source": media_ownership.source_name(str(row.get("origin") or "")),
             "match": str(row.get("matched_to") or ""),
             "covered_by": _standing_in(str(row.get("standing_in") or ""))}
            for row in found]


# The groups the column picker offers, the way Games and Tables already group theirs.
_FILE = "File"
_GAME = "Game"
_SOURCE = "Source"

COLUMNS: list[dict[str, Any]] = [
    grid.column("game", "Game", 200, pinned="left", group=_GAME,
                help="The game folder this file belongs to."),
    grid.column("label", "Kind", 160, group=_FILE,
                help="Which of the twenty media kinds this row is about - the wheel,\n"
                     "the playfield, the backglass and so on."),
    grid.column("used_by", "Used by", type="numericColumn", group=_FILE,
                help="How many of this game's tables actually load this file.\n\n"
                     "0 - nothing loads it.\n"
                     "Blank - there is no file to load."),
    grid.column("reason", "Unused reason", 150, group=_FILE,
                **grid.choice_filter(_REASON_CHOICES),
                help="Why this file is not the one being used. Blank while it is.\n\n"
                     "Missing - no file at all.\n"
                     "Orphan - named for a table this folder does not have, so "
                     "nothing will ever look for it again. Safe to delete.\n"
                     "Unused - correctly named, but something more specific wins. "
                     "It is the fallback, and it resolves again the moment the file "
                     "covering it goes."),
    grid.column("table_file", "Table", 200, group=_FILE,
                help="The .vpx this file is named for.\n\n"
                     "Blank - named for the folder, so every table falls back to it."),
    grid.column("path", "Path", 300, group=_FILE,
                help="Where the file sits, relative to the game folder.\n"
                     "Art placed since 2.x lives in medias/."),
    grid.column("source", "Source", 165, group=_SOURCE,
                **grid.choice_filter(_SOURCE_CHOICES),
                help="Who put the file here, as far as anything recorded it.\n\n"
                     "Unknown - nothing recorded it. True of anything placed before "
                     "the ledger or by another tool, which is most files.\n"
                     "Blank - there is no file."),
    grid.column("match", "Match", 140, group=_SOURCE,
                help="The VPS file somebody said this art is for.\n\n"
                     "Blank - nobody has said, which is not the same as there being "
                     "no match to make."),
    grid.column("covered_by", "Covered by", 130, group=_FILE,
                help="What the cabinet shows for this kind while there is no file of "
                     "its own - a set, or another kind standing in.\n"
                     "That file belongs to the other kind, which is why this row "
                     "still reads as missing."),
    grid.column("manufacturer", "Manufacturer", 150, group=_GAME,
                help="Who made the machine."),
    grid.column("year", "Year", group=_GAME, help="The year the machine was released."),
]

_ALL = [definition["field"] for definition in COLUMNS]

# A built-in may filter where its name is what somebody would predict the filter from,
# and says in `help` what it is for rather than what it filters - a reader can see which
# rows are here; what they cannot see is why this was worth building a view for.
VIEWS: dict[str, list[str] | views.Preset] = {
    "Missing": views.Preset(
        columns=("game", "label", "reason", "manufacturer", "year"),
        sort=({"colId": "game", "sort": "asc", "sortIndex": 0},),
        filters={"reason": {"values": [_MISSING]}},
        help="The art you do not have. Filter to one kind and you have the shopping "
             "list for it - select the rows and fetch them from the catalogs in one "
             "go."),
    "Orphans": views.Preset(
        columns=("game", "label", "reason", "table_file", "path"),
        sort=({"colId": "game", "sort": "asc", "sortIndex": 0},),
        filters={"reason": {"values": [_ORPHAN]}},
        help="Art left behind when a table was renamed, replaced by a new version or "
             "deleted. Nothing will ever look for these names again, so this is the "
             "list that is safe to clear out."),
    "Unused": views.Preset(
        columns=("game", "label", "reason", "used_by", "path", "source"),
        sort=({"colId": "game", "sort": "asc", "sortIndex": 0},),
        filters={"reason": {"values": [_UNUSED]}},
        help="Files nothing loads because something more specific always wins - the "
             "catalog art still sitting under the art you made yourself. Worth "
             "clearing if you want the space, but each one is a fallback that comes "
             "back the moment the file covering it goes."),
    "Sources": views.Preset(
        columns=("game", "label", "used_by", "path", "source", "match"),
        sort=({"colId": "source", "sort": "asc", "sortIndex": 0},
              {"colId": "game", "sort": "asc", "sortIndex": 1}),
        filters={"reason": {"values": [""]}},
        help="Where your art came from, with the unattributed first. Use it to see how "
             "much of the library you assembled yourself, and to bind files to their "
             "VPS records so updates can be tracked later."),
    "Everything": views.Preset(
        columns=tuple(_ALL),
        help="Every row, nothing hidden. The way out of any other view, and where you "
             "build a filter of your own worth saving."),
}


async def fill(picked: list[dict[str, Any]], library: Any,
               after: Callable[[], Any]) -> None:
    """Fetch art for every selected slot that has none.

    One call per slot, because the API fills one slot. A slot no catalog publishes is
    not a failure - a search that comes back empty is a real answer - so it is counted
    and reported rather than raised, and one slot's failure does not end the run.
    """
    wanted = [row for row in picked if not row.get("present")]
    if not wanted:
        ui.notify("Those all have a file. Select missing ones to fill.",
                  type="warning")
        return
    unmatched = sum(1 for row in wanted if not row.get("vps_id"))
    if not await confirm.ask(
            f"Look for art for {len(wanted)} missing?",
            detail="Anything found is copied into the game folder, named for the table "
                   "or shared by all of them, whichever the row is.",
            lines=([f"{unmatched} are not matched to VPS, so nothing can be looked up "
                    f"for those"] if unmatched else []),
            confirm="Get art", danger=False):
        return

    filled = empty = failed = 0
    for row in wanted:
        if not row.get("vps_id"):
            empty += 1
            continue
        try:
            offers = await run.io_bound(ApiClient().media_offers,
                                        row["vps_id"], row["kind"])
            if not offers:
                empty += 1
                continue
            offer = offers[0]
            await run.io_bound(library.fetch_media, row["game_id"],
                               row.get("table") or "", row["kind"],
                               offer["source"], row["vps_id"], offer.get("size") or "")
            filled += 1
        except Exception as exc:
            logger.warning("media: could not fill %s for %s: %s",
                           row["kind"], row["game_id"], exc)
            failed += 1

    said = f"Filled {filled}"
    if empty:
        said += f", nothing published for {empty}"
    if failed:
        said += f", {failed} failed"
    ui.notify(said, type="positive" if filled else "warning")
    if filled:
        await after()


def build(found: list[dict[str, Any]], library: Any,
          on_select: Callable[[dict | None], None],
          state: dict[str, Any] | None = None,
          rerender: Callable[[], None] | None = None,
          rescan: Callable[[], Any] | None = None) -> None:
    """The media lens: one row per file, and one per file that is not there."""
    state = state if state is not None else {}
    built = rows(found)
    gaps = sum(1 for row in built if not row.get("present"))
    selected: list[dict[str, Any]] = []

    # What is on screen, which on this page is rarely the whole library: the point of
    # the grid is narrowing, and a total that ignores the filter answers a question
    # nobody asked. Held rather than recomputed, because the count arrives from the
    # grid and the selection changes without it.
    on_screen = {"rows": len(built)}

    def said(picked: int) -> str:
        if picked:
            return f"{picked} of {on_screen['rows']} selected"
        if on_screen["rows"] == len(built):
            return f"{len(built)} media, {gaps} missing"
        return f"{on_screen['rows']} of {len(built)} media"

    with ui.row().classes("w-full items-center gap-2 px-3 py-2 mb-2 shrink-0 console-panel"):
        search = ui.input(placeholder="Search media") \
            .props("dense outlined clearable").classes("w-64")
        wire_views, _picker, showing = view_control(library, SCOPE, VIEWS,
                                                    _ALL, COLUMNS)
        ui.space()
        count = ui.label(said(0)).classes("text-xs console-label")
        if rescan is not None:
            ui.button(icon="refresh", on_click=rescan) \
                .props("flat dense round size=sm").classes("shrink-0") \
                .tooltip("Read the library from disk again and pick up anything "
                         "added, changed or removed - tables, media and assets")
        actions = ui.button(icon="more_vert").props("flat round dense") \
            .tooltip("Actions for the selected media")

        async def refill() -> None:
            for game_id in {row["game_id"] for row in selected}:
                library.forget_media(game_id)
            if rerender:
                rerender()

        with actions:
            with ui.menu():
                ui.menu_item("Get art for selected",
                             lambda: fill(list(selected), library, refill))
                ui.separator()
                ui.menu_item("Clear selection",
                             lambda: table.run_grid_method("deselectAll"))
        actions.set_visibility(False)

    def on_select_rows(picked: list[dict[str, Any]]) -> None:
        selected[:] = picked
        actions.set_visibility(bool(picked))
        count.text = said(len(picked))

    by_id = {row["id"]: row for row in built}
    ui.on("hub_row_focus",
          lambda event: on_select(by_id.get(grid.focused_row(event))))

    async def on_header_context(col_id: str | None) -> None:
        # Asked of the grid rather than tracked here: a column can also be dragged in
        # and out of the pinned area, and a local flag would then be wrong.
        state_now = await table.run_grid_method("getColumnState") or []
        entry = next((c for c in state_now if c.get("colId") == col_id), {})
        menu.clear()
        with menu:
            grid.column_menu(menu, table, COLUMNS, col_id, bool(entry.get("pinned")))

    with ui.element("div").classes("w-full grow min-h-0 flex flex-col"):
        table = grid.build(COLUMNS, built, SCOPE, on_select_rows,
                           on_header_context=on_header_context, view_of=showing)
        menu = ui.context_menu()
    search.on_value_change(
        lambda: table.run_grid_method("setGridOption", "quickFilterText",
                                      search.value or ""))

    async def counted() -> None:
        """Whatever narrowed the rows - a filter, the search, a view - lands here.

        `modelUpdated` is the one event every one of them fires, so the count follows
        all of them without each having to remember to say so.
        """
        found = await table.run_grid_method("getDisplayedRowCount")
        on_screen["rows"] = int(found if isinstance(found, int) else len(built))
        count.text = said(len(selected))

    table.on("modelUpdated", counted)
    wire_views(table)
