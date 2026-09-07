"""The program's own settings for one table, opened over the workbench.

One component, two ways in. The launcher's rail opens it fixed to that launcher and
shows every group; this opens it for a table, where the question is almost always one
setting and the scope arrives already correct. Somebody who has never seen this screen
should be able to change one setting for one table without touching the scope picker.

Scopes are named for what they do rather than for the files behind them. A person thinks
"the DMD off for this one table" or "hide the grill on everything"; a filename belongs in
a tooltip and in the log, nowhere else.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from nicegui import run, ui

from console import confirm, panel

# One definition of both: the launcher's rail and this dialog are the same surface at
# two scopes, and two spellings of "a table is playing" would drift.
from console.workbench import PLAYING_NOTE, _playing

logger = logging.getLogger("vpinfe.console.app_settings")

SCOPE_ENTRY = "entry"
SCOPE_FOLDER = "folder"
SCOPE_LAUNCHER = "launcher"


def scope_words(folder_tables: int, launcher_name: str) -> dict[str, str]:
    """What each scope is called, with the folder saying how many it reaches - a folder
    of one is a fact worth seeing before choosing it over the table."""
    return {
        SCOPE_ENTRY: "This table",
        SCOPE_FOLDER: (f"This folder - {folder_tables} tables" if folder_tables != 1
                       else "This folder - 1 table"),
        SCOPE_LAUNCHER: f"Everything {launcher_name} plays",
    }


async def open_for_table(library, *, launcher_id: str, launcher_name: str,
                         table_id: str, folder_tables: int = 1,
                         on_done: Callable | None = None) -> None:
    if not launcher_id:
        ui.notify("This table has no launcher to configure.", type="warning")
        return

    state: dict[str, Any] = {"scope": SCOPE_ENTRY, "search": ""}
    words = scope_words(folder_tables, launcher_name or "this launcher")

    with ui.dialog().props("maximized") as dialog, ui.card().classes(
            "w-full h-full console-panel"):
        with ui.row().classes("items-center gap-3 w-full no-wrap px-3 pt-2"):
            ui.label(f"{launcher_name} settings").classes("console-card-title")
            ui.space()
            ui.button("Done", on_click=dialog.close).props("flat dense no-caps")

        # The picker before the settings, because it says where an edit will go and
        # that has to be readable before anything is edited rather than after.
        with ui.row().classes("items-center gap-3 w-full no-wrap px-3 pb-2"):
            ui.label("Edits go to").classes("console-label text-xs")
            scope = ui.select(words, value=state["scope"]) \
                .props("dense outlined options-dense").classes("w-64")
            search = panel.search("Search settings")

        body = ui.column().classes("w-full grow min-h-0 gap-0 overflow-auto")

        async def draw() -> None:
            body.clear()
            with body:
                await _fill(library, launcher_id, table_id, state, words, draw)

        scope.on_value_change(lambda: _pick(state, scope.value, draw))
        search.on_value_change(lambda: _find(state, search.value or "", draw))
        await draw()

    dialog.on("hide", lambda: on_done() if callable(on_done) else None)
    dialog.open()


def _pick(state: dict[str, Any], chosen: Any, draw: Callable) -> Any:
    state["scope"] = str(chosen or SCOPE_ENTRY)
    return draw()


def _find(state: dict[str, Any], text: str, draw: Callable) -> Any:
    state["search"] = text.strip().lower()
    return draw()


async def _fill(library, launcher_id: str, table_id: str, state: dict[str, Any],
                words: dict[str, str], draw: Callable) -> None:
    scope = state["scope"]
    try:
        found = await run.io_bound(library.launcher_config, launcher_id,
                                   table_id, scope)
    except Exception as exc:  # noqa: BLE001 - this says why, never 500s
        panel.facts(ui, [panel.intro(f"Could not read the settings: {exc}")])
        return

    groups = found.get("groups") or []
    values = found.get("values") or {}
    playing = await run.io_bound(_playing, library)
    if playing:
        panel.facts(ui, [panel.note(PLAYING_NOTE)])
    wanted = state["search"]
    shown = 0
    for group in groups:
        rows = [f for f in group["settings"]
                if not wanted or wanted in f["label"].lower()
                or wanted in f["key"].lower()]
        if not rows:
            continue
        shown += len(rows)
        panel.header(group["label"])
        await _group_rows(library, launcher_id, table_id, scope, rows, values, draw,
                          playing)

    if not shown:
        panel.facts(ui, [panel.intro(
            f"Nothing matches “{state['search']}”." if wanted
            else f"{words[scope]} has no settings to show.")])


async def _group_rows(library, launcher_id: str, table_id: str, scope: str,
                      rows: list[dict], values: dict, draw: Callable,
                      playing: bool = False) -> None:
    """One group's settings, with where each value comes from and the way off it."""
    entries: list[tuple[Any, Any]] = []
    for field in rows:
        held = values.get(field["key"]) or {}
        entries.append((field["label"],
                        _control(library, launcher_id, table_id, scope, field,
                                 held, draw, playing)))
        aside = _aside(library, launcher_id, table_id, scope, field, held, draw,
                       playing)
        if aside is not None:
            entries.append((panel.ASIDE, aside))
        if field.get("description"):
            entries.append(panel.note(field["description"]))
    with ui.column().classes("gap-0 console-form"):
        panel.facts(ui, entries)


def _control(library, launcher_id: str, table_id: str, scope: str, field: dict,
             held: dict, draw: Callable, playing: bool = False) -> Callable[[], None]:
    """The control always shows the effective value: you never look at a number that is
    not the one the program will use."""
    from console import settings as settings_page

    async def save(value: Any) -> bool:
        # Giving a table its own file takes it off the folder's, so what the folder is
        # currently giving it has to be shown before that happens rather than found
        # afterwards. Only on the write that creates the file.
        if scope == SCOPE_ENTRY and not held.get("set_here"):
            if not await confirm_new_table_file(library, launcher_id, table_id):
                await draw()
                return False
        try:
            await run.io_bound(library.write_launcher_config, launcher_id,
                               {field["key"]: _as_text(value)},
                               table=table_id, scope=scope)
        except Exception as exc:  # noqa: BLE001
            ui.notify(f"Could not save it: {exc}", type="negative")
            return False
        await draw()
        return True

    option = dict(field)
    if field.get("choices"):
        option["choices"] = {value: label for value, label in field["choices"]}
        option["type"] = "choice"
    # `or`, not a default argument: a setting nobody has touched has an empty effective
    # value, and a closed set of answers has no option spelled "". The control shows what
    # the program will use, which for an untouched setting is its own default.
    return settings_page.control_for(
        option, settings_page.value_for(option, held.get("value")), save,
        writable=not playing)


def _aside(library, launcher_id: str, table_id: str, scope: str, field: dict,
           held: dict, draw: Callable,
           playing: bool = False) -> Callable[[], None] | None:
    from console import workbench

    mark = workbench._config_mark(held, scope)
    if mark is None:
        return None

    async def wipe() -> None:
        try:
            await run.io_bound(library.write_launcher_config, launcher_id,
                               {field["key"]: ""}, table=table_id, scope=scope)
        except Exception as exc:  # noqa: BLE001
            ui.notify(f"Could not clear it: {exc}", type="negative")
            return
        await draw()

    class _Field:
        type = field.get("type", "")
        choices = tuple(tuple(pair) for pair in field.get("choices") or ())
        default = field.get("default", "")

    def drawn() -> None:
        with ui.row().classes("items-center gap-2 no-wrap"):
            mark()
            if held.get("set_here"):
                panel.action("Clear", wipe, inline=True, enabled=not playing,
                             hint=(workbench.PLAYING_NOTE if playing
                                   else workbench._clear_hint(held, _Field)))()
    return drawn


def _as_text(value: Any) -> str:
    if isinstance(value, bool):
        return "1" if value else "0"
    return "" if value is None else str(value)


async def confirm_new_table_file(library, launcher_id: str, table_id: str) -> bool:
    """Asked before a table gets a file of its own, where a folder file is reaching it.

    The two do not stack: once a table has its own file, the folder's other keys stop
    reaching it and fall through to the launcher. Keeping them is the default, because
    the alternative changes what the table does without saying so.
    """
    try:
        reaching = await run.io_bound(library.folder_settings_reaching, launcher_id,
                                      table_id)
    except Exception:  # noqa: BLE001 - a confirm must not be the thing that breaks
        logger.exception("Could not read what the folder gives this table")
        return True
    if not reaching:
        return True
    count = len(reaching)
    return await confirm.ask(
        f"{count} setting{'' if count == 1 else 's'} currently reach this table "
        "from its folder.",
        detail="Giving this table its own settings stops the folder reaching it, so "
               "they are copied across and nothing it does changes. Everything else in "
               "the folder is unaffected.",
        confirm="Keep them")
