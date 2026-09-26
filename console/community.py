from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

from nicegui import ui

from common.extensions.host import SWITCHED_OFF
from common.failures import why
from common.games import rankings
from common.games.community_lists import keep, kept
from common.i18n import t
from console import collection_rules, deeplink, grid, offload, panel, tag_chips, verbs, views, when
from console.api import ApiClient, ApiError
from console.data import Library, read_state, sources_of

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


def address(extension: str, key: str) -> str:
    return "/console?" + deeplink.query({"view": view_key(extension, key)})


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


def ranked_orders(extensions: Sequence[dict[str, Any]]) -> dict[str, str]:
    """The order a collection stores for each ranked view, and what the menu calls it."""
    return {rankings.token(str(one.get("name") or ""), str(declared.get("key") or ""),
                           str(view.get("key") or "")):
            ranked_label({"title": declared.get("title"), "name": view.get("name")})
            for one, declared in lists(extensions) for view in rankings.views_of(declared)}


def ranked_label(ranking: dict[str, Any]) -> str:
    """A collection's `ranking` as the order menu and the grid name it."""
    if ranking.get("offered", True):
        return t("order.by.ranked", title=str(ranking.get("title") or ""),
                 name=str(ranking.get("name") or ""))
    return t("order.by.ranked_off", extension=str(ranking.get("display_name")
                                                  or ranking.get("extension") or ""))


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
    out = {view["key"]: views.Preset(
        name=view["name"],
        columns=tuple(view["columns"]),
        sort=tuple({"colId": one["field"], "sort": "desc" if one.get("desc") else "asc",
                    "sortIndex": index} for index, one in enumerate(view.get("sort") or [])),
        help=str(view.get("help") or "")) for view in declared.get("views") or []}
    shown = tuple(one["field"] for one in declared.get("columns") or [])
    first = next(iter(out.values()), None)
    if not out:
        out["console.view.everything"] = views.Preset(columns=shown)
    if related:
        out["console.community.yours"] = views.Preset(
            columns=first.columns if first else shown, filters={HELD: {"values": [True]}},
            help=t("console.community.yours.help"))
    return out


def rows(found: list[dict[str, Any]], declared: dict[str, Any],
         held: dict[str, dict[str, Any]],
         other: dict[str, dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    """`other` is the releases held as another version, by release id."""
    relation = declared.get("relation") or {}
    declared_columns = declared.get("columns") or []
    dates = [one["field"] for one in declared_columns if one.get("kind") == "date"]
    under = list(declared_columns[0].get("under") or []) if declared_columns else []
    out = []
    for index, row in enumerate(found):
        said = str(row.get(relation.get("field", "")) or "") if relation else ""
        mine = held.get(said) if relation else None
        elsewhere = (other or {}).get(said) if relation and not mine else None
        line = " ".join(str(row[one]) for one in under if row.get(one) not in (None, ""))
        href, tip = (_address(mine, relation), t("console.community.held")) if mine else ("", "")
        if elsewhere:
            version = str(elsewhere.get("version") or "")
            tip = (t("console.community.other_version", version=version) if version
                   else t("console.community.other_version_unknown"))
            href = str(elsewhere.get("url") or "")
            line = " · ".join(one for one in (line, tip) if one)
        built = {**row, "id": str(index), HELD: bool(mine), UNDER: line,
                 f"{HELD}_href": href, f"{HELD}_tip": tip}
        for field in dates:
            built = when.said(built, field)
        out.append(built)
    return out


def _address(mine: dict[str, Any], relation: dict[str, Any]) -> str:
    game, table = str(mine.get("game_id") or ""), str(mine.get("table_id") or "")
    if relation.get("keys") == "vps_release" and table:
        return "/console?" + deeplink.query({"view": "tables", "game": game, "table": table})
    return "/console?" + deeplink.query({"view": "games", "game": game})


def read(extension: str, key: str, fetch: Callable[[], dict]) -> dict[str, Any]:
    """Read a list and keep it. A read that fails answers with the last good one, said
    to be stale, and with `rows` None when there is none."""
    try:
        found = [one for one in (fetch() or {}).get("rows") or [] if isinstance(one, dict)]
    except (ApiError, OSError) as exc:
        return {**kept(extension, key), "stale": True, "error": why(exc)}
    return keep(extension, key, found)


def collection_for(collections: Sequence[dict[str, Any]], tag: str) -> str:
    """The smart collection whose rule is this tag alone, or ""."""
    return next((str(one.get("name") or "") for one in collections
                 if one.get("type") == "filter"
                 and collection_rules.named((one.get("filters") or {}).get("tags")) == [tag]),
                "")


def collection_ordered_by(collections: Sequence[dict[str, Any]], order_by: str) -> str:
    """The smart collection in this order, or ""."""
    return next((str(one.get("name") or "") for one in collections
                 if one.get("type") == "filter" and one.get("order_by") == order_by), "")


def free_name(wanted: str, collections: Sequence[dict[str, Any]]) -> str:
    taken = {str(one.get("name") or "").casefold() for one in collections}
    name, number = wanted, 2
    while name.casefold() in taken:
        name = t("console.community.collection_n", name=wanted, n=number)
        number += 1
    return name


def _collection_address(name: str) -> str:
    return "/console?" + deeplink.query({"view": "collections", "collection": name})


async def _make_collection(library: Library, title: str, filters: dict[str, Any]) -> None:
    collections = await offload.io(library.load_collections)
    try:
        made = await offload.io(library.create_collection, free_name(title, collections),
                                filters)
    except Exception as exc:  # noqa: BLE001 - the reason belongs on screen
        ui.notify(t("said.could_not_do_that"), caption=why(exc), type="negative")
        return
    name = str(made.get("name") or "")
    ui.notify(t("console.collections.created", name=name), type="positive")
    ui.navigate.to(_collection_address(name))


def _collection_action(library: Library, existing: str, title: str,
                       filters: dict[str, Any]) -> None:
    if existing:
        panel.action(t("console.community.open_collection"),
                     lambda: ui.navigate.to(_collection_address(existing)),
                     icon=verbs.GO, hint=existing)()
    else:
        panel.action(t("console.community.make_collection"),
                     lambda: _make_collection(library, title, filters),
                     icon=verbs.CREATE)()


def _tag_chip(said: dict[str, Any], library: Library) -> None:
    tag_chips.draw([str(said["tag"])], library.tag_looks())


def _said_age(age: Any, state: dict[str, Any]) -> None:
    age.clear()
    with age:
        panel.line(read_state(state), hint=str(state.get("error") or ""),
                   classes="text-xs console-label")


def as_it_stands(extension: dict[str, Any]) -> dict[str, Any]:
    """The extension as the API has it now, or as given when the API cannot say."""
    name = str(extension.get("name") or "")
    try:
        found = ApiClient().extensions()
    except (ApiError, OSError):
        return extension
    return next((one for one in found if str(one.get("name") or "") == name), extension)


def _why(extension: dict[str, Any]) -> str:
    return str(extension.get("reason") or "") or t("extension.reason.none_recorded")


def not_running(extension: dict[str, Any]) -> None:
    """Drawn in Refresh's place."""
    off = str(extension.get("state") or "") == "off"
    chip = ui.label(t("word.off") if off else t("console.community.stopped")) \
        .classes("console-member-chip "
                 + ("console-chip-quiet" if off else "console-chip-warn"))
    if extension.get("reason_key") != SWITCHED_OFF:
        chip.tooltip(_why(extension))


def build(extension: dict[str, Any], declared: dict[str, Any], library: Library) -> None:
    body = ui.column().classes("w-full grow min-h-0 gap-0")
    ui.timer(0.01, lambda: _fill(extension, declared, library, body), once=True)


async def _fill(extension: dict[str, Any], declared: dict[str, Any], library: Library,
                body: Any) -> None:
    from .games import view_control

    name = str(extension.get("name") or "")
    key = str(declared.get("key") or "")
    said = str(extension.get("display_name") or name)
    tagging, existing = {}, ""
    ranked = rankings.views_of(declared)
    collections = await offload.io(library.load_collections) \
        if declared.get("tag") or ranked else []
    if declared.get("tag"):
        await offload.io(library.read_tags)
        tagging = sources_of(library.tag_looks(), name, key)
        if tagging:
            existing = collection_for(collections, str(tagging["tag"]))
    route = f"/ext/{name}{declared.get('base') or ''}"

    def fetch() -> dict:
        return ApiClient().ext_get(route)

    now = await offload.io(as_it_stands, extension)
    stopped = str(now.get("state") or "") != "loaded"
    state = await offload.io(kept, name, key)
    reading = state["rows"] is None and not stopped
    if stopped:
        state = {**state, "stale": True}
    if reading:
        body.clear()
        with body, ui.row().classes("w-full justify-center py-8"):
            ui.spinner(size="lg").classes("text-primary")
        state = await offload.io(read, name, key, fetch)
    if state["rows"] is None:
        body.clear()
        with body:
            panel.facts(ui, [
                panel.intro(t("console.community.not_running", name=said, reason=_why(now)))
                if stopped else panel.intro(t("console.community.could_not_read", name=said),
                                            hint=str(state["error"]))])
            if tagging:
                with ui.row().classes("items-center gap-2 px-3"):
                    _tag_chip(tagging, library)
        return
    relation = declared.get("relation") or {}

    async def drawn(found: list[dict[str, Any]]) -> list[dict[str, Any]]:
        held, other = (await offload.io(library.owned,
                                        [str(one.get(relation["field"]) or "")
                                         for one in found])
                       if relation else ({}, {}))
        return rows(found, declared, held, other)

    built = await drawn(state["rows"])
    by_id = {row["id"]: row for row in built}
    shown = columns(declared)
    scope = f"console.community.{name}.{key}"
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
                for view in ranked:
                    order_by = rankings.token(name, key, view["key"])
                    with ui.row().classes("items-center gap-2 no-wrap") \
                            .bind_visibility_from(_picker, "value",
                                                  value=views.builtin_id(view["key"])):
                        _collection_action(
                            library, collection_ordered_by(collections, order_by),
                            ranked_label({"title": declared.get("title"),
                                          "name": view.get("name")}),
                            {"order_by": order_by})
                if tagging:
                    ranked_ids = {views.builtin_id(view["key"]) for view in ranked}
                    with ui.row().classes("items-center gap-2 no-wrap") \
                            .bind_visibility_from(_picker, "value",
                                                  backward=lambda on: on not in ranked_ids):
                        _collection_action(library, existing,
                                           str(declared.get("title") or ""),
                                           {"tags": [str(tagging["tag"])]})
                search = panel.search(t("console.community.search"))
            with bar.bottom, panel.bar_end():
                if tagging:
                    _tag_chip(tagging, library)
                age = ui.element("div")
                _said_age(age, state)
                count = ui.label(t("console.community.rows", count=len(built))) \
                    .classes("text-xs console-label")
                if stopped:
                    not_running(now)
                else:
                    again = panel.refresh(lambda: read_again(asked=True),
                                          t("console.community.read_again", name=said))

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

    async def read_again(asked: bool = False) -> None:
        again.disable()
        fresh = await offload.io(read, name, key, fetch)
        found = None if fresh["stale"] else await drawn(fresh["rows"])
        if table.is_deleted:
            return
        again.enable()
        _said_age(age, fresh)
        if found is not None:
            grid.replace_rows(table, built, by_id, found, lambda _row: True)
        elif asked:
            ui.notify(t("console.community.could_not_read", name=said),
                      caption=str(fresh["error"]), type="negative")

    if not reading and not stopped:
        await read_again()
