"""The library seen by asset file rather than by game.

The Media lens's twin, and it exists for the same reason: a row is a file, so a gap is
countable and a bulk action can be handed one. What differs is what the files are for.
Media is what a game looks like; an asset is what it needs to play as intended, and a
matrix that mixes them is neither.

It is also the surface a recorded defect has been waiting for. The Games grid reports a
`.directb2s` from a folder scan, so a game whose only backglass is named for one table
reads "has one" while its sibling launches without a backglass. Here they are two rows.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from nicegui import ui

from console import grid, media_ownership, views
from console.games import view_control

logger = logging.getLogger("vpinfe.console.assets")

SCOPE = "console.assets.columns"

# What the wire's binding is called on screen. Three of the four are the words the media
# lens already uses for the same question - whose file is this - and `orphaned` is the
# one assets have and media does not: a file named for a table that is not there.
ORPHAN = media_ownership.tier_for(media_ownership.ORPHAN).noun
UNUSED = media_ownership.tier_for(media_ownership.UNUSED).noun
MISSING = media_ownership.tier_for(media_ownership.MISSING).noun

_REASON_CHOICES = ([{"value": "", "label": "In use"}]
                   + [{"value": word, "label": word}
                      for word in (MISSING, ORPHAN, UNUSED)])

_SOURCE_CHOICES = ([{"value": name, "label": name}
                    for name in media_ownership.source_names()]
                   + [{"value": "", "label": "No file"}])


def _reason(row: dict[str, Any]) -> str:
    """Why this file is not the one being used, blank while it is.

    An asset has a second way to be unused that media does not: VPX resolves a script
    and a point of view by table stem only, so one named for the folder is correctly
    named and inert. `serves` is what tells them apart, not the binding.
    """
    binding = str(row.get("binding") or "")
    if binding == "orphaned":
        return ORPHAN
    if not row.get("present"):
        return MISSING
    return UNUSED if row.get("serves") == 0 else ""


def rows(found: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The API's assets, flattened for a grid."""
    return [{**row,
             "used_by": row.get("serves"),
             "reason": _reason(row),
             "source": media_ownership.source_name(str(row.get("origin") or "")),
             "match": str(row.get("matched_to") or ""),
             "path": row.get("path") or ""}
            for row in found]


_FILE = "File"
_GAME = "Game"
_SOURCE = "Source"

COLUMNS: list[dict[str, Any]] = [
    grid.column("game", "Game", 200, pinned="left", group=_GAME,
                help="The game folder this file belongs to."),
    grid.column("label", "Kind", 160, group=_FILE,
                help="What the file is for - the backglass VPX loads, the table's own\n"
                     "settings, its script, and so on."),
    grid.column("used_by", "Used by", type="numericColumn", group=_FILE,
                help="How many of this game's tables actually load this file.\n\n"
                     "0 - nothing loads it.\n"
                     "Blank - there is no file to load."),
    grid.column("reason", "Unused reason", 150, group=_FILE,
                **grid.choice_filter(_REASON_CHOICES),
                help="Why this file is not the one being used. Blank while it is.\n\n"
                     "Missing - no file at all.\n"
                     "Orphan - named for a table this folder does not have. Safe to "
                     "delete.\n"
                     "Unused - correctly named, but nothing resolves to it. Either "
                     "every table has its own, or it is named for the folder and VPX "
                     "only ever looks for one named for the table."),
    grid.column("table_file", "Table", 200, group=_FILE,
                help="The .vpx this file is named for.\n\n"
                     "Blank - named for the folder, so every table falls back to it."),
    grid.column("path", "Path", 300, group=_FILE,
                help="Where the file sits, relative to the game folder."),
    grid.column("source", "Source", 165, group=_SOURCE,
                **grid.choice_filter(_SOURCE_CHOICES),
                help="Who put the file here, as far as anything recorded it.\n\n"
                     "Unknown - nothing recorded it, which is true of most files.\n"
                     "Blank - there is no file."),
    grid.column("match", "Match", 140, group=_SOURCE,
                help="The VPS file somebody said this is.\n\n"
                     "Blank - nobody has said."),
    grid.column("manufacturer", "Manufacturer", 150, group=_GAME,
                help="Who made the machine."),
    grid.column("year", "Year", group=_GAME, help="The year the machine was released."),
]

_ALL = [definition["field"] for definition in COLUMNS]

VIEWS: dict[str, list[str] | views.Preset] = {
    "Missing": views.Preset(
        columns=("game", "label", "reason", "manufacturer", "year"),
        sort=({"colId": "game", "sort": "asc", "sortIndex": 0},),
        filters={"reason": {"values": [MISSING]}},
        help="What a table could use and has not got. Not all of it matters - a PUP "
             "pack is an enhancement, not a requirement - so read it as what is "
             "available to add rather than as a list of faults."),
    "Orphans": views.Preset(
        columns=("game", "label", "reason", "table_file", "path"),
        sort=({"colId": "game", "sort": "asc", "sortIndex": 0},),
        filters={"reason": {"values": [ORPHAN]}},
        help="Files left behind when a table was renamed, updated to a new version or "
             "deleted. VPX will never look for these names again, so this is the list "
             "that is safe to clear out."),
    "Unused": views.Preset(
        columns=("game", "label", "reason", "used_by", "table_file", "path"),
        sort=({"colId": "game", "sort": "asc", "sortIndex": 0},),
        filters={"reason": {"values": [UNUSED]}},
        help="Correctly named files that nothing loads - a shared file every table has "
             "overridden, or a script named for the folder when VPX only ever looks "
             "for one named for the table. The second kind is usually a mistake worth "
             "fixing rather than deleting."),
    "Sources": views.Preset(
        columns=("game", "label", "used_by", "path", "source", "match"),
        sort=({"colId": "source", "sort": "asc", "sortIndex": 0},
              {"colId": "game", "sort": "asc", "sortIndex": 1}),
        filters={"reason": {"values": [""]}},
        help="Where the files you rely on came from. Use it to bind them to their VPS "
             "records, so a later version of a table can be told from the one you have."),
    "Everything": views.Preset(
        columns=tuple(_ALL),
        help="Every row, nothing hidden. The way out of any other view, and where you "
             "build a filter of your own worth saving."),
}


def build(found: list[dict[str, Any]], library: Any,
          on_select: Callable[[dict | None], None],
          state: dict[str, Any] | None = None,
          rerender: Callable[[], None] | None = None,
          rescan: Callable[[], Any] | None = None) -> None:
    """The asset lens: one row per file, and one per file that is not there."""
    state = state if state is not None else {}
    built = rows(found)
    gaps = sum(1 for row in built if not row.get("present"))
    on_screen = {"rows": len(built)}

    def said() -> str:
        if on_screen["rows"] == len(built):
            return f"{len(built)} assets, {gaps} missing"
        return f"{on_screen['rows']} of {len(built)} assets"

    with ui.row().classes("w-full items-center gap-2 px-3 py-2 mb-2 shrink-0 hub-panel"):
        search = ui.input(placeholder="Search assets") \
            .props("dense outlined clearable").classes("w-64")
        wire_views, _picker, showing = view_control(library, SCOPE, VIEWS,
                                                    _ALL, COLUMNS)
        ui.space()
        count = ui.label(said()).classes("text-xs hub-label")
        if rescan is not None:
            ui.button(icon="refresh", on_click=rescan) \
                .props("flat dense round size=sm").classes("shrink-0") \
                .tooltip("Read the library from disk again and pick up anything "
                         "added, changed or removed - tables, media and assets")

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
        table = grid.build(COLUMNS, built, SCOPE,
                           on_header_context=on_header_context, view_of=showing)
        menu = ui.context_menu()
    search.on_value_change(
        lambda: table.run_grid_method("setGridOption", "quickFilterText",
                                      search.value or ""))

    async def counted() -> None:
        """Whatever narrowed the rows - a filter, the search, a view - lands here."""
        seen = await table.run_grid_method("getDisplayedRowCount")
        on_screen["rows"] = int(seen if isinstance(seen, int) else len(built))
        count.text = said()

    table.on("modelUpdated", counted)
    wire_views(table)
