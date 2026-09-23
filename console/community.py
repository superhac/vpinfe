from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Any

from nicegui import ui

from common.i18n import t
from console import deeplink, grid, offload, panel, views, when
from console.api import ApiClient, ApiError
from console.data import Library

logger = logging.getLogger("vpinfe.console.community")

PREFIX = "community:"
ICON = "extension"
HELD = "held"
UNDER = "under_said"

_KIND = {"number": {"type": "numericColumn", "filter": "agNumberColumnFilter"},
         "text": {}, "date": {}}
_WIDTH = {"number": 130, "text": 150, "date": 140}
FIRST_WIDTH = 240

def view_key(extension: str, key: str) -> str:
    return f"{PREFIX}{extension}:{key}"


def lists(extensions: Sequence[dict[str, Any]]) -> list[tuple[dict, dict]]:
    """(extension, list) for every list a running extension declares."""
    return [(one, declared) for one in extensions
            if str(one.get("state") or "") == "loaded"
            for declared in one.get("community") or []]


def nav_items(extensions: Sequence[dict[str, Any]], feature: str) -> tuple:
    return tuple((view_key(str(one.get("name") or ""), str(declared.get("key") or "")),
                  str(declared.get("title") or ""), ICON, feature)
                 for one, declared in lists(extensions))


def find(view: str, extensions: Sequence[dict[str, Any]]) -> tuple[dict, dict] | None:
    return next(((one, declared) for one, declared in lists(extensions)
                 if view_key(str(one.get("name") or ""), str(declared.get("key") or ""))
                 == view), None)


def columns(declared: dict[str, Any]) -> list[dict[str, Any]]:
    out = []
    for index, one in enumerate(declared.get("columns") or []):
        kind = str(one.get("kind") or "text")
        extra = {**_KIND.get(kind, {}), **(when.cell(one["field"]) if kind == "date" else {})}
        header, said = str(one.get("header") or one["field"]), str(one.get("help") or "")
        if index == 0:
            out.append(grid.identifier(one["field"], header, FIRST_WIDTH, help=said,
                                       subtitle=UNDER, link=HELD, **extra))
        else:
            out.append(grid.column(one["field"], header, _WIDTH.get(kind, 0), help=said,
                                   **extra))
    if declared.get("relation"):
        out.append(grid.column(HELD, t("console.community.in_library"),
                               help=t("console.community.in_library.help"),
                               **grid.choice_filter(
                                   [{"value": True, "label": t("console.community.held")},
                                    {"value": False,
                                     "label": t("console.community.not_held")}],
                                   formatted=True)))
    return out


def presets(declared: dict[str, Any]) -> dict[str, views.Preset]:
    related = bool(declared.get("relation"))
    out = {view["name"]: views.Preset(
        columns=tuple(view["columns"]),
        sort=tuple({"colId": one["field"], "sort": "desc" if one.get("desc") else "asc",
                    "sortIndex": index} for index, one in enumerate(view.get("sort") or [])),
        help=str(view.get("help") or "")) for view in declared.get("views") or []}
    shown = tuple(one["field"] for one in declared.get("columns") or [])
    first = next(iter(out.values()), None)
    if not out:
        out[t("console.view.everything")] = views.Preset(columns=shown)
    if related:
        out[t("console.community.yours")] = views.Preset(
            columns=first.columns if first else shown, filters={HELD: {"values": [True]}},
            help=t("console.community.yours.help"))
    return out


def rows(found: list[dict[str, Any]], declared: dict[str, Any],
         held: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    relation = declared.get("relation") or {}
    declared_columns = declared.get("columns") or []
    dates = [one["field"] for one in declared_columns if one.get("kind") == "date"]
    under = list(declared_columns[0].get("under") or []) if declared_columns else []
    out = []
    for index, row in enumerate(found):
        mine = held.get(str(row.get(relation.get("field", "")) or "")) if relation else None
        built = {**row, "id": str(index), HELD: bool(mine),
                 UNDER: " ".join(str(row[one]) for one in under
                                 if row.get(one) not in (None, "")),
                 f"{HELD}_href": _address(mine, relation) if mine else "",
                 f"{HELD}_tip": t("console.community.held") if mine else ""}
        for field in dates:
            built = when.said(built, field)
        out.append(built)
    return out


def _address(mine: dict[str, Any], relation: dict[str, Any]) -> str:
    game, table = str(mine.get("game_id") or ""), str(mine.get("table_id") or "")
    if relation.get("keys") == "vps_release" and table:
        return "/console?" + deeplink.query({"view": "tables", "game": game, "table": table})
    return "/console?" + deeplink.query({"view": "games", "game": game})


def build(extension: dict[str, Any], declared: dict[str, Any], library: Library) -> None:
    body = ui.column().classes("w-full grow min-h-0 gap-0")
    ui.timer(0.01, lambda: _fill(extension, declared, library, body), once=True)


async def _fill(extension: dict[str, Any], declared: dict[str, Any], library: Library,
                body: Any) -> None:
    from .games import view_control

    name = str(extension.get("name") or "")
    said = str(extension.get("display_name") or name)
    try:
        found = (await offload.io(ApiClient().ext_get,
                                  f"/ext/{name}{declared.get('base') or ''}")).get("rows") or []
    except (ApiError, OSError) as exc:
        body.clear()
        with body:
            panel.facts(ui, [panel.intro(t("console.community.could_not_read", name=said,
                                           exc=(exc)))])
        return
    relation = declared.get("relation") or {}
    held = (await offload.io(library.owned, [str(one.get(relation["field"]) or "")
                                             for one in found]) if relation else {})
    built = rows(found, declared, held)
    shown = columns(declared)
    scope = f"console.community.{name}.{declared.get('key')}"
    fields = [one["field"] for one in shown]
    body.clear()
    with body:
        with ui.row().classes("w-full items-center gap-2 px-3 py-2 mb-2 shrink-0 "
                              "console-panel console-grid-bar"):
            bar = panel.grid_bar()
            wire_views, _picker, showing, describe = view_control(
                library, scope, presets(declared), fields, shown, bar=bar)
            describe()
            with bar.top, panel.bar_end():
                search = panel.search(t("console.community.search"))
            with bar.bottom, panel.bar_end():
                count = ui.label(t("console.community.rows", count=len(built))) \
                    .classes("text-xs console-label")

        async def on_header_context(col_id: str | None) -> None:
            await grid.header_menu(menu, table, shown, col_id)

        with ui.element("div").classes("w-full grow min-h-0 flex flex-col"):
            table = grid.build(shown, built, scope, on_header_context=on_header_context,
                               view_of=showing)
            menu = ui.context_menu()
        async def counted() -> None:
            seen = await table.run_grid_method("getDisplayedRowCount")
            seen = int(seen if isinstance(seen, int) else len(built))
            count.text = (t("console.community.rows", count=len(built)) if seen == len(built)
                          else t("console.community.rows_of", shown=seen, count=len(built)))

        table.on("modelUpdated", counted)
        wire_views(table)
        search.on_value_change(
            lambda: table.run_grid_method("setGridOption", "quickFilterText",
                                          search.value or ""))
