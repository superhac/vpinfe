"""Grids the user can arrange, with the arrangement kept on the hub."""

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
_SAVE_EVENTS = ("columnMoved", "columnResized", "columnVisible", "columnPinned",
                "sortChanged")


# Chrome measured at 50px; 9px/char is the widest average in the header font, so a
# header never has to wrap.
_HEADER_CHROME_PX = 58
_HEADER_CHAR_PX = 9


def header_width(header: str) -> int:
    """The narrowest this column can be and still show its header in full.

    Measured per line: a header broken over two lines needs the width of its longest
    line, not of the whole string.
    """
    longest = max((len(line) for line in header.split("\n")), default=0)
    return longest * _HEADER_CHAR_PX + _HEADER_CHROME_PX


def column(field: str, header: str, width: int, **extra: Any) -> dict[str, Any]:
    """A column that never starts narrower than its own header.

    `width` is the preference, the header is the floor. Dragging narrower still works.
    """
    return {"field": field, "headerName": header,
            "width": max(width, header_width(header))} | extra


def build(columns: list[dict[str, Any]], rows: list[dict[str, Any]], scope: str,
          on_select: Callable[[dict | None], None] | None = None,
          on_context: Callable[[dict | None], None] | None = None,
          on_header_context: Callable[[str | None], None] | None = None,
          html_fields: list[str] | None = None) -> ui.aggrid:
    """A grid whose column arrangement is restored from, and saved to, the hub."""
    grid = ui.aggrid({
        "columnDefs": columns,
        "rowData": rows,
        "defaultColDef": DEFAULT_COL_DEF,
        # enableClickSelection is required from AG Grid 33: without it a row click only
        # takes focus, and with checkboxes off there is no way to select at all.
        "rowSelection": {"mode": "multiRow", "checkboxes": True,
                         "headerCheckbox": True, "enableClickSelection": True},
        # The ":" prefix marks this as JavaScript. Without it AG Grid calls a string and
        # the grid dies as an empty table rather than an error.
        ":getRowId": "params => params.data.id",
        # The checkbox belongs to the row, so it stays with the row's left edge.
        "selectionColumnDef": {"pinned": "left"},
        "suppressDragLeaveHidesColumns": True,
        "animateRows": False,
        # False deliberately: preventing the default here stops the event reaching
        # Quasar, and ui.context_menu never opens.
        "preventDefaultOnContextMenu": False,
    }, html_columns=[i for i, d in enumerate(columns)
                     if d["field"] in (html_fields or [])],
        theme="quartz",
        # nicegui defaults this True, which fits columns to the grid width and so
        # overrides both the declared widths and any the user saved.
        auto_size_columns=False,
    ).classes("w-full grow min-h-0")

    _restore(grid, scope, columns)
    _save_on_change(grid, scope)
    if on_select is not None:
        async def changed() -> None:
            rows = await grid.get_selected_rows()
            # The workbench follows one row, the action menu wants them all.
            result = on_select(rows[-1] if rows else None, rows)
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
            # Only columns this grid still has: state for ones it lost collapses them all.
            known = {definition["field"] for definition in columns}
            state = [entry for entry in stored if entry.get("colId") in known]
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
            await run.io_bound(HubClient().put_preferences, scope, {"columns": state})
        except Exception:
            # A layout that fails to save is worth a log and nothing more - it must
            # never take down the grid the user is working in.
            logger.warning("hub ui: could not save column state for %s", scope, exc_info=True)

    for event in _SAVE_EVENTS:
        # A resize fires per pixel. nicegui's own throttle, so no timer outlives the
        # element; trailing_events keeps the final width.
        grid.on(event, save, args=[], throttle=0.6, trailing_events=True)
