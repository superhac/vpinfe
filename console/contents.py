from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from nicegui import ui

from common.i18n import t
from console import game_tables, grid, offload, panel, renderers, views
from console.data import Library

logger = logging.getLogger("vpinfe.console.contents")

SCOPE = "console.contents.columns"

ADDED, MATCHED, EXCLUDED, MISSING = "added", "matched", "excluded", "missing"

# The members lens says `origin`; a person reads the words the game panel uses.
_FROM_ORIGIN = {"named": ADDED, "filter": MATCHED, "excluded": EXCLUDED,
                "missing": MISSING}

STATES = {
    ADDED: {"label": t("console.workbench.held_added")},
    MATCHED: {"label": t("console.workbench.held_matched")},
    EXCLUDED: {"label": t("console.workbench.excluded"), "tier": "off"},
    MISSING: {"label": t("console.game_tables.missing"), "tier": "warn"},
}

COLUMNS: list[dict[str, Any]] = [
    grid.column("collection", t("console.contents.collection"), 160, pinned="left"),
    grid.identifier("game", t("word.game"), 200),
    grid.column("status", t("word.status"), 110,
                **grid.choice_filter([{"value": key, "label": one["label"]}
                                      for key, one in STATES.items()], formatted=True),
                **renderers.drawable("state", states=STATES)),
    grid.column("table", t("console.contents.table"), 160,
                help=t("console.contents.table.help")),
]
_ALL = [one["field"] for one in COLUMNS]

VIEWS: dict[str, list[str] | views.Preset] = {
    t("console.view.everything"): views.Preset(
        columns=tuple(_ALL),
        sort=({"colId": "collection", "sort": "asc", "sortIndex": 0},
              {"colId": "game", "sort": "asc", "sortIndex": 1}),
        help=t("console.view.contents.help")),
}


def status(member: dict[str, Any]) -> str:
    tables = member.get("tables") or []
    if tables and tables[0].get("origin") == "missing":
        return MISSING
    return _FROM_ORIGIN.get(str(member.get("origin") or ""), ADDED)


def named_table(member: dict[str, Any]) -> str:
    """The table this row names, or "" where it follows the game's default."""
    ref = str(member.get("ref_table") or "")
    tables = member.get("tables") or []
    if not ref or not tables or tables[0].get("id") != ref \
            or tables[0].get("origin") == "missing":
        return ""
    return game_tables.table_name(tables[0])


def row_id(collection: str, member: dict[str, Any]) -> str:
    # A game can be in a collection twice - named with two of its tables, or named and
    # excluded - so the game alone does not say which row.
    return "\x1f".join((collection, str(member.get("origin") or ""),
                        str(member.get("game") or ""), str(member.get("ref_table") or "")))


def rows(contents: list[tuple[dict[str, Any], dict[str, Any]]]) -> list[dict[str, Any]]:
    built = []
    for collection, membership in contents:
        name = str(collection.get("name") or "")
        for member in membership.get("members") or []:
            built.append({"id": row_id(name, member), "collection": name,
                          "game": str(member.get("name") or member.get("game") or ""),
                          "table": named_table(member), "status": status(member)})
    return built


def find(collection: str, membership: dict[str, Any], wanted: str) -> dict | None:
    """The row `wanted` names, or the same game and ref in whatever state an act left it."""
    members = list(membership.get("members") or [])
    exact = next((one for one in members if row_id(collection, one) == wanted), None)
    if exact is not None:
        return exact
    _, _, game, ref = (wanted.split("\x1f") + ["", "", "", ""])[:4]
    return next((one for one in members if str(one.get("game") or "") == game
                 and str(one.get("ref_table") or "") == ref), None)


def build(library: Library, state: dict[str, Any],
          on_select: Callable[[dict | None], Any]) -> None:
    body = ui.column().classes("w-full grow min-h-0 gap-0")
    ui.timer(0.01, lambda: _fill(library, state, on_select, body), once=True)


async def _fill(library: Library, state: dict[str, Any],
                on_select: Callable[[dict | None], Any], body: Any) -> None:
    # Deferred: `games` imports `workbench`, which imports this module.
    from .games import view_control

    try:
        built = rows(await offload.io(library.contents))
    except Exception as exc:  # noqa: BLE001 - this page says why, never 500s
        body.clear()
        with body:
            panel.facts(ui, [panel.intro(t("console.contents.could_not_read", exc=(exc)))])
        return
    by_id = {row["id"]: row for row in built}
    body.clear()
    with body:
        with ui.row().classes("w-full items-center gap-2 px-3 py-2 mb-2 shrink-0 "
                              "console-panel console-grid-bar"):
            bar = panel.grid_bar()
            wire_views, _picker, showing, describe = view_control(
                library, SCOPE, VIEWS, _ALL, COLUMNS, bar=bar)
            describe()
            with bar.top, panel.bar_end():
                search = panel.search(t("console.contents.search"))
            with bar.bottom, panel.bar_end():
                count = ui.label(t("console.contents.count", count=len(built))) \
                    .classes("text-xs console-label")

        async def on_header_context(col_id: str | None) -> None:
            await grid.header_menu(menu, table, COLUMNS, col_id)

        with ui.element("div").classes("w-full grow min-h-0 flex flex-col"):
            table = grid.build(COLUMNS, built, SCOPE, on_header_context=on_header_context,
                               view_of=showing)
            menu = ui.context_menu()
        grid.on_row_focus(SCOPE, lambda event: on_select(by_id.get(grid.focused_row(event))))

        async def refresh_rows() -> None:
            fresh = rows(await offload.io(library.contents))
            by_id.clear()
            by_id.update({row["id"]: row for row in fresh})
            count.text = t("console.contents.count", count=len(fresh))
            table.run_grid_method("setGridOption", "rowData", fresh)

        state["refresh_contents"] = refresh_rows
        wire_views(table)
        search.on_value_change(
            lambda: table.run_grid_method("setGridOption", "quickFilterText",
                                          search.value or ""))
