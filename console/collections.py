"""The collections grid: one row per collection, with the workbench beside it.

A collection is a subject like any other here, so this is a grid and not a pair of
cards. What one *is* - a name, how it is ordered, how many games - is what the columns
carry; what it *holds* is the workbench's answer, because membership is a list and a
list does not fit in a cell.
"""

from __future__ import annotations

import inspect
import json
import logging
from collections.abc import Awaitable, Callable
from functools import partial
from typing import Any

from nicegui import run, ui

from common.failures import why
from common.games.collection_store import DIRECTION_WORDS, MANUAL_ORDER, SORT_LABELS
from common.i18n import t
from console import art, collection_adds, community, confirm, grid, offload, panel, verbs, views
from console.games import view_control

logger = logging.getLogger("vpinfe.console.collections")

SCOPE = "console.collections"

# The wire's kind, and what a person reads for it.
KIND_LABELS = {"manual": "console.collections.hand_picked",
               "filter": "console.collections.smart"}
_KIND_WORDS = {kind: t(key) for kind, key in KIND_LABELS.items()}

# A number filters as a number: greater-than, less-than, between. AG Grid's default
# filter is the text one, which offers "contains" over a count - and `agNumberColumnFilter`
# is community, unlike the set filter this project cannot use.
_NUMERIC: dict[str, Any] = {"type": "numericColumn",
                            "filter": "agNumberColumnFilter"}

_ESCAPE = ("const esc = s => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;')"
           ".replace(/\"/g, '&quot;');")

_NAME = (
    "params => {" + _ESCAPE +
    f" const tip = esc({json.dumps(t('console.collections.opens_on.help'))});"
    f" const off = esc({json.dumps(t('console.collections.not_in_frontend.help'))});"
    f" const unsaved = esc({json.dumps(t('word.not_saved'))});"
    f" const why = esc({json.dumps(t('console.collections.not_saved.help'))});"
    " const d = params.data || {};"
    " let said = esc(params.value == null ? '' : params.value);"
    " if (d.opens_on) said += ' <i class=\"material-icons console-cell-mark"
    " console-cell-mark--chosen\" title=\"' + tip + '\">" + verbs.OPENS_ON + "</i>';"
    " if (d.in_frontend === false) said += ' <i class=\"material-icons console-cell-mark\""
    " title=\"' + off + '\">" + verbs.HIDE + "</i>';"
    " if (d.unsaved) said += ' <span class=\"console-member-chip console-tier"
    " console-tier--warn\" title=\"' + why + '\">' + unsaved + '</span>';"
    " return said; }"
)

_KIND = (
    "params => {" + _ESCAPE +
    " const said = esc(params.valueFormatted ?? params.value ?? '');"
    " return params.value === 'filter' ? '<i class=\"material-icons console-cell-mark\">"
    + verbs.SMART + "</i> ' + said : said; }"
)

# The cell's value stays the count, which is what the column sorts and filters on.
_GAMES = (
    "params => {" + _ESCAPE +
    " const d = params.data || {};"
    " const said = esc(d.games_said || (params.value ?? ''));"
    " const chip = text => text ? ' <span class=\"console-member-chip console-tier"
    " console-tier--warn\">' + esc(text) + '</span>' : '';"
    " return said + chip(d.missing_said) + chip(d.hidden_said); }"
)

COLUMNS = [
    # The wheel leads. A collection is recognized by its picture in the wheel long
    # before its name is read, and a list of collections that showed none of them was
    # asking the reader to work from the least distinctive thing about each.
    grid.column("icon", "", 56, pinned="left", sortable=False, filter=False,
                picker=t("console.collections.wheel"),
                help=t("console.collections.icon.help")),
    grid.identifier("name", t("word.name"), 240, pinned="left",
                    rowDrag=True, **{":cellRenderer": _NAME}),
    grid.column("kind", t("word.kind"), 120, help=t("console.collections.kind.help"),
                **{**grid.choice_filter([{"value": kind, "label": word}
                                         for kind, word in _KIND_WORDS.items()]),
                   ":cellRenderer": _KIND,
                   ":comparator": f"(a, b) => {{ const said = {json.dumps(_KIND_WORDS)};"
                                  " return String(said[a] ?? a)"
                                  ".localeCompare(String(said[b] ?? b)); }"}),
    # Right-aligned with the other number rather than left with the words: a count is
    # read against the counts above and below it.
    grid.column("count", t("console.collections.games"), 170,
                help=t("console.collections.games.help"),
                **{**_NUMERIC, ":cellRenderer": _GAMES}),
    grid.column("added", t("console.collections.added"), **_NUMERIC,
                help=t("console.collections.added.help")),
    grid.column("matched", t("console.collections.by_rule"), **_NUMERIC,
                help=t("console.collections.by_rule.help")),
    grid.column("excluded", t("console.collections.taken_out"), **_NUMERIC,
                help=t("console.collections.taken_out.help")),
    grid.column("order", t("console.collections.order"), 200,
                help=t("console.collections.order.help")),
    grid.column("limit", t("console.collections.limit"), **_NUMERIC,
                help=t("console.collections.limit.help")),
    grid.column("missing", t("console.collections.missing"), **_NUMERIC,
                help=t("console.collections.missing.help")),
    grid.column("hidden", t("word.hidden"), **_NUMERIC,
                help=t("console.collections.hidden.help")),
    grid.column("in_frontend", t("console.collections.in_frontend"),
                help=t("console.collections.in_frontend.help"),
                **{":valueFormatter": "params => params.value ? '\u2713' : ''",
                   "cellClass": "console-tick", ":cellRenderer": None,
                   **grid.choice_filter([{"value": True, "label": t("word.yes")},
                                         {"value": False, "label": t("word.no")}],
                                        formatted=True)}),
    grid.column("attention", t("console.collections.needs_attention"),
                **{":valueFormatter": "params => params.value ? '\u2713' : ''",
                   "cellClass": "console-tick", ":cellRenderer": None,
                   **grid.choice_filter([{"value": True, "label": t("word.yes")},
                                         {"value": False, "label": t("word.no")}],
                                        formatted=True)}),
]

_ARRANGEMENT = """(() => {
  const api = getElement(%d).api;
  const shown = [];
  api.forEachNodeAfterFilterAndSort(node => shown.push(node.data.id));
  const by = api.getColumnState().filter(c => c.sort)
    .sort((a, b) => (a.sortIndex ?? 0) - (b.sortIndex ?? 0))[0];
  return {shown: shown, sorted: by ? by.colId : ''};
})()"""

# Focusing the row is what opens its panel. Waits for the row, because the grid takes
# new rowData after this runs; false where the row is not displayed.
_FOCUS_ROW = """new Promise((done) => {
  const api = getElement(%d).api;
  let tries = 0;
  const look = () => {
    const node = api && api.getRowNode(%s);
    if (node && node.rowIndex !== null) {
      api.ensureNodeVisible(node);
      api.setFocusedCell(node.rowIndex, 'name');
      return done(true);
    }
    if (node || ++tries >= 40) return done(false);
    setTimeout(look, 25);
  };
  look();
})"""

COLLECTION_VIEWS: dict[str, list[str] | views.Preset] = {
    "console.view.everything": views.Preset(
        columns=("icon", "name", "kind", "count", "order"),
        help=t("console.view.collections_everything.help")),
    "console.collections.needs_attention": views.Preset(
        columns=("icon", "name", "kind", "added", "matched", "excluded", "missing",
                 "hidden"),
        filters={"attention": {"values": [True]}},
        help=t("console.view.collections_needs_attention.help")),
}


def rows(collections: list[dict[str, Any]], opens_on: str = "",
         unsaved: set[str] | frozenset[str] = frozenset()) -> list[dict[str, Any]]:
    """One row per collection, in the words the grid shows.

    `count` is what the collection resolves to, which is its size. The stored
    membership is a different number and lives in the panel. `opens_on` names the
    collection the cabinet opens on, and `unsaved` the ones with rules not yet saved.
    """
    built = []
    for row in collections:
        count = int(row.get("count") or 0)
        whole = int(row.get("before_limit") or 0)
        missing = int(row.get("missing") or 0)
        hidden = int(row.get("hidden") or 0)
        excluded = int(row.get("excluded") or 0)
        built.append({
            "id": row.get("name") or "",
            "name": row.get("name") or "",
            "kind": str(row.get("type") or ""),
            "icon": _icon_cell(row),
            # Zero is an answer here, not an absence: this is what the collection
            # resolves to, and an empty collection resolves to none.
            "count": count,
            "games_said": (t("console.collections.count_of", count=count, whole=whole)
                           if whole > count else str(count)),
            "missing_said": (t("console.collections.count_missing", count=missing)
                             if missing else ""),
            "hidden_said": (t("console.collections.count_hidden", count=hidden)
                            if hidden else ""),
            "added": int(row.get("added") or 0),
            "matched": int(row.get("matched") or 0),
            "excluded": excluded,
            "missing": missing,
            "hidden": hidden,
            "attention": bool(missing or hidden or excluded),
            "opens_on": bool(opens_on) and row.get("name") == opens_on,
            "in_frontend": row.get("in_frontend") is not False,
            "unsaved": row.get("name") in unsaved,
            "order": _order_line(row),
            "limit": row.get("limit") or None,
            # Kept whole on the row so the workbench does not refetch what the grid
            # already read.
            "_raw": row,
        })
    return built


def _icon_cell(row: dict[str, Any]) -> str:
    """The collection's picture, or nothing. No placeholder: an icon column of grey
    squares is louder than the few real pictures in it."""
    if not row.get("image"):
        return ""
    src = art.collection(str(row.get("name") or ""), version=row.get("image_version"),
                         size=art.CELL)
    return f'<img src="{src}" loading="lazy" class="console-collection-cell">'


def _order_line(row: dict[str, Any]) -> str:
    """How this collection is ordered, in one phrase.

    `manual` is the stored member array and says so - it is not one of the fields a
    collection can be sorted by, which is why SORT_LABELS does not carry it.
    """
    by = row.get("order_by") or ""
    if by == MANUAL_ORDER:
        return t("order.by.manual")
    if not by:
        return ""
    if row.get("ranking"):
        return community.ranked_label(row["ranking"])
    field = t(SORT_LABELS[by]) if by in SORT_LABELS else by
    way = DIRECTION_WORDS.get(by, {}).get(row.get("direction") or "")
    return t("console.collections.ordered", by=field, direction=t(way)) if way else field


def build(collections: list[dict[str, Any]], library: Any,
          on_select: Callable[[dict | None], Any],
          state: dict[str, Any] | None = None,
          rerender: Callable[[], None] | None = None) -> None:
    state = state if state is not None else {}
    built = rows(collections, library.opens_on(), state.get("unsaved_rules") or set())
    fields = [definition["field"] for definition in COLUMNS]

    async def act(what: Callable, *args: Any, said: str = "") -> None:
        try:
            await run.io_bound(what, *args)
        except Exception as exc:
            ui.notify(t("said.could_not_do_that"), caption=why(exc), type="negative")
            return
        ui.notify(said, type="positive")
        if rerender is not None:
            rerender()

    arrangement: dict[str, Any] = {"shown": [row["id"] for row in built], "sorted": ""}
    hint: dict[str, Any] = {}

    def annotate() -> None:
        hint["label"] = ui.label().classes("text-xs console-label shrink-0 whitespace-nowrap")
        hint["label"].set_visibility(False)

    with ui.row().classes("w-full items-center gap-2 px-3 py-2 mb-2 shrink-0 "
                                  "console-panel console-grid-bar"):
        bar = panel.grid_bar()
        wire_views, _picker, showing, describe = view_control(
            library, SCOPE, COLLECTION_VIEWS, fields, COLUMNS, bar=bar,
            annotate=annotate)
        describe()
        with bar.top, panel.bar_end():
            search = panel.search(t("console.collections.search_collections"))
        with bar.bottom, panel.bar_end():
            count = ui.label(t("console.collections.collections",
                               count=len(built))).classes("text-xs console-label")
            bulk = ui.button(icon=verbs.MORE).props("flat round dense") \
                .tooltip(t("console.collections.actions_selected_collections"))
            with bulk, ui.menu():
                ui.menu_item(t("console.collections.delete_selected"),
                             lambda: _ask_delete_many(grid.selection(table), library,
                                                      act)) \
                    .classes("console-menu-item console-menu-danger")
            bulk.set_visibility(False)
            panel.add_action([(t("console.collections.new_collection"),
                               lambda: collection_adds.ask_new(library, reread))],
                              empty=not built)

    by_id = {row["id"]: row for row in built}
    grid.on_row_focus(SCOPE,
                      lambda event: on_select(by_id.get(grid.focused_row(event))))
    picked: list[dict[str, Any]] = []

    shown: dict[str, int] = {"rows": len(built)}

    def said() -> str:
        if picked:
            return grid.selection_said(table, len(picked), t(
                "console.collections.selected", picked=len(picked), shown=shown["rows"]))
        if shown["rows"] != len(built):
            return t("console.collections.collections_of", shown=shown["rows"],
                     count=len(built))
        return t("console.collections.collections", count=len(built))

    def on_selected(rows_selected: list[dict[str, Any]]) -> None:
        picked[:] = rows_selected
        bulk.set_visibility(bool(rows_selected))
        count.text = said()

    def on_context(row: dict | None) -> None:
        # The menu acts on the row under the cursor, not on the selection.
        _fill(row)

    async def on_header_context(col_id: str | None) -> None:
        state_now: list[dict[str, Any]] = \
            await table.run_grid_method("getColumnState") or []
        entry = next((c for c in state_now if c.get("colId") == col_id), {})
        _fill(None, col_id=col_id, pinned=bool(entry.get("pinned")))

    with ui.element("div").classes("w-full grow min-h-0 flex flex-col"):
        table: ui.aggrid = grid.build(COLUMNS, built, SCOPE, on_selected, on_context,
                                      on_header_context, html_fields=["icon"],
                                      view_of=showing)
        menu = ui.context_menu()
    table.options["rowDragManaged"] = True
    table.options[":rowDragText"] = "params => params.rowNode.data.name"

    async def redrawn(_next: str | None) -> None:
        if rerender is not None:
            rerender()

    def _fill(row: dict | None, col_id: str | None = None,
              pinned: bool = False) -> None:
        """One menu, filled for whatever was right-clicked."""
        menu.clear()
        with menu:
            if col_id and not col_id.startswith("ag-Grid-"):
                header = next((d.get("headerName") for d in COLUMNS
                               if d.get("field") == col_id), col_id)
                ui.item_label(str(header)).props("header").classes("console-menu-header")
                ui.separator()
                ui.menu_item(
                    t("word.unpin") if pinned else t("word.pin_left"),
                    lambda c=col_id, p=pinned: grid.pin(table, c, None if p else "left")) \
                    .classes("console-menu-item")
                ui.menu_item(t("word.hide_column"),
                             lambda c=col_id: table.run_grid_method(
                                 "setColumnsVisible", [c], False)) \
                    .classes("console-menu-item")
            elif row:
                panel.verb_menu(menu, row["name"],
                                moves(row["name"])
                                + acts(library, state, row["name"], redrawn))

    def moves(name: str) -> list[panel.Verb]:
        out = []
        for label, where in ((t("console.collections.move_up"), "up"),
                             (t("console.collections.move_down"), "down"),
                             (t("console.collections.move_to_top"), "top")):
            order = moved(name, where)
            out.append(panel.Verb(
                label, partial(arrange, order, name) if order else None,
                hint=sorted_said() if not order and arrangement["sorted"] else "",
                in_panel=False))
        return out

    def sorted_said() -> str:
        by = arrangement["sorted"]
        header = next((d.get("headerName") for d in COLUMNS if d.get("field") == by), by)
        return t("console.collections.sorted_to_arrange", column=header)

    def moved(name: str, where: str) -> list[str] | None:
        """The whole order with `name` moved, or None where it cannot go that way."""
        shown = arrangement["shown"]
        if arrangement["sorted"] or name not in shown:
            return None
        order = [row["id"] for row in built]
        at = shown.index(name)
        if where == "top":
            if order[0] == name:
                return None
            order.remove(name)
            order.insert(0, name)
        elif where == "up":
            if at == 0:
                return None
            order.remove(name)
            order.insert(order.index(shown[at - 1]), name)
        else:
            if at == len(shown) - 1:
                return None
            order.remove(name)
            order.insert(order.index(shown[at + 1]) + 1, name)
        return order

    async def arrange(order: list[str], focus: str = "") -> None:
        try:
            await run.io_bound(library.arrange_collections, order)
        except Exception as exc:
            ui.notify(t("said.could_not_do_that"), caption=why(exc), type="negative")
        await reread(focus)

    async def dragged() -> None:
        drawn = await ui.run_javascript(_ARRANGEMENT % table.id)
        await arrange(list((drawn or {}).get("shown") or []))

    async def counted() -> None:
        drawn = await ui.run_javascript(_ARRANGEMENT % table.id) or {}
        arrangement["shown"] = list(drawn.get("shown") or [])
        arrangement["sorted"] = str(drawn.get("sorted") or "")
        shown["rows"] = len(arrangement["shown"])
        count.text = said()
        hint["label"].text = sorted_said() if arrangement["sorted"] else ""
        hint["label"].set_visibility(bool(arrangement["sorted"]))

    table.on("modelUpdated", counted)
    table.on("rowDragEnd", dragged, args=["type"])
    wire_views(table)
    search.on_value_change(
        lambda: table.run_grid_method("setGridOption", "quickFilterText",
                                      search.value or ""))

    async def reread(focus: str = "") -> None:
        fresh = rows(await offload.io(library.load_collections), library.opens_on(),
                     state.get("unsaved_rules") or set())
        built[:] = fresh
        by_id.clear()
        by_id.update({row["id"]: row for row in fresh})
        table.run_grid_method("setGridOption", "rowData", fresh)
        table.run_grid_method("refreshCells", {"force": True, "columns": ["name"]})
        count.text = said()
        if not focus:
            return
        try:
            shown = await ui.run_javascript(_FOCUS_ROW % (table.id, json.dumps(focus)),
                                            timeout=2.0)
        except Exception:  # noqa: BLE001 - the panel still opens below
            shown = False
        if not shown:
            opened = on_select(by_id.get(focus))
            if inspect.isawaitable(opened):
                await opened

    state["refresh_collections"] = reread

    def mark_unsaved(names: set[str]) -> None:
        changed = [{**row, "unsaved": row["id"] in names} for row in built
                   if row["unsaved"] != (row["id"] in names)]
        if changed:
            grid.transact(table, built, {"update": changed}, by_id)
            # The name is unchanged, so the grid would not redraw the cell carrying it.
            table.run_grid_method("refreshCells", {"force": True, "columns": ["name"]})

    state["mark_unsaved"] = mark_unsaved


async def _ask_delete_many(picked: list[dict], library: Any, act: Callable) -> None:
    """Several at once, asked once. The games stay in the library either way."""
    names = [row["name"] for row in picked]
    if not names:
        return
    # Eight, then a count: the list is here to say which ones, and a hundred names is
    # a dialog nobody reads to the end of.
    shown = names[:8] + ([t("said.and_more", count=len(names) - 8)]
            if len(names) > 8 else [])
    if await confirm.ask(t("console.collections.delete_collections", count=len(names)),
                         detail=await what_deleting_leaves(library, names),
                         lines=shown):
        for name in names:
            await act(library.delete_collection, name,
                    said=t("console.collections.deleted", name=(name)))


def acts(library: Any, state: dict[str, Any], name: str,
         after: Callable[[str | None], Awaitable[None]]) -> list[panel.Verb]:
    """What can be done to one collection. `after` is given the collection to show next,
    or None when this one has gone.

    No Rename: the name is a field in the panel's Details, beside the description, and
    a name editable in two places is two answers."""
    async def duplicate() -> None:
        try:
            taken = {str(one.get("name") or "")
                     for one in await offload.io(library.load_collections)}
            made = await offload.io(library.copy_collection, _copy_name(name, taken), name)
        except Exception as exc:  # noqa: BLE001
            ui.notify(t("said.could_not_do_that"), caption=why(exc), type="negative")
            return
        copy = str(made.get("name") or "")
        ui.notify(t("console.collections.created", strip=copy), type="positive")
        await after(copy)

    async def delete() -> None:
        # Asked, because a manual collection is somebody's hand-picked list and there
        # is no undo behind this.
        if not await confirm.ask(t("console.collections.delete", name=(name)),
                                 detail=await what_deleting_leaves(library, [name])):
            return
        try:
            await run.io_bound(library.delete_collection, name)
        except Exception as exc:  # noqa: BLE001
            ui.notify(t("said.could_not_do_that"), caption=why(exc), type="negative")
            return
        ui.notify(t("console.collections.deleted", name=(name)), type="positive")
        state.setdefault("collection_drafts", {}).pop(name, None)
        if state.get("collection") == name:
            state["collection"] = None
        await after(None)

    return [panel.Verb(t("console.workbench.duplicate"), duplicate),
            panel.Verb(t("word.delete"), delete, danger=True)]


def _copy_name(name: str, taken: set[str]) -> str:
    wanted = t("console.collections.copy_of", name=name)
    number = 2
    while wanted in taken:
        wanted = t("console.collections.copy_of_n", name=name, n=number)
        number += 1
    return wanted


async def what_deleting_leaves(library: Any, names: list[str]) -> str:
    try:
        settings = await offload.io(library.config_values)
    except Exception:  # noqa: BLE001 - asked all the same, without the second sentence
        settings = {}
    opens_on = str((settings.get("behavior") or {}).get("startup_collection") or "")
    if opens_on.strip() in names:
        return t("console.collections.games_stay_opens_all")
    return t("console.collections.games_stay")


def stored_views(library: Any) -> tuple[list[views.View], str]:
    """Exposed for tests: which views this grid has saved."""
    return views.stored(library, SCOPE)
