
"""The tag editor: one row per tag, and the way to fix two spellings of one word.

Entry does not fold case - the picker surfaces close matches and the user decides -
so `sci-fi` and `Sci-Fi` can both exist. This is where that gets cleaned up,
which is why merge is the headline here and rename is the same operation with one
source.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from functools import partial
from typing import Any

from nicegui import ui

from common.failures import why
from common.games.tag_registry import derived_color
from common.i18n import t
from console import confirm, grid, offload, panel, renderers, tag_chips, verbs, views
from console import dialog as frame
from console.data import Library

SUBJECT = "tag"
LABEL = t("console.tageditor.tags")

SCOPE = "console.tags"

COLUMNS = [
    grid.identifier("tag", t("console.tageditor.tag"), 220, pinned="left",
                    help=t("console.tageditor.tag.help"),
                    **renderers.drawable("chips", list="tag_list",
                                         looks=renderers.TAG_LOOKS)),
    grid.column("description", t("console.workbench.description"), 280),
    grid.column("games", t("console.tageditor.games"), type="numericColumn",
                help=t("console.tageditor.games.help")),
    grid.column("tables", t("console.tageditor.tables"), type="numericColumn",
                help=t("console.tageditor.tables.help")),
    grid.column("source", t("console.tags.from"), 200, help=t("console.tags.from.help")),
    grid.column("unused", t("console.tageditor.unused"), 120,
                **grid.choice_filter([{"value": True, "label": t("console.tageditor.unused")},
                                      {"value": False, "label": t("console.tageditor.in_use")}],
                                     formatted=True)),
    grid.column("duplicate", t("console.tageditor.two_spellings"), 140,
                **grid.choice_filter(
                    [{"value": True, "label": t("console.tageditor.two_spellings")},
                     {"value": False, "label": t("console.tageditor.one_spelling")}],
                    formatted=True)),
    grid.column("same", t("console.tageditor.spelled_as"), 160,
                help=t("console.tageditor.spelled_as.help")),
]
_ALL = [one["field"] for one in COLUMNS]
_SHOWN = ("tag", "description", "games", "tables", "source")

VIEWS: dict[str, list[str] | views.Preset] = {
    "console.view.everything": views.Preset(
        columns=_SHOWN, help=t("console.view.tags_everything.help")),
    "console.tageditor.unused": views.Preset(
        columns=_SHOWN, filters={"unused": {"values": [True]}},
        help=t("console.view.tags_unused.help")),
    "console.tageditor.two_spellings": views.Preset(
        columns=_SHOWN, filters={"duplicate": {"values": [True]}},
        sort=({"colId": "same", "sort": "asc", "sortIndex": 0},
              {"colId": "games", "sort": "desc", "sortIndex": 1}),
        help=t("console.view.tags_two_spellings.help")),
}


def rows_by_key(rows: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    """The spellings that share a word, most-used first inside each group.

    Only groups with more than one member: a tag nobody has spelled twice is not
    something to act on, and listing it would bury the ones that are.
    """
    groups: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        if row.get("sources"):
            continue
        groups.setdefault(str(row.get("same") or ""), []).append(row)
    return [sorted(group, key=lambda r: (-int(r.get("games") or 0), str(r.get("tag"))))
            for group in groups.values() if len(group) > 1]


def build(rows: list[dict[str, Any]], library: Any,
          on_select: Callable[[dict | None], Any],
          state: dict[str, Any],
          rerender: Callable[[], None] | None = None) -> None:
    """The editor. The duplicates lead, because they are what somebody came here for."""
    tag_chips.install(library.tag_looks())
    async def sweep(call: Callable[..., Any], *args: Any, said: str = "") -> None:
        try:
            changed = await offload.io(call, *args)
        except Exception as exc:
            ui.notify(t("said.could_not_do_that"), caption=why(exc), type="negative")
            return
        ui.notify(t("console.tageditor.game_changed", said=said, count=changed),
                  type="positive")
        if rerender is not None:
            rerender()

    async def merge(group: list[dict[str, Any]]) -> None:
        into = str(group[0].get("tag") or "")
        others = [str(r.get("tag")) for r in group[1:]]
        if not await confirm.ask(
                t("console.tageditor.merge", into=(into)),
                detail=t("console.tageditor.every_game_carrying_one"),
                lines=[t("console.tageditor.tag_game" if r["games"] == 1
                         else "console.tageditor.tag_games",
                         tag=r["tag"], count=r["games"]) for r in group[1:]],
                confirm=t("word.merge"), icon=verbs.MERGE):
            return
        await sweep(library.merge_tags, others + [into], into,
                said=t("console.tageditor.merged", into=(into)))

    duplicates = rows_by_key(rows)
    if duplicates:
        with ui.element("div").classes("console-card w-full mb-2"):
            ui.label(t("console.tageditor.look_like_same_tag")).classes("console-card-title")
            ui.label(t("console.tageditor.entry_keeps_what_typed")) \
                .classes("console-help")
            for group in duplicates:
                with ui.row().classes("items-center gap-2 w-full no-wrap "
                                      "console-member-row"):
                    ui.label(" · ".join(f"{r['tag']} ({r['games']})" for r in group)) \
                        .classes("console-member-name grow min-w-0 truncate")
                    ui.button(t("word.merge"),
                        icon=verbs.MERGE, on_click=lambda _, g=group: merge(g)) \
                        .props("flat dense no-caps size=sm") \
                        .classes("console-action console-action--inline")

    async def write_down() -> None:
        wanted = await _new_tag(library)
        if not wanted:
            return
        name, changes = wanted
        try:
            await offload.io(library.put_tag, name, changes)
        except Exception as exc:
            ui.notify(t("said.could_not_do_that"), caption=why(exc), type="negative")
            return
        if rerender is not None:
            rerender()

    from .games import view_control

    with ui.row().classes("w-full items-center gap-2 px-3 py-2 mb-2 shrink-0 "
                          "console-panel console-grid-bar"):
        bar = panel.grid_bar()
        wire_views, _picker, showing, describe = view_control(
            library, SCOPE, VIEWS, _ALL, COLUMNS, bar=bar)
        describe()
        with bar.top, panel.bar_end():
            search = panel.search(t("console.tageditor.search_tags"))
        with bar.bottom, panel.bar_end():
            count = ui.label(t("console.tageditor.tags_counted", count=len(rows))) \
                .classes("text-xs console-label")
            panel.add_action([(t("console.tageditor.new_tag"), write_down)],
                             empty=not rows)

    if not rows:
        ui.label(t("console.tageditor.no_tags_yet_tag")) \
            .classes("console-help p-4")
        return
    by_id = {row["id"]: row for row in rows}

    menu_row: dict[str, Any] = {}

    async def redrawn(_next: str | None) -> None:
        if rerender is not None:
            rerender()

    def fill(row: dict | None) -> None:
        if not row:
            menu.clear()
            return
        tag = str(row.get("tag") or "")
        panel.verb_menu(menu, tag, acts(library, tag, int(row.get("games") or 0), redrawn))

    def on_context(row: dict | None) -> None:
        menu_row["row"] = row
        fill(row)

    with ui.element("div").classes("w-full grow min-h-0 flex flex-col"):
        table = grid.build(COLUMNS, rows, SCOPE, on_context=on_context, view_of=showing)
        menu = ui.context_menu()
    wire_views(table)

    async def counted() -> None:
        seen = await table.run_grid_method("getDisplayedRowCount")
        seen = int(seen if isinstance(seen, int) else len(rows))
        count.text = (t("console.tageditor.tags_counted", count=len(rows)) if seen == len(rows)
                      else t("console.tageditor.tags_of", shown=seen, count=len(rows)))

    table.on("modelUpdated", counted)
    grid.on_row_focus(SCOPE, lambda event: on_select(by_id.get(grid.focused_row(event))))
    search.on_value_change(
        lambda: table.run_grid_method("setGridOption", "quickFilterText",
                                      search.value or ""))

    async def refresh_rows() -> None:
        fresh = library.tag_rows()
        by_id.clear()
        by_id.update({row["id"]: row for row in fresh})
        tag_chips.install(library.tag_looks())
        table.run_grid_method("setGridOption", "rowData", fresh)
        table.run_grid_method("refreshCells", {"force": True})

    state["refresh_tags"] = refresh_rows


async def _new_tag(library: Library) -> tuple[str, dict[str, str]] | None:
    """The panel's three fields, asked before anything carries the tag."""
    known = set(library.tag_looks())
    held: dict[str, Any] = {"color": ""}
    fields: dict[str, Any] = {}

    def draw_name() -> None:
        fields["name"] = frame.field()
        fields["name"].on_value_change(renamed)

    def renamed() -> None:
        refused("")
        draw_colors()

    def draw_said() -> None:
        fields["said"] = frame.field(lines=2)

    def draw_colors() -> None:
        box = fields.get("colors") or ui.element("div")
        fields["colors"] = box
        box.clear()
        with box:
            tag_chips.swatches(held["color"], derived_color(_named(fields)), pick)

    def pick(color: str) -> None:
        held["color"] = color
        draw_colors()

    def refused(why: str) -> None:
        fields["name"].props["error"] = bool(why)
        fields["name"].props["error-message"] = why

    def keep() -> None:
        name = _named(fields)
        if not name:
            refused(t("said.give_it_a_name"))
        elif name in known:
            refused(t("console.tageditor.already_a_tag"))
        else:
            box.submit((name, {"description": str(fields["said"].value or "").strip(),
                               "color": held["color"]}))

    with frame.opened(t("console.tageditor.add_new_tag")) as box:
        panel.facts(ui, [(t("console.tageditor.tag"), draw_name),
                         (t("console.workbench.description"), draw_said),
                         (t("console.tags.color"), draw_colors)])
        with frame.footer():
            frame.cancel(lambda: box.submit(None))
            add = frame.answer(t("word.add"), keep, icon=verbs.CREATE)
    frame.focus(box, fields["name"])
    frame.enter_presses(add)
    return await box


def acts(library: Any, tag: str, games: int,
         after: Callable[[str | None], Awaitable[None]]) -> list[panel.Verb]:
    """What can be done to one tag. `after` is given the tag to show next, or None when
    this one has gone."""
    derived = library.derived_tags()
    if tag in derived:
        return []
    others = sorted((one for one in library.tag_looks() if one != tag and one not in derived),
                    key=str.casefold)

    async def rename() -> None:
        said = await _ask_for_a_name(tag)
        if not said or said == tag:
            return
        try:
            await offload.io(library.merge_tags, [tag], said)
        except Exception as exc:  # noqa: BLE001
            ui.notify(t("said.could_not_do_that"), caption=why(exc), type="negative")
            return
        ui.notify(t("console.tageditor.renamed", said=(said)), type="positive")
        await after(said)

    async def merge(into: str) -> None:
        if not await confirm.ask(t("console.tageditor.merge", into=into),
                                 detail=t("console.tageditor.every_game_carrying_one"),
                                 lines=[t("console.tageditor.tag_game" if games == 1
                                          else "console.tageditor.tag_games",
                                          tag=tag, count=games)],
                                 confirm=t("word.merge"), icon=verbs.MERGE):
            return
        try:
            await offload.io(library.merge_tags, [tag], into)
        except Exception as exc:  # noqa: BLE001
            ui.notify(t("said.could_not_do_that"), caption=why(exc), type="negative")
            return
        ui.notify(t("console.tageditor.merged", into=(into)), type="positive")
        await after(into)

    async def delete() -> None:
        if not await confirm.ask(t("console.tageditor.delete", tag=tag),
                                 detail=t("console.tageditor.delete_detail", count=games),
                                 confirm=t("word.delete"), icon=verbs.DELETE):
            return
        try:
            await offload.io(library.delete_tag, tag)
        except Exception as exc:  # noqa: BLE001
            ui.notify(t("said.could_not_do_that"), caption=why(exc), type="negative")
            return
        ui.notify(t("console.tageditor.deleted", tag=tag), type="positive")
        await after(None)

    offered = [panel.Verb(t("console.tageditor.rename"), rename, in_panel=False)]
    if others:
        offered.append(panel.Verb(t("console.tags.merge_into"), choices=tuple(
            (other, partial(merge, other)) for other in others)))
    offered.append(panel.Verb(t("word.delete"), delete, danger=True))
    return offered


def _named(fields: dict[str, Any]) -> str:
    return " ".join(str(fields["name"].value or "").split())


async def _ask_for_a_name(current: str, *, title: str = "", help_: str = "",
                          verb: str = "") -> str:
    held: dict[str, Any] = {}
    with frame.opened(title or t("console.tageditor.rename_tag")) as box:
        ui.label(help_ or t("console.tageditor.every_game_carrying_retagged")) \
            .classes("console-help px-3")
        panel.facts(ui, [(t("console.tageditor.tag"),
                          lambda: held.update(field=frame.field(current)))])
        with frame.footer():
            frame.cancel(lambda: box.submit(""))
            go = frame.answer(verb or t("console.tageditor.rename_2"),
                              lambda: box.submit(held["field"].value or ""),
                              icon=verbs.CREATE if verb else verbs.RENAME)
    frame.focus(box, held["field"])
    frame.enter_presses(go)
    return str(await box or "")
