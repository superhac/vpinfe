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
from pathlib import Path
from typing import Any

from nicegui import run, ui

from common.media_specs import media_label_map
from hubui import confirm, grid, media_ownership, views
from hubui.api import HubClient
from hubui.games import view_control

logger = logging.getLogger("vpinfe.hubui.media")

SCOPE = "hubui.media.columns"

_SOURCE_CHOICES = ([{"value": name, "label": name}
                    for name in media_ownership.source_names()]
                   + [{"value": "", "label": "No file"}])

# The states a row can be in. A stand-in is not one of them: it is another slot's file
# being borrowed, so the slot it borrows for is empty and says separately what is
# covering it.
PRESENT_STATES = (media_ownership.TABLE, media_ownership.GAME)
_STATE_CHOICES = [{"value": media_ownership.tier_for(key).noun,
                   "label": media_ownership.tier_for(key).noun}
                  for key in (*PRESENT_STATES, media_ownership.MISSING)]


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


def _where(path: str) -> str:
    """The folder a file sits in - `medias/`, or the game folder itself in a library
    old enough to keep its art beside the .vpx."""
    if not path:
        return ""
    parent = str(Path(path).parent)
    return "Game folder" if parent == "." else parent


def rows(found: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The API's media, flattened for a grid.

    `state` carries the word rather than the tier: one column read across needs no
    legend, where twenty columns of marks did.
    """
    built = []
    for row in found:
        present = bool(row.get("present"))
        state = (media_ownership.noun(row.get("via")) if present
                 else media_ownership.tier_for(media_ownership.MISSING).noun)
        built.append({**row,
                      "state": state,
                      "source": media_ownership.source_name(str(row.get("origin") or "")),
                      "match": str(row.get("matched_to") or ""),
                      "where": _where(str(row.get("path") or "")),
                      "covered_by": _standing_in(str(row.get("standing_in") or "")),
                      # Named, not counted: the use of the column is knowing which file
                      # is sitting underneath, and a "1" answers nothing.
                      "hidden_files": ", ".join(row.get("shadowed") or [])})
    return built


COLUMNS: list[dict[str, Any]] = [
    grid.column("game", "Game", 200),
    grid.column("label", "Kind", 160),
    grid.column("state", "State", **grid.choice_filter(_STATE_CHOICES)),
    grid.column("table_file", "Table", 180),
    grid.column("serves", "Serves", type="numericColumn"),
    grid.column("file", "File", 220),
    grid.column("where", "Where", 110),
    # Wider than the word: this is the column Sources sorts on, so its header carries
    # a sort badge and a funnel beside the label and `header_width` only measures text.
    grid.column("source", "Source", 165, **grid.choice_filter(_SOURCE_CHOICES)),
    grid.column("match", "Match", 140),
    grid.column("covered_by", "Covered by", 120),
    grid.column("hidden_files", "Hidden", 180),
    grid.column("manufacturer", "Maker", 140),
    grid.column("year", "Year"),
]

_MISSING = media_ownership.tier_for(media_ownership.MISSING).noun
_ALL = [definition["field"] for definition in COLUMNS]

# A built-in may filter where its name is what somebody would predict the filter from.
# Gaps is the empty slots and Files is the ones holding something, which is each name
# doing what it says. Sources promises no subset, so it filters nothing and sorts
# instead - the unattributed group together and stay countable.
VIEWS: dict[str, list[str] | views.Preset] = {
    # State is in here although every row reads "Missing", which normally makes a
    # column worth deleting. It is the filtered column: left out, the funnel that says
    # rows are being hidden is on a header nobody can see, and a view that quietly
    # drops 475 rows is the one thing a reader cannot recover from.
    # Serves and Covered by are not here. Both are blank or constant on a library of
    # single-table folders with no sets, which is nearly every library and every row of
    # this one - and a column that reads the same all the way down is furniture. They
    # are in Everything, where somebody looking for them will find them.
    "Gaps": views.Preset(
        columns=("game", "label", "state", "manufacturer", "year"),
        sort=({"colId": "game", "sort": "asc", "sortIndex": 0},),
        filters={"state": {"values": [_MISSING]}}),
    "Files": views.Preset(
        columns=("game", "label", "state", "table_file", "file", "where",
                 "hidden_files"),
        sort=({"colId": "game", "sort": "asc", "sortIndex": 0},),
        filters={"state": {"values": [media_ownership.tier_for(key).noun
                                      for key in PRESENT_STATES]}}),
    # Filtered to what is here, for the same reason as Files and predictable from the
    # name the same way: a slot with no file came from nowhere, so it is not a row this
    # view is about. Sorted so Unknown leads, which is the gap somebody opens this to
    # close - and it leads on its own, because alphabetically it comes first.
    "Sources": views.Preset(
        columns=("game", "label", "state", "file", "source", "match"),
        # `sortIndex` spelled out: applying a state without one lets the grid number
        # them in column order, so the sort it reports back is not the one declared and
        # the view reads as modified the moment it is picked.
        sort=({"colId": "source", "sort": "asc", "sortIndex": 0},
              {"colId": "game", "sort": "asc", "sortIndex": 1}),
        filters={"state": {"values": [media_ownership.tier_for(key).noun
                                      for key in PRESENT_STATES]}}),
    "Everything": _ALL,
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
            offers = await run.io_bound(HubClient().media_offers,
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
          rerender: Callable[[], None] | None = None) -> None:
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

    with ui.row().classes("w-full items-center gap-2 px-3 py-2 mb-2 shrink-0 hub-panel"):
        search = ui.input(placeholder="Search media") \
            .props("dense outlined clearable").classes("w-64")
        wire_views, _picker, showing = view_control(library, SCOPE, VIEWS,
                                                    _ALL, COLUMNS)
        ui.space()
        count = ui.label(said(0)).classes("text-xs hub-label")
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

    with ui.element("div").classes("w-full grow min-h-0 flex flex-col"):
        table = grid.build(COLUMNS, built, SCOPE, on_select_rows, view_of=showing)
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
