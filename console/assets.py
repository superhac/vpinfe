
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

from common.i18n import t
from console import grid, media_ownership, panel, verbs, views
from console.games import view_control

logger = logging.getLogger("vpinfe.console.assets")

SCOPE = "console.assets.columns"

# What the wire's binding is called on screen. Three of the four are the words the media
# lens already uses for the same question - whose file is this - and `orphaned` is the
# one assets have and media does not: a file named for a table that is not there.
ORPHAN = media_ownership.tier_for(media_ownership.ORPHAN).noun
UNUSED = media_ownership.tier_for(media_ownership.UNUSED).noun
MISSING = media_ownership.tier_for(media_ownership.MISSING).noun

_REASON_CHOICES = ([{"value": "", "label": t("word.in_use")}]
                   + [{"value": word, "label": t(word)}
                      for word in (MISSING, ORPHAN, UNUSED)])

_SOURCE_CHOICES = ([{"value": name, "label": name}
                    for name in media_ownership.source_names()]
                   + [{"value": "", "label": t("word.no_file")}])


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


_FILE = "word.file"
_GAME = "word.game"
_SOURCE = "word.source"

COLUMNS: list[dict[str, Any]] = [
    grid.identifier("game", t(_GAME), 240, pinned="left", group=t(_GAME),
                subtitle="said",
                help=t("console.assets.game_folder_file_belongs.help")),
    grid.column("label", t("word.kind"), 160, group=t(_FILE),
                help=t("console.assets.what_file_backglass_vpx.help")),
    grid.column("used_by", t("word.used_by"), type="numericColumn", group=t(_FILE),
                help=t("console.assets.how_many_game_s.help")),
    grid.column("reason", t("word.unused_reason"), 150, group=t(_FILE),
                **grid.choice_filter(_REASON_CHOICES),
                help=t("console.assets.why_file_not_one.help")),
    grid.column("table_file", t("console.assets.table"), 200, group=t(_FILE),
                help=t("console.assets.vpx_file_named_blank.help")),
    grid.column("path", t("word.path"), 300, group=t(_FILE),
                help=t("console.assets.where_file_sits_relative.help")),
    grid.column("source", t("word.source"), 165, group=t(_SOURCE),
                **grid.choice_filter(_SOURCE_CHOICES),
                help=t("console.assets.put_file_far_anything.help")),
    grid.column("match", t("console.assets.match"), 140, group=t(_SOURCE),
                help=t("console.assets.vps_file_somebody_said.help")),
    grid.column("manufacturer", t("word.manufacturer"), 150, group=t(_GAME),
                help=t("help.who_made_it")),
    grid.column("year", t("word.year"), group=t(_GAME),
            help=t("help.year_released")),
]

_ALL = [definition["field"] for definition in COLUMNS]

VIEWS: dict[str, list[str] | views.Preset] = {
    t("console.view.missing"): views.Preset(
        columns=("game", "label", "reason"),
        sort=({"colId": "game", "sort": "asc", "sortIndex": 0},),
        filters={"reason": {"values": [MISSING]}},
        help=t("console.assets.what_table_could_use.help")),
    t("console.view.orphans"): views.Preset(
        columns=("game", "label", "reason", "table_file", "path"),
        sort=({"colId": "game", "sort": "asc", "sortIndex": 0},),
        filters={"reason": {"values": [ORPHAN]}},
        help=t("console.assets.files_left_behind_table.help")),
    t("console.view.unused"): views.Preset(
        columns=("game", "label", "reason", "used_by", "table_file", "path"),
        sort=({"colId": "game", "sort": "asc", "sortIndex": 0},),
        filters={"reason": {"values": [UNUSED]}},
        help=t("console.assets.correctly_named_files_nothing.help")),
    t("console.view.sources"): views.Preset(
        columns=("game", "label", "used_by", "path", "source", "match"),
        sort=({"colId": "source", "sort": "asc", "sortIndex": 0},
              {"colId": "game", "sort": "asc", "sortIndex": 1}),
        filters={"reason": {"values": [""]}},
        help=t("console.assets.where_files_rely_came.help")),
    t("console.view.everything"): views.Preset(
        columns=tuple(_ALL),
        help=t("console.assets.every_row_nothing_hidden.help")),
}


def build(found: list[dict[str, Any]], library: Any,
          on_select: Callable[[dict | None], Any],
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
            return t("console.assets.assets_missing", count=(len(built)), gaps=(gaps))
        return t("console.assets.assets", value=(on_screen['rows']), len=(len(built)))

    with ui.row().classes("w-full items-center gap-2 px-3 py-2 mb-2 shrink-0 "
                                  "console-panel console-grid-bar"):
        bar = panel.grid_bar()
        wire_views, _picker, showing, describe = view_control(library, SCOPE, VIEWS,
                                                    _ALL, COLUMNS, bar=bar)
        describe()
        with bar.top, panel.bar_end():
            search = panel.search(t("console.assets.search_assets"))
        with bar.bottom, panel.bar_end():
            count = ui.label(said()).classes("text-xs console-label")
            if rescan is not None:
                ui.button(icon=verbs.REFRESH, on_click=rescan) \
                    .props("flat dense round size=sm").classes("shrink-0") \
                    .tooltip(t("console.assets.read_library_disk_pick"))

    by_id = {row["id"]: row for row in built}
    grid.on_row_focus(SCOPE,
                      lambda event: on_select(by_id.get(grid.focused_row(event))))

    async def on_header_context(col_id: str | None) -> None:
        # Asked of the grid rather than tracked here: a column can also be dragged in
        # and out of the pinned area, and a local flag would then be wrong.
        state_now: list[dict[str, Any]] = \
            await table.run_grid_method("getColumnState") or []
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
