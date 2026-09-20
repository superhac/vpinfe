
"""The frontend themes this install knows, and which one plays.

Cards rather than a grid. A theme is chosen by looking at it - the preview is the point,
and a row of text columns is the one shape that cannot show one.

Active first, then installed, then the rest, which is the order somebody scans in: what
am I running, what could I switch to without downloading, what else is there.

**Configure renders the theme's own schema, not ours.** A theme declares its options in
its own manifest and this install has no opinion about what they can be. What a person
chooses is kept *outside* the theme package - an update deletes the package, and values
written into it were reset by the next update every time.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from typing import Any

from nicegui import run, ui

from common.i18n import t
from console import confirm, offload, panel, settings
from console.data import Library

logger = logging.getLogger("vpinfe.console.themes")

# What a theme says it needs. Named here because a number is not an answer: "3" is a
# cabinet, and somebody choosing a theme is choosing against the screens they have.
SCREENS = {1: t("console.themes.desktop"), 2: t("console.themes.two_screens"),
        3: t("console.themes.cabinet")}


def build(library: Library, state: dict[str, Any], redraw: Callable[[], None]) -> None:
    body = ui.column().classes("w-full gap-3")
    ui.timer(0.01, lambda: _fill(library, state, redraw, body, refresh=False),
             once=True)


async def _fill(library: Library, state: dict[str, Any], redraw: Callable[[], None], body: Any,
                refresh: bool) -> None:
    try:
        found = await offload.io(library.themes, refresh)
    except Exception as exc:  # noqa: BLE001 - this page says why, never 500s
        body.clear()
        with body:
            panel.facts(ui, [panel.intro(t("console.themes.could_not_read_themes", exc=(exc)))])
        return

    themes = list(found.get("themes") or [])
    body.clear()
    with body:
        with ui.row().classes("items-center gap-2 w-full no-wrap px-1 pt-1"):
            ui.label(t("console.themes.what_frontend_looks_like")) \
                .classes("console-help grow min-w-0")
            ui.button(t("console.themes.check_updates"), icon="refresh",
                      on_click=lambda: _fill(library, state, redraw, body,
                                             refresh=True)) \
                .props("flat dense no-caps size=sm")
        if not themes:
            panel.facts(ui, [panel.intro(
                t("console.themes.no_theme_sources_configured"))])
            return
        for theme in themes:
            _card(library, state, redraw, body, theme)


def _card(library: Library, state: dict[str, Any], redraw: Callable[[], None], body: Any,
          theme: dict[str, Any]) -> None:
    classes = "console-card w-full console-theme-card"
    if theme["active"]:
        classes += " console-theme-card--active"
    with ui.element("div").classes(classes):
        with ui.row().classes("w-full gap-4 no-wrap items-start"):
            _preview(theme)
            with ui.column().classes("gap-1 grow min-w-0"):
                _heading(theme)
                if theme.get("description"):
                    ui.label(theme["description"]).classes("console-help")
                ui.label(_said(theme)).classes("console-help")
                _actions(library, state, redraw, body, theme)
        # Only where it says something new: what changed matters before you take it,
        # and reading it about the copy you already run is reading old news.
        if theme.get("change_log") and (not theme["installed"]
                                        or theme["update_available"]):
            with ui.element("div").classes("console-theme-changes"):
                ui.label(theme["change_log"]).classes("console-help")


def _preview(theme: dict[str, Any]) -> None:
    """The picture, at one size so a column of cards has one left edge."""
    with ui.element("div").classes("console-theme-preview shrink-0"):
        if theme.get("preview"):
            ui.image(theme["preview"]).classes("w-full")
        else:
            ui.icon("image_not_supported", size="40px").classes("opacity-40")


def _heading(theme: dict[str, Any]) -> None:
    with ui.row().classes("items-center gap-2 w-full no-wrap flex-wrap"):
        ui.label(theme["name"]).classes("console-setting")
        # One state chip, not four. A theme is exactly one of these, and drawing the
        # others as absent would put a badge on every card saying nothing.
        if theme["active"]:
            _chip(t("console.themes.active"), "console-tier--on")
        elif theme["update_available"]:
            _chip(t("console.themes.update_2", value=(theme['version'])), "console-tier--warn")
        elif theme["installed"]:
            _chip(t("word.installed"), "console-tier--off")
        if theme.get("configurable"):
            _chip(t("console.themes.configurable"), "console-tier--off")
        if theme.get("url"):
            ui.link(t("word.source"), theme["url"], new_tab=True).classes("console-help")


def _chip(text: str, tone: str) -> None:
    ui.label(text).classes(f"console-member-chip console-tier {tone}")


def _said(theme: dict[str, Any]) -> str:
    """The facts that fit on one line: who made it, which version, what it needs."""
    parts = []
    if theme.get("author"):
        parts.append(t("console.themes.by", author=theme["author"]))
    version = theme.get("installed_version") or theme.get("version")
    if version and theme["update_available"]:
        parts.append(f"v{theme['installed_version']} → v{theme['version']}")
    elif version:
        parts.append(f"v{version}")
    screens = theme.get("screens")
    if isinstance(screens, int):
        parts.append(SCREENS.get(screens, t("console.themes.screens", count=screens)))
    return " · ".join(parts)


def _actions(library: Library, state: dict[str, Any], redraw: Callable[[], None], body: Any,
             theme: dict[str, Any]) -> None:
    key = theme["key"]

    async def again() -> None:
        await _fill(library, state, redraw, body, refresh=False)

    with ui.row().classes("items-center gap-2 no-wrap flex-wrap pt-1"):
        if not theme["installed"]:
            ui.button(t("console.themes.install"), icon="download",
                      on_click=lambda: _install(library, key, again)) \
                .props("flat dense no-caps size=sm")
        elif theme["update_available"]:
            ui.button(t("console.themes.update"), icon="system_update_alt",
                      on_click=lambda: _install(library, key, again)) \
                .props("flat dense no-caps size=sm color=primary")
        if theme["installed"] and not theme["active"]:
            ui.button(t("word.make_active"), icon="check_circle",
                      on_click=lambda: _activate(library, theme, again)) \
                .props("flat dense no-caps size=sm")
        if theme.get("configurable"):
            ui.button(t("console.themes.configure"), icon="tune",
                      on_click=lambda: _configure(library, theme)) \
                .props("flat dense no-caps size=sm")
        if theme["installed"] and not theme["active"]:
            # Not on the active one: removing it would leave the frontend with no theme
            # at all, and the way out of that is a config file.
            ui.button(t("word.remove"), icon="delete",
                      on_click=lambda: _remove(library, theme, again)) \
                .props("flat dense no-caps size=sm color=negative")


async def _install(library: Library, key: str, again: Callable[[], Any]) -> None:
    ui.notify(t("console.themes.downloading", key=(key)), type="ongoing")
    try:
        await run.io_bound(library.install_theme, key)
    except Exception as exc:  # noqa: BLE001
        ui.notify(t("console.themes.could_not_install", exc=(exc)), type="negative")
        return
    ui.notify(t("console.themes.installed", key=(key)), type="positive")
    await again()


async def _activate(library: Library, theme: dict[str, Any], again: Callable[[], Any]) -> None:
    """Asked first, and the question says when it happens.

    The Manager UI restarts VPinFE here. This does not: a setting and a restart are two
    acts, and taking the second without asking is how somebody loses what they were
    doing on another screen.
    """
    if not await confirm.ask(
            t("console.themes.make_active_theme", value=(theme['name'])),
            detail=t("console.themes.takes_effect_next_time"),
            confirm=t("word.make_active"), danger=False):
        return
    try:
        await run.io_bound(library.activate_theme, theme["key"])
    except Exception as exc:  # noqa: BLE001
        ui.notify(t("console.themes.could_not_make_active", exc=(exc)), type="negative")
        return
    ui.notify(t("console.themes.plays_frontend_next_starts", value=(theme['name'])),
            type="positive")
    await again()


async def _remove(library: Library, theme: dict[str, Any], again: Callable[[], Any]) -> None:
    if not await confirm.ask(
            t("console.themes.remove", value=(theme['name'])),
            detail=t("console.themes.files_deleted_can_installed"),
            confirm=t("word.remove")):
        return
    try:
        await run.io_bound(library.remove_theme, theme["key"])
    except Exception as exc:  # noqa: BLE001
        ui.notify(t("said.could_not_remove_it", exc=(exc)), type="negative")
        return
    ui.notify(t("console.themes.removed", value=(theme['name'])), type="positive")
    await again()


async def _configure(library: Library, theme: dict[str, Any]) -> None:
    """The theme's own options, drawn from what it declares.

    Its schema rather than ours: a theme can offer a control this install has never
    heard of, and the fallback for one is a text field rather than a refusal.
    """
    try:
        found = await offload.io(library.theme_options, theme["key"])
    except Exception as exc:  # noqa: BLE001
        ui.notify(t("console.themes.could_not_read_settings", exc=(exc)), type="negative")
        return

    options = list(found.get("options") or [])
    values = dict(found.get("values") or {})
    if not options:
        ui.notify(t("console.themes.declares_no_settings", value=(theme['name'])), type="warning")
        return

    # Held rather than read back off the controls when Save is pressed: a json option
    # is parsed as it is edited, so a mistake is reported while the dialog is still open
    # and beside the field that has it.
    wanted = {option["key"]: values.get(option["key"], option.get("default"))
              for option in options}
    with ui.dialog() as dialog, ui.card().classes("console-confirm console-theme-config"):
        ui.label(found.get("title") or f"{theme['name']} settings") \
            .classes("console-confirm-title")
        ui.label(found.get("description")
                 or t("console.themes.belong_theme_saved_own")) \
            .classes("console-help")
        with ui.column().classes("w-full gap-3 console-theme-options"):
            panel.facts(ui, _rows(options, wanted))
        with ui.row().classes("justify-end gap-2 w-full"):
            ui.button(t("word.cancel"), on_click=lambda: dialog.submit(False)) \
                .props("flat no-caps")
            ui.button(t("word.save"),
                    on_click=lambda: dialog.submit(True)).props("no-caps")

    if not await dialog:
        return
    try:
        await run.io_bound(library.save_theme_options, theme["key"], wanted)
    except Exception as exc:  # noqa: BLE001
        ui.notify(t("console.themes.could_not_save_settings", exc=(exc)), type="negative")
        return
    ui.notify(t("console.themes.saved"), type="positive")


def _rows(options: list[dict[str, Any]], wanted: dict[str, Any]) -> list[tuple]:
    """The theme's options as settings rows, through the same grammar Settings uses.

    A theme's settings are settings. A control vocabulary of their own is a second
    answer to a question already answered, and the two drift the moment one gains a
    type - so the dispatch lives in one place and this only says what a theme option
    *is*.
    """
    rows: list[tuple] = []
    for option in options:
        key = option["key"]
        rows.append((str(option.get("name") or key),
                     settings.control_for(_as_option(option), _shown(option, wanted),
                                          _saver(option, wanted))))
        said = " ".join(part for part in (str(option.get("description") or ""),
                                          _expected(option, _kind(option))) if part)
        rows.append(panel.note(said))
    return rows


def _shown(option: dict[str, Any], wanted: dict[str, Any]) -> Any:
    """What goes into the control. A json option holds an object, and a field handed one
    renders Python's idea of it - single quotes and all - which is not what the theme
    would read back."""
    value = wanted.get(option["key"])
    if _kind(option) == "json":
        return _as_text(value)
    return value


def _kind(option: dict[str, Any]) -> str:
    """The names the theme service normalizes to, not the ones they look like: it emits
    "boolean", and a renderer checking for "bool" draws a switch as a text field."""
    return str(option.get("type") or "text")


def _as_option(option: dict[str, Any]) -> dict[str, Any]:
    """A theme option in the shape the shared control dispatch reads.

    An unknown type becomes text rather than nothing: a theme declaring something this
    install has never heard of should be editable badly rather than not at all.
    """
    kind = _kind(option)
    if kind == "boolean":
        return {"type": "bool"}
    if kind == "number":
        return {"type": "number", "min": option.get("min"), "max": option.get("max"),
                "step": option.get("step")}
    if kind == "select":
        return {"type": "choice", "choices": _choices(option)}
    if kind in ("textarea", "json"):
        return {"type": "text", "lines": 4}
    return {"type": "text"}


def _saver(option: dict[str, Any], wanted: dict[str, Any]) -> Callable[[Any], Any]:
    """Into the dialog's own pending values, not to the install.

    Nothing is written until Save, so this is where a json option is parsed - the
    dialog is still open, and a mistake can be corrected where it was made.
    """
    key = option["key"]

    def save(value: Any) -> bool:
        if _kind(option) == "json":
            text = str(value or "").strip()
            if not text:
                wanted[key] = None
                return True
            try:
                wanted[key] = json.loads(text)
            except json.JSONDecodeError as exc:
                ui.notify(t("console.themes.not_json", value=(option.get('name') or key),
                        msg=(exc.msg)),
                          type="warning")
                return False
            return True
        wanted[key] = value
        return True

    return save


def _choices(option: dict[str, Any]) -> Any:
    found = option.get("options") or []
    if found and isinstance(found[0], dict):
        return {one.get("value"): str(one.get("label") or one.get("value"))
                for one in found}
    return [one for one in found]


def _as_text(value: Any) -> str:
    if isinstance(value, (dict, list)):
        return json.dumps(value, indent=2)
    return "" if value is None else str(value)


def _expected(option: dict[str, Any], kind: str) -> str:
    """What a valid answer looks like. The Manager UI says this under every option and
    it is the difference between a field and a guess.

    No full stop: each of these is a fragment naming a shape, not a sentence about it.
    """
    if kind == "boolean":
        return t("console.themes.expected_off")
    if kind == "number":
        low, high = option.get("min"), option.get("max")
        if low is not None and high is not None:
            return t("console.themes.expected_number_between", low=(low), high=(high))
        return t("console.themes.expected_number")
    if kind == "select":
        return t("console.themes.expected_one_choices", len=(len(option.get('options') or [])))
    if kind == "textarea":
        return t("console.themes.expected_text_many_lines")
    if kind == "json":
        return t("console.themes.expected_json_object_array")
    return t("console.themes.expected_text")
