
"""One extension's own page: what it is set to, what it can be asked to do, what it holds.

Core draws all of it. The extension says what its settings are, what its actions are and
what it is holding; none of the treatment is its own, so an extension's page looks like
the Console rather than like whoever wrote it - and it keeps working if that extension
later runs somewhere else.

Three groups, in the order somebody needs them: configure it, run it, see what came of it.
What it may reach is at the bottom, because that is a question somebody asks once and
nobody asks while using it.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from nicegui import run, ui

from common.i18n import t
from console import ext_action, offload, panel, verbs
from console.api import ApiClient


def build(extension: dict, back: Any) -> None:
    """Draw the page for one extension."""
    name = str(extension.get("name") or "")
    surfaces = dict(extension.get("surfaces") or {})

    with ui.row().classes("items-center gap-2 w-full"):
        ui.button(icon="arrow_back", on_click=lambda: back()) \
            .props("flat dense round").tooltip(t("console.ext_page.back_extensions"))
        ui.label(str(extension.get("display_name") or name)) \
            .classes("text-base console-workbench-title console-panel-heading")
        version = str(extension.get("version") or "")
        if version:
            ui.label(version).classes("console-help")
    if extension.get("description"):
        ui.label(str(extension["description"])).classes("console-help mb-2")

    if surfaces.get("settings"):
        _settings(name, surfaces)
    _actions(extension, name)
    if surfaces.get("state"):
        _state(name, surfaces)
    _reach(extension)


def _settings(name: str, surfaces: dict) -> None:
    """What the extension is configured with, saved as each field is left."""
    ui.label(str(surfaces.get("settings_label") or t("console.ext_page.settings"))) \
        .classes("console-group mt-4")
    card = ui.element("div").classes("console-card w-full")
    base = f"/ext/{name}{surfaces['settings']}"
    client = ApiClient()

    async def draw() -> None:
        try:
            found = await offload.io(client.ext_get, base)
        except Exception as exc:  # noqa: BLE001
            card.clear()
            with card:
                ui.label(t("console.ext_page.could_not_read_them",
                        exc=(exc))).classes("console-help")
            return
        card.clear()
        with card:
            if found.get("help"):
                ui.label(str(found["help"])).classes("console-help mb-2")
            entries: list[tuple[Any, Any]] = []
            for field in found.get("fields") or []:
                key = str(field.get("key") or "")
                if not key:
                    continue
                entries.append((str(field.get("label") or key),
                                _control(client, base, key, field, draw)))
                if field.get("help"):
                    entries.append((panel.ASIDE, _aside(str(field["help"]))))
            if entries:
                panel.facts(ui, entries)

    ui.timer(0, draw, once=True)


def _control(client: Any, base: str, key: str, field: dict,
             redraw: Callable[[], Awaitable[None]]) -> Any:
    """One setting, in the control its type asks for."""
    kind = str(field.get("type") or "string")
    value = field.get("value")

    async def save(new_value: Any) -> None:
        try:
            await run.io_bound(client.ext_put, base, {"values": {key: new_value}})
        except Exception as exc:  # noqa: BLE001
            ui.notify(str(exc), type="negative")
            return
        await redraw()

    if kind == "switch":
        return panel.switch(bool(value), lambda event: save(bool(event.value)))
    if kind == "select":
        choices = {str(one[0]): str(one[1]) for one in field.get("choices") or []}
        return panel.select(choices, str(value or ""), lambda event: save(event.value))
    return panel.field(str(value or ""), save,
                       placeholder=str(field.get("placeholder") or ""))


def _aside(text: str) -> Any:
    def draw() -> None:
        ui.label(text).classes("console-help")
    return draw


def _actions(extension: dict, name: str) -> None:
    offered = list(extension.get("actions") or [])
    if not offered:
        return
    ui.label(t("word.actions")).classes("console-group mt-4")
    with ui.element("div").classes("console-card w-full"), \
            ui.row().classes("items-center gap-2 w-full flex-wrap"):
        for action in offered:
            ui.button(str(action.get("label") or action.get("key") or ""),
                      icon=verbs.RUN,
                      on_click=lambda _e=None, action=action:
                          ext_action.open_action(name, action)) \
                .props("no-caps outline") \
                .tooltip(str(action.get("description") or ""))


def _state(name: str, surfaces: dict) -> None:
    """What the extension is holding, and the couple of things you can do to a row."""
    ui.label(str(surfaces.get("state_label") or t("console.ext_page.held"))) \
        .classes("console-group mt-4")
    card = ui.element("div").classes("console-card w-full")
    base = f"/ext/{name}{surfaces['state']}"
    client = ApiClient()

    async def draw() -> None:
        try:
            found = await offload.io(client.ext_get, base)
        except Exception as exc:  # noqa: BLE001
            card.clear()
            with card:
                ui.label(t("console.ext_page.could_not_read", exc=(exc))).classes("console-help")
            return
        card.clear()
        rows = list(found.get("rows") or [])
        with card:
            if not rows:
                # The empty state is the extension's to word: it knows what would be
                # here and why there is none.
                ui.label(str(found.get("empty") or t("console.ext_page.nothing_yet"))) \
                    .classes("console-help")
                return
            for row in rows:
                _row(client, base, row, draw)

    ui.timer(0, draw, once=True)


def _row(client: Any, base: str, row: dict, redraw: Callable[[], Awaitable[None]]) -> None:
    async def press(key: str) -> None:
        try:
            await run.io_bound(client.ext_post, f"{base}/{key}",
                               {"id": str(row.get("id") or "")})
        except Exception as exc:  # noqa: BLE001
            ui.notify(str(exc), type="negative")
            return
        await redraw()

    with ui.row().classes("items-center gap-2 w-full console-member-row"):
        with ui.column().classes("gap-0 min-w-0 grow"):
            with ui.row().classes("items-center gap-2"):
                ui.label(str(row.get("label") or "")).classes("console-setting")
                # A mark on the one row that is different, never on all of them.
                if row.get("mark"):
                    ui.label(str(row["mark"])) \
                        .classes("console-member-chip console-chip-quiet")
            if row.get("detail"):
                ui.label(str(row["detail"])).classes("console-help")
        # Two at most, and that is the whole of what a row can offer.
        for action in list(row.get("actions") or [])[:2]:
            key = str(action.get("key") or "")
            ui.button(str(action.get("label") or ""), icon=verbs.RUN,
                      on_click=lambda _e=None, key=key: press(key)) \
                .props("flat dense no-caps")


# What a scope or capability is called on screen. The wire says `games:write`; a person
# reading a consent list should not have to work out what that lets somebody do.
PLAINLY = {
    "games:read": t("console.ext_page.read_library"),
    "games:write": t("console.ext_page.add_change_games"),
    "filesystem:read": t("console.ext_page.read_folders_point"),
    "ui:mount": t("console.ext_page.add_page_console"),
    "config:own": t("console.ext_page.keep_own_settings"),
    "net:outbound": t("console.ext_page.reach_internet"),
    "proc:spawn": t("console.ext_page.run_other_programs"),
    "hardware:usb": t("console.ext_page.talk_usb_devices"),
    "fs:read": t("console.ext_page.read_files"),
    "fs:write": t("console.ext_page.write_files"),
}


def _plainly(name: str) -> str:
    """Its own name is the fallback, never a guess: an unknown scope shown as prose
    somebody invented is worse than one shown as it is."""
    return PLAINLY.get(name, name)


def _reach(extension: dict) -> None:
    """What this extension may do, for whoever came looking.

    At the bottom and never on the list of what is installed: a scope is what somebody
    agrees to when installing something, and in front of everybody else it is jargon.
    """
    reaches = [_plainly(str(one)) for one in extension.get("scopes") or []]
    uses = [_plainly(str(one)) for one in extension.get("capabilities") or []]
    if not reaches and not uses:
        return
    ui.label(t("console.ext_page.what_can_reach")).classes("console-group mt-4")
    with ui.element("div").classes("console-card w-full"):
        entries: list[tuple[Any, Any]] = []
        if reaches:
            entries.append((t("console.ext_page.library"), ", ".join(reaches)))
        if uses:
            entries.append((t("console.ext_page.machine"), ", ".join(uses)))
        panel.facts(ui, entries)
