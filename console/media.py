"""The library seen by media file rather than by game.

Its own subject, not a lens on the games grid. A matrix of games against kinds answers
coverage well and can hold one fact per cell; a file has several, and the question
"everything a stranger placed" spans twenty columns there and one here.

The row that matters is the one with nothing in it. A selection under Games is a
selection of games whatever column you filtered, so the kind is never part of what a
bulk action is given - which is why filling gaps in bulk has had nowhere to live.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from nicegui import ui

from common import icons
from common.i18n import t
from common.media_specs import media_label_map
from console import art_fill, grid, list_art, media_ownership, offload, panel, verbs, views
from console.games import view_control
from console.on_page import on_page

SCOPE = "console.media.columns"

_ORPHAN = media_ownership.tier_for(media_ownership.ORPHAN).noun
_UNUSED = media_ownership.tier_for(media_ownership.UNUSED).noun
_MISSING = media_ownership.tier_for(media_ownership.MISSING).noun

# Why a file on disk is not the one being used, blank while it is doing its job. The
# blank is a choice like any other in the funnel, and it needs a word there because
# "match the empty ones" is not something a checkbox can say by being unlabelled.
_REASON = {media_ownership.ORPHAN: _ORPHAN, media_ownership.UNUSED: _UNUSED}
_REASON_CHOICES = ([{"value": "", "label": t("word.in_use")}]
                   + [{"value": word, "label": t(word)}
                      for word in (_MISSING, _ORPHAN, _UNUSED)])

_SOURCE_CHOICES = ([{"value": name, "label": name}
                    for name in media_ownership.source_names()]
                   + [{"value": "", "label": t("word.no_file")}])


def _standing_in(via: str) -> str:
    """What is covering an empty slot on the cabinet, said short.

    Worth a column because this lens reads "Missing" against a machine that is visibly
    showing something, and both are true: the file belongs to another slot.
    """
    if via.startswith("set:"):
        return t("console.media.set_named", name=via.split(":", 1)[1])
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
_FILE = "word.file"
_GAME = "word.game"
_SOURCE = "word.source"

COLUMNS: list[dict[str, Any]] = [
    grid.identifier("game", t(_GAME), 240, pinned="left", group=t(_GAME),
                subtitle="said", picture=list_art.FIELD, glyph=icons.GAMES,
                help=t("console.media.game_folder_file_belongs.help")),
    grid.column("label", t("word.kind"), 160, group=t(_FILE),
                help=t("console.media.twenty_media_kinds_row.help")),
    grid.column("used_by", t("word.used_by"), type="numericColumn", group=t(_FILE),
                help=t("console.media.how_many_game_s.help")),
    grid.column("reason", t("word.unused_reason"), 150, group=t(_FILE),
                **grid.choice_filter(_REASON_CHOICES),
                help=t("console.media.why_file_not_one.help")),
    grid.column("table_file", t("console.media.table"), 200, group=t(_FILE),
                help=t("console.media.vpx_file_named_blank.help")),
    grid.column("path", t("word.path"), 300, group=t(_FILE),
                help=t("console.media.where_file_sits_relative.help")),
    grid.column("source", t("word.source"), 165, group=t(_SOURCE),
                **grid.choice_filter(_SOURCE_CHOICES),
                help=t("console.media.put_file_far_anything.help")),
    grid.column("match", t("console.media.match"), 140, group=t(_SOURCE),
                help=t("console.media.vps_file_somebody_said.help")),
    grid.column("covered_by", t("console.media.covered"), 130, group=t(_FILE),
                help=t("console.media.what_shows_kind_no_file.help")),
    grid.column("manufacturer", t("word.manufacturer"), 150, group=t(_GAME),
                help=t("help.who_made_it")),
    grid.column("year", t("word.year"), group=t(_GAME),
            help=t("help.year_released")),
]

_ALL = [definition["field"] for definition in COLUMNS]

# A built-in may filter where its name is what somebody would predict the filter from,
# and says in `help` what it is for rather than what it filters - a reader can see which
# rows are here; what they cannot see is why this was worth building a view for.
VIEWS: dict[str, list[str] | views.Preset] = {
    "console.view.missing": views.Preset(
        columns=("game", "label", "reason"),
        sort=({"colId": "game", "sort": "asc", "sortIndex": 0},),
        filters={"reason": {"values": [_MISSING]}},
        help=t("console.media.art_not_filter_one.help")),
    "console.view.orphans": views.Preset(
        columns=("game", "label", "reason", "table_file", "path"),
        sort=({"colId": "game", "sort": "asc", "sortIndex": 0},),
        filters={"reason": {"values": [_ORPHAN]}},
        help=t("console.media.art_left_behind_table.help")),
    "console.view.unused": views.Preset(
        columns=("game", "label", "reason", "used_by", "path", "source"),
        sort=({"colId": "game", "sort": "asc", "sortIndex": 0},),
        filters={"reason": {"values": [_UNUSED]}},
        help=t("console.media.files_nothing_loads_because.help")),
    "console.view.sources": views.Preset(
        columns=("game", "label", "used_by", "path", "source", "match"),
        sort=({"colId": "source", "sort": "asc", "sortIndex": 0},
              {"colId": "game", "sort": "asc", "sortIndex": 1}),
        filters={"reason": {"values": [""]}},
        help=t("console.media.where_art_came_unattributed.help")),
    "console.view.everything": views.Preset(
        columns=tuple(_ALL),
        help=t("console.media.every_row_nothing_hidden.help")),
}


async def refill(library: Any, table: Any, built: list[dict[str, Any]],
                 by_id: dict[str, Any], game_ids: list[str]) -> None:
    """Read these games' rows again and swap them in place: the search, the view and
    the rest of the selection stay as they were."""
    for game_id in game_ids:
        library.forget_media(game_id)
    found = await offload.io(library.load_media_rows)
    if table.is_deleted:
        return
    wanted = set(game_ids)
    fresh = rows([row for row in found if str(row["game_id"]) in wanted])
    grid.replace_rows(table, built, by_id, fresh, lambda row: str(row["game_id"]) in wanted)


def build(found: list[dict[str, Any]], library: Any,
          on_select: Callable[[dict | None], Any],
          state: dict[str, Any] | None = None,
          rescan: Callable[[], Any] | None = None) -> None:
    """The media lens: one row per file, and one per file that is not there."""
    state = state if state is not None else {}
    built = rows(found)
    columns = grid.with_art(COLUMNS, library.list_art_look())
    selected: list[dict[str, Any]] = []

    # What is on screen, which on this page is rarely the whole library: the point of
    # the grid is narrowing, and a total that ignores the filter answers a question
    # nobody asked. Held rather than recomputed, because the count arrives from the
    # grid and the selection changes without it.
    on_screen = {"rows": len(built)}

    def said(picked: int) -> str:
        if picked:
            return grid.selection_said(table, picked, t(
                "console.media.selected", picked=(picked), shown=on_screen["rows"]))
        if on_screen["rows"] == len(built):
            return t("console.media.media_missing", count=(len(built)),
                     gaps=(sum(1 for row in built if not row.get("present"))))
        return t("console.media.media", shown=on_screen["rows"], count=len(built))

    with ui.row().classes("w-full items-center gap-2 px-3 py-2 mb-2 shrink-0 "
                                  "console-panel console-grid-bar"):
        bar = panel.grid_bar()
        wire_views, _picker, showing, describe = view_control(library, SCOPE, VIEWS,
                                                    _ALL, columns, bar=bar,
                                                    art_in_lists=True)
        describe()
        with bar.top, panel.bar_end():
            search = panel.search(t("console.media.search_media"))
        with bar.bottom, panel.bar_end():
            count = ui.label(said(0)).classes("text-xs console-label")
            actions = ui.button(icon=verbs.MORE).props("flat round dense") \
                .tooltip(t("console.media.actions_selected_media"))
            if rescan is not None:
                panel.refresh(rescan, t("console.media.read_library_disk_pick"))

        @on_page
        async def get_missing_art() -> None:
            picked = grid.selection(table)
            ids = list(dict.fromkeys(str(row["game_id"]) for row in picked))

            def placed() -> Any:
                return refill(library, table, built, by_id, ids)

            if grid.hidden_count(table) or len(picked) < on_screen["rows"]:
                await art_fill.confirm_slots(picked, state, placed)
                return
            await art_fill.ask(ids, state, placed,
                               name=str(picked[0].get("game") or "") if len(ids) == 1 else "")

        with actions:
            with ui.menu():
                ui.menu_item(t("console.art_fill.get_missing"), get_missing_art) \
                    .classes("console-menu-item")
                ui.separator()
                ui.menu_item(t("word.clear_selection"),
                             lambda: table.run_grid_method("deselectAll")) \
                    .classes("console-menu-item")
        actions.set_visibility(False)

    def on_select_rows(picked: list[dict[str, Any]]) -> None:
        selected[:] = picked
        actions.set_visibility(bool(picked))
        count.text = said(len(picked))

    by_id = {row["id"]: row for row in built}
    grid.on_row_focus(SCOPE,
                      lambda event: on_select(by_id.get(grid.focused_row(event))))

    async def on_header_context(col_id: str | None) -> None:
        await grid.header_menu(menu, table, columns, col_id)

    with ui.element("div").classes("w-full grow min-h-0 flex flex-col"):
        table: ui.aggrid = grid.build(columns, built, SCOPE, on_select_rows,
                                      on_header_context=on_header_context,
                                      view_of=showing)
        menu: ui.context_menu = ui.context_menu()
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

    async def refresh_files(game_id: str) -> None:
        fresh = rows(await offload.io(library.files_of, "media", game_id))
        grid.replace_rows(table, built, by_id, fresh, lambda row: row["game_id"] == game_id)

    state["refresh_files"] = refresh_files
    wire_views(table)
