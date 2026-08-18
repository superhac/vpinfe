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
}

# AG Grid's own column state is the stored payload - it already carries width, order,
# visibility, sort and pinning.
_SAVE_EVENTS = ("columnMoved", "columnResized", "columnVisible", "columnPinned",
                "sortChanged")


# Padding either side plus the sort and filter icons AG Grid puts in every header.
_HEADER_CHROME_PX = 58
_HEADER_CHAR_PX = 7


def header_width(header: str) -> int:
    """The narrowest this column can be and still show its header in full."""
    return len(header) * _HEADER_CHAR_PX + _HEADER_CHROME_PX


def column(field: str, header: str, width: int, **extra: Any) -> dict[str, Any]:
    """A column that never starts narrower than its own header.

    `width` is the preference, the header is the floor. Dragging narrower still works.
    """
    return {"field": field, "headerName": header,
            "width": max(width, header_width(header))} | extra


def build(columns: list[dict[str, Any]], rows: list[dict[str, Any]], scope: str,
          on_select: Callable[[dict | None], None] | None = None,
          on_context: Callable[[dict | None], None] | None = None) -> ui.aggrid:
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
        "suppressDragLeaveHidesColumns": True,
        "animateRows": False,
        # False deliberately: preventing the default here stops the event reaching
        # Quasar, and ui.context_menu never opens.
        "preventDefaultOnContextMenu": False,
    }, theme="quartz",
        # nicegui defaults this True, which fits columns to the grid width and so
        # overrides both the declared widths and any the user saved.
        auto_size_columns=False,
    ).classes("w-full").style("height:calc(100vh - 124px)")

    _restore(grid, scope, columns)
    _save_on_change(grid, scope)
    if on_select is not None:
        async def changed() -> None:
            rows = await grid.get_selected_rows()
            # The inspector follows one row, the action menu wants them all.
            result = on_select(rows[-1] if rows else None, rows)
            if inspect.isawaitable(result):
                await result

        # Queried rather than read off rowSelected: that payload can fail to serialise
        # and is then never sent, and its `selected` field arrives undefined.
        grid.on("selectionChanged", changed)
    if on_context is not None:
        # Only `data`: the full payload can fail to serialise and is then never sent.
        grid.on("cellContextMenu",
                lambda event: on_context((event.args or {}).get("data")), args=["data"])
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
            # Only columns this grid still has: a saved layout outlives its column set,
            # and state for columns that no longer exist collapses every column.
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
        # Dragging a column edge fires a resize event per pixel. throttle is nicegui's
        # own, so there is no timer to outlive the element; trailing_events keeps the
        # final width rather than the one mid-drag.
        grid.on(event, save, args=[], throttle=0.6, trailing_events=True)
