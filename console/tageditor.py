
"""The tag editor: one row per tag, and the way to fix two spellings of one word.

Entry does not fold case - the picker surfaces close matches and the user decides -
so `sci-fi` and `Sci-Fi` can both exist. This is where that gets cleaned up,
which is why merge is the headline here and rename is the same operation with one
source.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from nicegui import ui

from common.games.tag_registry import derived_color
from common.i18n import t
from console import confirm, grid, offload, panel, renderers, tag_chips, verbs, views
from console.data import Library

SUBJECT = "tag"
LABEL = t("console.tageditor.tags")

SCOPE = "console.tags"

COLUMNS = [
    grid.identifier("tag", t("console.tageditor.tag"), 220, pinned="left",
                    help=t("console.tageditor.tag.help"), **renderers.drawable("tags")),
    grid.column("description", t("console.workbench.description"), 280),
    grid.column("games", t("console.tageditor.games"), type="numericColumn",
                help=t("console.tageditor.games.help")),
    grid.column("tables", t("console.tageditor.tables"), type="numericColumn",
                help=t("console.tageditor.tables.help")),
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
_SHOWN = ("tag", "description", "games", "tables")

VIEWS: dict[str, list[str] | views.Preset] = {
    t("console.view.everything"): views.Preset(
        columns=_SHOWN, help=t("console.view.tags_everything.help")),
    t("console.tageditor.unused"): views.Preset(
        columns=_SHOWN, filters={"unused": {"values": [True]}},
        help=t("console.view.tags_unused.help")),
    t("console.tageditor.two_spellings"): views.Preset(
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
            ui.notify(t("said.could_not_do_that", exc=(exc)), type="negative")
            return
        ui.notify(t("console.tageditor.game_changed", said=(said), changed=(changed),
                value=('' if changed == 1 else 's')),
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

    async def rename(row: dict[str, Any]) -> None:
        said = await _ask_for_a_name(str(row.get("tag") or ""))
        if not said or said == row.get("tag"):
            return
        await sweep(library.merge_tags, [str(row.get("tag"))], said,
                    said=t("console.tageditor.renamed", said=(said)))

    async def drop(row: dict[str, Any]) -> None:
        tag = str(row.get("tag") or "")
        count = int(row.get("games") or 0)
        if not await confirm.ask(
                t("console.tageditor.remove_every_game", tag=(tag)),
                detail=t("console.tageditor.delete_detail", count=count),
                confirm=t("word.remove"), icon=verbs.REMOVE):
            return
        await sweep(library.delete_tag, tag, said=t("console.tageditor.removed", tag=(tag)))

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
            ui.notify(t("said.could_not_do_that", exc=(exc)), type="negative")
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

    def fill(row: dict | None) -> None:
        menu.clear()
        if not row:
            return
        with menu:
            ui.item_label(str(row.get("tag") or "")).props("header") \
                .classes("console-menu-header")
            ui.separator()
            ui.menu_item(t("console.tageditor.rename"),
                    lambda r=row: rename(r)).classes("console-menu-item")
            ui.menu_item(t("console.tageditor.remove_every_game_2"), lambda r=row: drop(r)) \
                .classes("console-menu-item console-menu-danger")

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
        with ui.element("div").classes("console-fact-edit"):
            fields["name"] = ui.input().props("dense borderless debounce=0") \
                .classes("console-edit-field")
        fields["name"].on_value_change(renamed)

    def renamed() -> None:
        refused("")
        draw_colors()

    def draw_said() -> None:
        with ui.element("div").classes("console-fact-edit"):
            fields["said"] = ui.textarea().props("dense borderless rows=2 debounce=0") \
                .classes("console-edit-field")

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
            refused(t("console.tageditor.give_it_a_name"))
        elif name in known:
            refused(t("console.tageditor.already_a_tag"))
        else:
            dialog.submit((name, {"description": str(fields["said"].value or "").strip(),
                                  "color": held["color"]}))

    with ui.dialog() as dialog, ui.card().classes("console-new-tag"):
        ui.label(t("console.tageditor.add_new_tag")).classes("console-card-title")
        panel.facts(ui, [(t("console.tageditor.tag"), draw_name),
                         (t("console.workbench.description"), draw_said),
                         (t("console.tags.color"), draw_colors)])
        with ui.row().classes("justify-end gap-2 w-full"):
            ui.button(t("word.cancel"), icon=verbs.CANCEL,
                      on_click=lambda: dialog.submit(None)).props("flat no-caps")
            add = ui.button(t("word.add"), icon=verbs.CREATE, on_click=keep) \
                .props("no-caps")
    dialog.on("show", lambda: ui.run_javascript(
        f"document.getElementById('c{fields['name'].id}').focus()"))
    ui.run_javascript(f"""
        (() => {{
          let tries = 0;
          const wire = () => {{
            const button = document.getElementById('c{add.id}');
            if (!button) {{ if (++tries < 40) setTimeout(wire, 25); return; }}
            button.closest('.q-dialog').addEventListener('keyup', (event) => {{
              if (event.key === 'Enter' && event.target.tagName !== 'TEXTAREA') button.click();
            }});
          }};
          wire();
        }})()
    """)
    return await dialog


def _named(fields: dict[str, Any]) -> str:
    return " ".join(str(fields["name"].value or "").split())


async def _ask_for_a_name(current: str, *, title: str = "", help_: str = "",
                          verb: str = "") -> str:
    """A dialog that collects a value keeps its own shape - `docs/conventions.md` says
    the confirm treatment is for a question, not for a field."""
    with ui.dialog() as dialog, ui.card().classes("console-confirm"):
        ui.label(title or t("console.tageditor.rename_tag")).classes("console-confirm-title")
        ui.label(help_ or t("console.tageditor.every_game_carrying_retagged")) \
            .classes("console-help")
        field = ui.input(value=current).props("dense autofocus") \
            .classes("console-edit-field w-full")
        with ui.row().classes("justify-end gap-2 w-full"):
            ui.button(t("word.cancel"), icon=verbs.CANCEL,
                    on_click=lambda: dialog.submit("")).props("flat no-caps")
            ui.button(verb or t("console.tageditor.rename_2"),
                      icon=verbs.CREATE if verb else verbs.RENAME,
                      on_click=lambda: dialog.submit(field.value or "")) \
                .props("no-caps")
    return str(await dialog or "")
