"""The frontend themes this install knows, and which one plays.

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
from urllib.parse import urlparse

from nicegui import run, ui

from common.i18n import t
from console import confirm, grid, offload, panel, renderers, settings, verbs, views
from console.data import Library

logger = logging.getLogger("vpinfe.console.themes")

SCOPE = "console.themes.columns"

ACTIVE, UPDATE, INSTALLED, AVAILABLE = "active", "update", "installed", "available"

# What each state is called, and the tier of the ones worth noticing.
STATES = {
    ACTIVE: {"label": t("console.themes.active"), "tier": "on"},
    UPDATE: {"label": t("console.themes.update_available"), "tier": "warn"},
    INSTALLED: {"label": t("word.installed")},
    AVAILABLE: {"label": t("console.themes.not_installed")},
}

# What a theme says it is made for.
MADE_FOR = {"cab": t("console.themes.cabinet"), "desktop": t("console.themes.desktop"),
            "both": t("console.themes.both")}

COLUMNS: list[dict[str, Any]] = [
    grid.identifier("name", t("console.themes.theme"), 320, subtitle="said",
                    picture="preview"),
    grid.column("status", t("word.status"), 150,
                **grid.choice_filter([{"value": key, "label": one["label"]}
                                      for key, one in STATES.items()], formatted=True),
                **renderers.drawable("state", states=STATES)),
    grid.column("made_for", t("console.themes.made_for"), 150,
                **grid.choice_filter([{"value": key, "label": label}
                                      for key, label in MADE_FOR.items()])),
    grid.column("author", t("word.author"), 140),
    grid.column("registry", t("console.themes.registry"), 200,
                help=t("console.themes.registry.help")),
    grid.column("repository", t("console.themes.repository"), 280),
]
_ALL = [one["field"] for one in COLUMNS]
_SHOWN = ("name", "status", "made_for")

VIEWS: dict[str, list[str] | views.Preset] = {
    t("console.view.themes_all"): views.Preset(
        columns=_SHOWN, help=t("console.view.themes_all.help")),
    t("console.view.themes_active"): views.Preset(
        columns=_SHOWN, filters={"status": {"values": [ACTIVE]}},
        help=t("console.view.themes_active.help")),
    t("console.view.themes_installed"): views.Preset(
        columns=_SHOWN, filters={"status": {"values": [ACTIVE, UPDATE, INSTALLED]}},
        help=t("console.view.themes_installed.help")),
    t("console.view.themes_available"): views.Preset(
        columns=_SHOWN, filters={"status": {"values": [AVAILABLE]}},
        help=t("console.view.themes_available.help")),
}


def status(theme: dict[str, Any]) -> str:
    if theme.get("active"):
        return ACTIVE
    if theme.get("update_available"):
        return UPDATE
    return INSTALLED if theme.get("installed") else AVAILABLE


def version_said(theme: dict[str, Any]) -> str:
    """The version, and the one on offer where it is newer."""
    if theme.get("update_available"):
        return t("console.themes.version_to", now=theme.get("installed_version") or "",
                 then=theme.get("version") or "")
    return str(theme.get("installed_version") or theme.get("version") or "")


def repo_name(url: str) -> str:
    """`owner/repo` for a repository on GitHub or Forgejo, or a file in one; the address
    itself for anything else."""
    parsed = urlparse(url)
    parts = [part for part in parsed.path.split("/") if part]
    in_one = len(parts) > 2 and (parsed.netloc == "raw.githubusercontent.com"
                                 or parts[2] == "raw")
    return "/".join(parts[:2]) if len(parts) == 2 or in_one else url


def rows(themes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{"id": theme["key"], "name": theme.get("name") or theme["key"],
             "preview": theme.get("preview") or "", "status": status(theme),
             "made_for": theme.get("type") if theme.get("type") in MADE_FOR else "",
             "author": str(theme.get("author") or ""),
             "registry": repo_name(str(theme["registry"])) if theme.get("registry") else "",
             "repository": repo_name(str(theme["url"])) if theme.get("url") else "",
             "said": " \u00b7 ".join(part for part in (str(theme.get("author") or ""),
                                                        version_said(theme)) if part)}
            for theme in themes]


def build(library: Library, state: dict[str, Any],
          on_select: Callable[[dict | None], Any], redraw: Callable[[], None]) -> None:
    body = ui.column().classes("w-full grow min-h-0 gap-0")
    ui.timer(0.01, lambda: _fill(library, state, on_select, redraw, body, refresh=False),
             once=True)


async def _fill(library: Library, state: dict[str, Any],
                on_select: Callable[[dict | None], Any], redraw: Callable[[], None],
                body: Any, refresh: bool) -> None:
    # Deferred: `games` imports `workbench`, and `workbench` imports this module for its
    # sections.
    from .games import view_control

    try:
        found = await offload.io(library.themes, refresh)
    except Exception as exc:  # noqa: BLE001 - this page says why, never 500s
        body.clear()
        with body:
            panel.facts(ui, [panel.intro(t("console.themes.could_not_read_themes", exc=(exc)))])
        return

    built = rows(list(found.get("themes") or []))
    by_id = {row["id"]: row for row in built}
    body.clear()
    if not built:
        with body:
            panel.facts(ui, [panel.intro(t("console.themes.no_theme_sources_configured"))])
        return
    with body:
        with ui.row().classes("w-full items-center gap-2 px-3 py-2 mb-2 shrink-0 "
                              "console-panel console-grid-bar"):
            bar = panel.grid_bar()
            wire_views, _picker, showing, describe = view_control(
                library, SCOPE, VIEWS, _ALL, COLUMNS, bar=bar)
            describe()
            with bar.top, panel.bar_end():
                search = panel.search(t("console.themes.search_themes"))
            with bar.bottom, panel.bar_end():
                ui.label(t("console.themes.themes", count=len(built))) \
                    .classes("text-xs console-label")
                ui.button(icon=verbs.REFRESH,
                          on_click=lambda: _fill(library, state, on_select, redraw, body,
                                                 refresh=True)) \
                    .props("flat dense round size=sm").classes("shrink-0") \
                    .tooltip(t("console.themes.check_updates"))

        async def on_header_context(col_id: str | None) -> None:
            await grid.header_menu(menu, table, COLUMNS, col_id)

        with ui.element("div").classes("w-full grow min-h-0 flex flex-col"):
            table = grid.build(COLUMNS, built, SCOPE, on_header_context=on_header_context,
                               view_of=showing)
            menu = ui.context_menu()
        grid.on_row_focus(SCOPE, lambda event: on_select(by_id.get(grid.focused_row(event))))

        async def refresh_rows() -> None:
            fresh = rows(list((await offload.io(library.themes, False)).get("themes") or []))
            by_id.clear()
            by_id.update({row["id"]: row for row in fresh})
            table.run_grid_method("setGridOption", "rowData", fresh)

        state["refresh_themes"] = refresh_rows
        wire_views(table)
        search.on_value_change(
            lambda: table.run_grid_method("setGridOption", "quickFilterText",
                                          search.value or ""))


def _found(context: dict[str, Any]) -> dict[str, Any]:
    return context["theme"]


async def _changed(context: dict[str, Any]) -> None:
    """The grid's row and this panel, after an act changed the theme."""
    refresh = context["state"].get("refresh_themes")
    if callable(refresh):
        await refresh()
    await context["rebuild"]()


async def details(context: dict[str, Any]) -> None:
    theme = _found(context)
    library = context["library"]
    with ui.column().classes("gap-0 console-form w-full min-w-0"):
        with ui.element("div").classes("console-theme-hero"):
            if theme.get("preview"):
                ui.image(theme["preview"]).classes("w-full")
            else:
                ui.icon("image_not_supported").classes("console-theme-hero-empty")
        entries: list[tuple[Any, Any]] = []
        if theme.get("description"):
            entries.append(panel.intro(str(theme["description"])))
        state_of = STATES[status(theme)]
        entries.append((t("word.status"), panel.state(state_of["label"],
                                                      state_of.get("tier", "off"))))
        if version_said(theme):
            entries.append((t("word.version"), version_said(theme)))
        if theme.get("author"):
            entries.append((t("word.author"), str(theme["author"])))
        if theme.get("type") in MADE_FOR:
            entries.append((t("console.themes.made_for"), MADE_FOR[str(theme["type"])]))
        if theme.get("registry"):
            entries.append((t("console.themes.registry"), repo_name(str(theme["registry"]))))
        entries.append((t("console.themes.repository"),
                        panel.link_out(repo_name(str(theme["url"])), to=str(theme["url"]))
                        if theme.get("url") else t("console.themes.added_by_hand")))
        changes = changes_worth_showing(theme)
        if changes:
            entries += [(panel.HEADING, t("console.themes.new_in_version")),
                        panel.intro(changes)]
        panel.facts(ui, entries)
        with ui.element("div").classes("console-slot-actions px-3"):
            _actions(context, library, theme)


# Text a theme template ships as its changelog, which is not news about any theme.
_PLACEHOLDERS = frozenset({"what changed in this version?"})


def changes_worth_showing(theme: dict[str, Any]) -> str:
    said = str(theme.get("change_log") or "").strip()
    if not said or said.lower() in _PLACEHOLDERS:
        return ""
    return said if not theme.get("installed") or theme.get("update_available") else ""


def _actions(context: dict[str, Any], library: Library, theme: dict[str, Any]) -> None:
    key = theme["key"]

    async def again() -> None:
        await _changed(context)

    if not theme["installed"]:
        panel.action(t("console.themes.install"), lambda: _install(library, key, again),
                     icon=verbs.FETCH)()
    elif theme["update_available"]:
        panel.action(t("console.themes.update"), lambda: _install(library, key, again),
                     icon=verbs.UPDATE)()
    if theme["installed"] and not theme["active"]:
        panel.action(t("word.make_active"), lambda: _activate(library, theme, again),
                     icon=verbs.ACTIVATE)()
    if theme["installed"] and not theme["active"]:
        # Not on the active one: removing it would leave the frontend with no theme at
        # all, and the way out of that is a config file.
        panel.action(t("word.remove"), lambda: _remove(library, theme, again),
                     icon=verbs.REMOVE, danger=True)()


async def settings_section(context: dict[str, Any]) -> None:
    theme = _found(context)
    library = context["library"]
    try:
        found = await offload.io(library.theme_options, theme["key"])
    except Exception as exc:  # noqa: BLE001
        panel.facts(ui, [panel.intro(t("console.themes.could_not_read_settings", exc=(exc)))])
        return
    options = list(found.get("options") or [])
    values = dict(found.get("values") or {})
    wanted = {option["key"]: values.get(option["key"], option.get("default"))
              for option in options}

    async def keep() -> bool:
        try:
            await run.io_bound(library.save_theme_options, theme["key"], dict(wanted))
        except Exception as exc:  # noqa: BLE001
            ui.notify(t("console.themes.could_not_save_settings", exc=(exc)), type="negative")
            return False
        return True

    with ui.column().classes("gap-0 console-form w-full"):
        entries: list[tuple[Any, Any]] = []
        if found.get("description"):
            entries.append(panel.intro(str(found["description"])))
        panel.facts(ui, entries + _rows(options, wanted, keep))


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
            confirm=t("word.make_active"), icon=verbs.ACTIVATE, danger=False):
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
            confirm=t("word.remove"), icon=verbs.REMOVE):
        return
    try:
        await run.io_bound(library.remove_theme, theme["key"])
    except Exception as exc:  # noqa: BLE001
        ui.notify(t("said.could_not_remove_it", exc=(exc)), type="negative")
        return
    ui.notify(t("console.themes.removed", value=(theme['name'])), type="positive")
    await again()


def _rows(options: list[dict[str, Any]], wanted: dict[str, Any],
          keep: Callable[[], Any]) -> list[tuple]:
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
                                          _saver(option, wanted, keep))))
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


def _saver(option: dict[str, Any], wanted: dict[str, Any],
           keep: Callable[[], Any]) -> Callable[[Any], Any]:
    """Into the theme's values, and written. A json option is parsed first, and one that
    does not parse is said and not written."""
    key = option["key"]

    async def save(value: Any) -> bool:
        if _kind(option) == "json":
            text = str(value or "").strip()
            try:
                wanted[key] = json.loads(text) if text else None
            except json.JSONDecodeError as exc:
                ui.notify(t("console.themes.not_json", value=(option.get('name') or key),
                            msg=(exc.msg)), type="warning")
                return False
        else:
            wanted[key] = value
        return bool(await keep())

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
        return ""
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
