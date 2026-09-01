"""Grids, and the column layout the hub keeps for each.

Layout only - width, order, pinning. Which columns are shown, how they are
sorted and what is filtered belong to a view; see hubui/views.py.
"""

from __future__ import annotations

import inspect
import logging
from collections.abc import Callable
from typing import Any

from nicegui import run, ui

logger = logging.getLogger("vpinfe.hubui")

DEFAULT_COL_DEF: dict[str, Any] = {
    "sortable": True,
    "resizable": True,
    "filter": True,
    "minWidth": 60,
    # Lets a header carrying a newline take the second line it needs.
    "autoHeaderHeight": True,
}

# AG Grid's own column state is the stored payload: width, order, visibility, sort, pin.
# Layout is the grid's, whatever view is showing; visibility, sort and filters are the
# view's. Keeping them apart is what lets a built-in view be a constant - go back to one
# and you get its definition, not a layout that drifted. See hubui/views.py.
_SAVE_EVENTS = ("columnMoved", "columnResized", "columnPinned")
_LAYOUT_FIELDS = ("colId", "width", "flex", "pinned")


# Chrome measured at 50px, plus the 8px gap the theme puts between a header and its
# filter icon; 9px/char is the widest average in the header font, so a header never has
# to wrap. Counted here because a gap the width does not know about is a gap that
# squeezes the text it was added to protect.
_HEADER_CHROME_PX = 66
_HEADER_CHAR_PX = 9


def header_width(header: str) -> int:
    """The narrowest this column can be and still show its header in full.

    Measured per line: a header broken over two lines needs the width of its longest
    line, not of the whole string.
    """
    longest = max((len(line) for line in header.split("\n")), default=0)
    # No header, no floor: a column of pictures carries no text, no sort arrow and no
    # filter button, so charging it for their chrome makes it wider than it needs.
    return longest * _HEADER_CHAR_PX + _HEADER_CHROME_PX if longest else 0


# A picker in the funnel, where AG Grid's text box would be: on a column of marks that
# box asks the reader to know the word behind a circle, and on a boolean it offers
# "Choose one / True / False". The set filter that would fix it is Enterprise; a custom
# filter is not, and community takes any class implementing the interface.
#
# `choices` is [{value, label, mark, repeat}], the value being what the cell holds - so
# a blank cell is a choice like any other rather than the one state a filter cannot
# express.
CHOICE_FILTER = "window.HubChoiceFilter"

_CHOICE_FILTER_JS = """
if (!window.HubChoiceFilter) {
  window.HubChoiceFilter = class {
    init(params) {
      this.params = params;
      this.picked = new Set();
      this.boxes = new Map();
      this.gui = document.createElement('div');
      this.gui.className = 'hub-filter';
      for (const choice of params.choices || []) {
        const row = document.createElement('label');
        row.className = 'hub-filter-row';
        const box = document.createElement('input');
        box.type = 'checkbox';
        box.addEventListener('change', () => {
          box.checked ? this.picked.add(choice.value) : this.picked.delete(choice.value);
          this.params.filterChangedCallback();
        });
        row.appendChild(box);
        // `repeat` draws the mark more than once, which is how a rating says three
        // rather than saying "3" beside a picture of one star.
        for (let n = 0; n < (choice.mark ? (choice.repeat || 1) : 0); n++) {
          const mark = document.createElement('span');
          mark.className = choice.mark;
          row.appendChild(mark);
        }
        // A state drawn as a character rather than a shape - presence is a tick here.
        if (choice.glyph) {
          const tick = document.createElement('span');
          tick.className = 'hub-tick';
          tick.textContent = choice.glyph;
          row.appendChild(tick);
        }
        const word = document.createElement('span');
        word.textContent = choice.label;
        row.appendChild(word);
        this.boxes.set(choice.value, box);
        this.gui.appendChild(row);
      }
    }
    getGui() { return this.gui; }
    isFilterActive() { return this.picked.size > 0; }
    doesFilterPass(params) {
      const held = this.params.getValue(params.node);
      // A cell with nothing in it is the "missing" choice, whose value is "".
      return this.picked.has(held === null || held === undefined ? '' : held);
    }
    getModel() { return this.picked.size ? {values: [...this.picked]} : null; }
    setModel(model) {
      this.picked = new Set((model && model.values) || []);
      for (const [value, box] of this.boxes) box.checked = this.picked.has(value);
    }
  };
}
"""


def install_filters() -> None:
    """Put the filter component on the page. Once per page, before any grid is built."""
    ui.add_body_html(f"<script>{_CHOICE_FILTER_JS}</script>")


def choice_filter(choices: list[dict[str, Any]]) -> dict[str, Any]:
    """Column options that filter by picking a state rather than by typing one."""
    return {":filter": CHOICE_FILTER, "filterParams": {"choices": choices}}


def focused_row(event: Any) -> str:
    """The row id out of a focus event, and `focused_column` the column it landed in.

    The column travels with it because a cell is a more specific place than a row: the
    Games grid opens the workbench on the part of the game the column is about. Older
    payloads were the bare id, so both read either shape.
    """
    args = event.args
    return str((args.get("id") if isinstance(args, dict) else args) or "")


def focused_column(event: Any) -> str:
    args = event.args
    return str((args.get("col") if isinstance(args, dict) else "") or "")


def two_line(header: str) -> str:
    """Break the last word onto its own line, so a long header stays a narrow column."""
    words = header.split()
    return header if len(words) < 2 else " ".join(words[:-1]) + "\n" + words[-1]


def column(field: str, header: str, width: int = 0, **extra: Any) -> dict[str, Any]:
    """A column sized to fit, which is its header unless the content needs more.

    **Omit `width`.** Pass one only where the values are longer than the header - a
    title, an author, a filename - and it is a floor, not a target. Every width used to
    be hand-picked, so a column of one-digit counts was as wide as somebody guessed
    rather than as wide as it needs to be. Dragging narrower still works, and what the
    user drags to is what persists.

    Every multi-word header wraps, here rather than at each call site: it was applied
    only where the columns were generated, so `Table Count` and the asset headers sat
    on one line beside media headers that did not.
    """
    header = two_line(header)
    return {"field": field, "headerName": header,
            "width": max(width, header_width(header))} | extra


# Ours, not AG Grid's: it names the group a column sits under in the column picker.
# Carried on the definition so the list that declares the columns also declares their
# order and their grouping, and stripped before the defs reach the grid.
GROUP_KEY = "group"


def for_grid(columns: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The definitions as AG Grid wants them, without our own keys."""
    return [{k: v for k, v in column.items() if k != GROUP_KEY} for column in columns]


def build(columns: list[dict[str, Any]], rows: list[dict[str, Any]], scope: str,
          on_select: Callable[[dict | None], None] | None = None,
          on_context: Callable[[dict | None], None] | None = None,
          on_header_context: Callable[[str | None], None] | None = None,
          html_fields: list[str] | None = None) -> ui.aggrid:
    """A grid whose column layout is restored from, and saved to, the hub."""
    grid = ui.aggrid({
        "columnDefs": for_grid(columns),
        "rowData": rows,
        "defaultColDef": DEFAULT_COL_DEF,
        # Clicking a cell takes focus and nothing else. Click-selection in multiRow
        # mode *replaces* the set, so a cell click would clear every checkbox a bulk
        # action is about to read.
        "rowSelection": {"mode": "multiRow", "checkboxes": True,
                         "headerCheckbox": True, "enableClickSelection": False},
        # The ":" prefix marks this as JavaScript. Without it AG Grid calls a string and
        # the grid dies as an empty table rather than an error.
        ":getRowId": "params => params.data.id",
        # The checkbox belongs to the row, so it stays with the row's left edge.
        "selectionColumnDef": {"pinned": "left"},
        # The workbench follows the focused row, and focus is not selection: arrowing
        # must not disturb the checkboxes a bulk action reads.
        #
        # Marked on every fragment: AG Grid splits a row across the pinned and center
        # containers, each its own .ag-row.
        ":onCellFocused":
            "params => { const r = params.api.getDisplayedRowAtIndex(params.rowIndex); "
            "if (r) emitEvent('hub_row_focus', "
            "{id: r.data.id, col: params.column && params.column.getColId()}); "
            "window.__hubFocusRow = params.rowIndex; "
            "window.__hubMarkFocus && window.__hubMarkFocus(); }",
        # Rows are recycled as you scroll, so the mark rides the wrong row without
        # this.
        ":onBodyScroll": "() => { window.__hubMarkFocus && window.__hubMarkFocus(); }",
        "suppressDragLeaveHidesColumns": True,
        "animateRows": False,
        # False deliberately: preventing the default stops the event reaching Quasar,
        # and ui.context_menu never opens.
        "preventDefaultOnContextMenu": False,
    }, html_columns=[i for i, d in enumerate(columns)
                     if d["field"] in (html_fields or [])],
        theme="quartz",
        # nicegui defaults this True, which fits columns to the grid width and so
        # overrides both the declared widths and any the user saved.
        auto_size_columns=False,
    ).classes("w-full grow min-h-0")

    # Installed once per page. Idempotent, so a second grid does not stack it.
    ui.run_javascript("""
    window.__hubMarkFocus = () => {
      const i = window.__hubFocusRow;
      document.querySelectorAll('.ag-row.hub-row-focus')
        .forEach(e => e.classList.remove('hub-row-focus'));
      if (i === undefined || i === null) return;
      document.querySelectorAll(`.ag-row[row-index="${i}"]`)
        .forEach(e => e.classList.add('hub-row-focus'));
    };
    """)
    _restore(grid, scope, columns)
    _save_on_change(grid, scope)
    if on_select is not None:
        async def changed() -> None:
            rows = await grid.get_selected_rows()
            # The count only; the focused row owns which game is on screen.
            result = on_select(rows)
            if inspect.isawaitable(result):
                await result

        # Queried, not read off rowSelected: that payload can fail to serialise and its
        # `selected` field arrives undefined.
        grid.on("selectionChanged", changed)
    if on_context is not None:
        # Only `data`: the full payload can fail to serialise and is then never sent.
        grid.on("cellContextMenu",
                lambda event: on_context((event.args or {}).get("data")), args=["data"])
    if on_header_context is not None:
        # Fires in Community and carries colId. The native column menu is Enterprise.
        grid.on("columnHeaderContextMenu",
                lambda event: on_header_context((event.args or {}).get("colId")),
                args=["colId"])
    return grid


def _restore(grid: ui.aggrid, scope: str, columns: list[dict[str, Any]]) -> None:
    from hubui.api import HubClient

    async def apply() -> None:
        try:
            stored = (await run.io_bound(HubClient().preferences, scope)).get("columns")
        except Exception:
            logger.warning("hub ui: could not read column state for %s", scope, exc_info=True)
            return
        if stored:
            # Only columns this grid still has - state for ones it lost collapses them
            # all - and only the layout fields, in as well as out: a payload written
            # before views existed carries `hide`, which would override the view.
            known = {definition["field"] for definition in columns}
            state = [{k: entry[k] for k in _LAYOUT_FIELDS if k in entry}
                     for entry in stored if entry.get("colId") in known]
            if state:
                grid.run_grid_method("applyColumnState",
                                     {"state": state, "applyOrder": True})

    # gridReady rather than a timer: a timer outlives the grid when the view changes,
    # and firing under a cleared container raises "parent slot has been deleted".
    grid.on("gridReady", apply)


def _save_on_change(grid: ui.aggrid, scope: str) -> None:
    from hubui.api import HubClient

    async def save() -> None:
        try:
            state = await grid.run_grid_method("getColumnState")
            # Stripped to the layout: storing `hide` or `sort` would make a built-in
            # drift, which is the one thing it must never do.
            layout = [{k: entry[k] for k in _LAYOUT_FIELDS if k in entry}
                      for entry in (state or [])]
            await run.io_bound(HubClient().put_preferences, scope, {"columns": layout})
        except Exception:
            # A layout that fails to save is worth a log and nothing more - it must
            # never take down the grid the user is working in.
            logger.warning("hub ui: could not save column state for %s", scope, exc_info=True)

    for event in _SAVE_EVENTS:
        # A resize fires per pixel. nicegui's own throttle, so no timer outlives the
        # element; trailing_events keeps the final width.
        grid.on(event, save, args=[], throttle=0.6, trailing_events=True)
