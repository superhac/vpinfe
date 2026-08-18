"""The games grid: one row per game, with lenses over the same rows."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from nicegui import ui

from hubui import grid
from hubui.api import HubClient
from hubui.data import TIER_LEGEND

SCOPE = "hubui.games.columns"

COLUMNS = [
    grid.column("name", "Name", 280),
    grid.column("manufacturer", "Manufacturer", 150),
    grid.column("year", "Year", 80),
    grid.column("game_type", "Type", 80),
    grid.column("themes", "Themes", 200),
    grid.column("rom", "ROM", 150),
    grid.column("version", "Version", 90),
    grid.column("coverage", "Assets", 90, type="numericColumn"),
    grid.column("rating", "Rating", 90, type="numericColumn"),
]

# Presets, not a replacement for the column picker: a lens sets which columns are
# shown, and anything the user changes afterwards is theirs and is what persists.
LENSES: dict[str, list[str]] = {
    "Metadata": ["name", "manufacturer", "year", "game_type", "themes", "rating"],
    "Coverage": ["name", "coverage", "rating"],
    "Files": ["name", "rom", "version"],
    # Media is built from the library's own kinds, so it is added at render time.
    "Media": [],
}

_ALL = [definition["field"] for definition in COLUMNS]


def media_columns(kinds: list[str]) -> list[dict[str, Any]]:
    return [grid.column(f"media_{kind}", kind.replace("_", " "), 92,
                        cellStyle={"textAlign": "center"}) for kind in kinds]


async def _rate(games: list[dict[str, Any]]) -> None:
    """Set a rating on every game passed in.

    The API rates one game at a time (`PUT /games/{id}/rating`), so this loops here
    rather than calling a bulk endpoint that does not exist.
    """
    from nicegui import run
    if not games:
        return

    async def apply(value: int) -> None:
        client = HubClient()
        for game in games:
            await run.io_bound(client.rate, game["id"], value)
        dialog.close()
        ui.notify(f"Rated {len(games)} game(s) {value}", type="positive")

    with ui.dialog() as dialog, ui.card():
        ui.label(f"Rate {len(games)} game(s)").classes("text-sm")
        with ui.row():
            for value in range(6):
                ui.button(str(value), on_click=lambda v=value: apply(v)).props("flat dense")
    dialog.open()


async def _launch(games: list[dict[str, Any]]) -> None:
    """Launch one game. Deliberately refuses a multi-row selection.

    Launching is player-resident and starts something on a machine; doing it for
    several rows at once has no sensible meaning, so it is refused rather than looped.
    """
    from nicegui import run
    if len(games) != 1:
        ui.notify("Select a single game to launch", type="warning")
        return
    await run.io_bound(HubClient().launch, games[0]["id"])
    ui.notify(f"Launching {games[0].get('name')}", type="positive")


def build(rows: list[dict[str, Any]], kinds: list[str],
          on_select: Callable[[dict | None], None]) -> None:
    columns = COLUMNS + media_columns(kinds)
    all_fields = [definition["field"] for definition in columns]
    selected: list[dict[str, Any]] = []
    context_row: list[dict[str, Any]] = []

    with ui.row().classes("w-full items-center gap-2 px-3 py-2 mb-2 hub-panel"):
        search = ui.input(placeholder="Search games") \
            .props("dense outlined clearable").classes("w-64")
        lens = ui.toggle(list(LENSES), value="Metadata").props("dense no-caps unelevated")
        ui.space()
        legend = ui.label(TIER_LEGEND).classes("text-xs opacity-60")
        legend.bind_visibility_from(lens, "value", lambda value: value == "Media")
        # The selection count sits with the total: it is the same fact - how much am I
        # looking at - and it costs no vertical space of its own.
        count = ui.label(f"{len(rows)} games").classes("text-xs hub-label")
        actions = ui.button(icon="more_vert").props("flat round dense") \
            .tooltip("Actions for the selected games")
        with actions:
            with ui.menu():
                ui.menu_item("Rate selected", lambda: _rate(selected))
                ui.separator()
                ui.menu_item("Clear selection",
                             lambda: table.run_grid_method("deselectAll"))
        actions.set_visibility(False)

    def on_select_rows(row: dict | None, rows_selected: list[dict[str, Any]]):
        selected[:] = rows_selected
        actions.set_visibility(bool(rows_selected))
        count.text = (f"{len(rows_selected)} of {len(rows)} selected"
                      if rows_selected else f"{len(rows)} games")
        return on_select(row)

    def on_context(row: dict | None) -> None:
        # The row menu acts on the row under the cursor, which is not necessarily the
        # selection. Conflating the two is how people act on the wrong thing.
        context_row[:] = [row] if row else []
        context_label.text = (row or {}).get("name") or ""

    # The menu hangs off a wrapper, not off the grid: ui.aggrid's Vue template is a bare
    # <div> with no slot, so a child of it is never rendered and the menu silently does
    # not exist. Anchoring to an element that does render its children is the fix.
    with ui.element("div").classes("w-full"):
        table = grid.build(columns, rows, SCOPE, on_select_rows, on_context)
        with ui.context_menu():
            context_label = ui.item_label("").props("header").classes("text-xs opacity-70")
            ui.separator()
            ui.menu_item("Rate", lambda: _rate(context_row))
            ui.menu_item("Launch", lambda: _launch(context_row))

    def apply_lens() -> None:
        if lens.value == "Media":
            wanted = ["name", *[f"media_{kind}" for kind in kinds]]
        else:
            wanted = LENSES.get(lens.value or "", all_fields)
        table.run_grid_method("setColumnsVisible", wanted, True)
        table.run_grid_method("setColumnsVisible",
                              [name for name in all_fields if name not in wanted], False)

    lens.on_value_change(apply_lens)
    search.on_value_change(
        lambda: table.run_grid_method("setGridOption", "quickFilterText", search.value or ""))
