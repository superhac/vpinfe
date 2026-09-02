"""Settings: a grouped index beside a content pane, inside the shell.

The index is the point. A flat list of pages hides the shape of the product; a grouped
one is a map of it, and it is the thing VPin Studio gets right about its preferences
even though it throws the rest of the app away to show it. This keeps the shell.

Every control carries its explanation beneath it, not in a tooltip and not in a link.
That single habit is what makes a dense settings page readable.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from nicegui import run, ui

from common.games.asset_registry import ALWAYS_KEPT, ASSET_SPECS
from common.media_specs import media_label_map
from hubui import deeplink

# group -> (key, label) - VPinFE first, because that is the thing being configured and
# everything else is either downstream of it or somebody else's software.
# An object's settings live with the object. What is left here is what belongs to the
# install as a whole and has no other owner - which is the only rule that keeps this
# section from becoming the bucket everything lands in. See ELSEWHERE.
# What switching one off does, and the two things it deliberately does not do. Said
# where it applies to every switch on the page rather than repeated under each.
KEPT_NOTE = ("What this library collects. Turning one off stops the hub showing and "
             "counting it; the files stay where they are, and a table that will not "
             "launch still says so.")

# Every source that ships is listed, switched off included: "why is that catalog not
# coming up" is answered by seeing it sitting there off.
SOURCES_NOTE = ("Which online catalogs are searched for artwork. All of them, until "
                "you turn one off.")

# Everything VPS-shaped reads the local copy - matching, release lists, what a kind is
# offered from - so this page is how fresh all of those answers are.
VPS_NOTE = ("Matching, release lists and what the catalog offers are read from a copy "
            "kept on this machine. Checking is cheap; the copy is only downloaded when "
            "it has actually changed.")


INDEX: tuple[tuple[str, tuple[tuple[str, str], ...]], ...] = (
    ("VPinFE", (("general", "General"), ("library", "Library"),
                ("media_kinds", "Media kinds"), ("asset_kinds", "Asset kinds"),
                ("media_sources", "Media sources"),
                ("appearance", "Appearance"), ("startup", "Startup"))),
    ("Validation", (("checks_library", "Library checks"),
                    ("checks_media", "Media checks"),
                    ("checks_script", "Script checks"))),
    ("Integrations", (("vps", "Virtual Pinball Spreadsheet"),
                      ("vpinplay", "VPinPlay"), ("webhooks", "Webhooks"))),
    ("Diagnostics", (("logs", "Logs"), ("jobs", "Job history"),
                     ("support", "Support bundle"))),
)

# label -> (section, why it lives there). Shown as links, not as a duplicate page: a
# setting with two homes has two answers, and one of them is always stale.
ELSEWHERE: tuple[tuple[str, str, str], ...] = (
    ("Displays, input, launchers", "devices",
     "They belong to one device, and only make sense with that device named."),
    ("Frontend themes", "settings",
     "A theme carries its own settings; they are shown with the theme."),
    ("Extension settings", "extensions",
     "Each extension declares its own; hubui renders what it declares."),
    ("Collection rules", "collections",
     "The rule is the collection."),
)

# What each page will hold. Written out because an index whose destinations are unknown
# is not a design, and because reading this list is the cheapest way to notice that a
# page is in the wrong group.
STUBS = {
    "library": "Where tables live, how often the library is rescanned, and what a scan "
               "is allowed to write back.",
    "appearance": "Palette, density, and which columns a fresh install starts with.",
    "startup": "What launches with the hub, and what it does when a device is already "
               "running.",
    "checks_media": "Checks about media presence, resolution and fallbacks.",
    "checks_script": "Checks that read the table script.",
    "vpinplay": "The account a score is submitted under.",
    "webhooks": "Endpoints told when something changes here.",
    "logs": "This install's log, filtered.",
    "jobs": "What ran, when, and what it did.",
    "support": "A bundle to attach to a bug report, with what it contains listed before "
               "it is written.",
}


def _setting(label: str, help_text: str, control: Callable[[], None]) -> None:
    """One control, its label, and the sentence that says what it does.

    The order matters: label, control, explanation. Explanation last so the eye can skip
    it once the setting is understood, and never as a tooltip - a tooltip is help you
    have to already suspect you need.
    """
    with ui.column().classes("gap-1 w-full py-2"):
        ui.label(label).classes("hub-setting")
        control()
        ui.label(help_text).classes("hub-help")


def _control(option: dict, value, on_change: Callable[[object], None]) -> None:
    """The control a setting's type asks for.

    Driven by the schema's `type`, never by the key's name: a setting added to
    config_schema renders here without this file being touched, which is the whole
    point of the schema being served rather than restated.
    """
    kind = option.get("type")
    if kind == "bool":
        ui.switch(value=bool(value), on_change=lambda e: on_change(bool(e.value))) \
            .props("dense color=positive")
        return
    if kind == "choice" and option.get("choices"):
        ui.select(list(option["choices"]), value=str(value or ""),
                  on_change=lambda e: on_change(e.value)) \
            .props("dense outlined options-dense").classes("w-80")
        return
    if kind == "int":
        ui.number(value=value if value != "" else None, format="%d",
                  on_change=lambda e: on_change(
                      "" if e.value is None else int(e.value))) \
            .props("dense outlined").classes("w-40")
        return
    if kind == "list":
        # One line, comma separated, which is how the file holds it. A chip editor would
        # be nicer and would need to know whether order matters; it does for some.
        ui.input(value=", ".join(str(v) for v in (value or [])),
                 on_change=lambda e: on_change(
                     [p.strip() for p in str(e.value or "").split(",") if p.strip()])) \
            .props("dense outlined").classes("w-full")
        return
    ui.input(value=str(value or ""), on_change=lambda e: on_change(e.value)) \
        .props("dense outlined").classes("w-full")


def _schema_page(library, rerender: Callable[[], None], title: str,
                 section: str, note: str = "") -> None:
    """A settings page built from what the install says it has.

    Nothing here names a setting. The section is named; everything in it - label, help,
    control, legal values - comes from the schema, so this page cannot drift from the
    config file the way a hand-written one does.
    """
    ui.label(title).classes("hub-card-title")
    if note:
        ui.label(note).classes("hub-help mt-1")
    body = ui.column().classes("w-full gap-0")
    # Filled off the event loop. These calls go to our own process, so making them here
    # blocks the server from answering them and the page waits for its own timeout.
    ui.timer(0.01, lambda: _fill(library, rerender, body, title, section), once=True)
    if section in FOOTERS:
        foot = ui.column().classes("w-full gap-0")
        ui.timer(0.01, lambda: FOOTERS[section](library, rerender, foot), once=True)


async def _fill(library, rerender: Callable[[], None], body, title: str,
                section: str) -> None:
    try:
        schema = await run.io_bound(library.config_schema)
        values = await run.io_bound(library.config_values)
    except Exception as exc:  # noqa: BLE001 - a settings page says why, never 500s
        with body:
            ui.label(f"Could not read the settings: {exc}").classes("hub-help mt-2")
        return

    block = next((s for s in schema if s.get("name") == section), None)
    if block is None:
        with body:
            ui.label(f"This install declares no [{section}] settings.") \
                .classes("hub-help")
        return

    dirty: dict[str, object] = {}
    current = dict(values.get(section) or {})
    bar: dict[str, object] = {}

    def refresh_bar() -> None:
        holder = bar.get("holder")
        if holder is None:
            return
        holder.clear()
        if not dirty:
            return
        with holder:
            with ui.row().classes("items-center gap-3 w-full hub-savebar"):
                ui.label(f"{len(dirty)} unsaved change"
                         + ("s" if len(dirty) != 1 else "")).classes("hub-setting")
                ui.space()
                ui.button("Discard", on_click=discard) \
                    .props("flat dense no-caps").classes("hub-action")
                ui.button("Save", icon="save", on_click=save) \
                    .props("flat dense no-caps").classes("hub-action")

    def mark(key: str, original, value) -> None:
        if value == original:
            dirty.pop(key, None)
        else:
            dirty[key] = value
        refresh_bar()

    async def save() -> None:
        changes = dict(dirty)
        try:
            await run.io_bound(library.put_config, {section: changes})
        except Exception as exc:  # noqa: BLE001 - the reason belongs on the page
            ui.notify(f"Could not save: {exc}", type="negative")
            return
        current.update(changes)
        dirty.clear()
        refresh_bar()
        ui.notify(f"Saved {len(changes)} setting"
                  + ("s" if len(changes) != 1 else ""), type="positive")

    def discard() -> None:
        dirty.clear()
        rerender()

    with body:
        found = len(block["options"])
        ui.label(f"Read from this install. {found} setting"
                 f"{'' if found == 1 else 's'} in [{section}]."
                 ).classes("hub-help mt-1")
        if not block.get("writable"):
            ui.label("Read-only over HTTP.").classes("hub-help mt-1")
        bar["holder"] = ui.element("div").classes("w-full")
        with ui.element("div").classes("hub-card w-full mt-2"):
            for option in block["options"]:
                key = option["key"]
                original = current.get(key, option.get("default"))
                _setting(option.get("label") or key,
                         option.get("description") or "",
                         lambda o=option, k=key, v=original:
                             _control(o, v, lambda new, k=k, v=v: mark(k, v, new)))
    refresh_bar()


def _kind_page(library, rerender: Callable[[], None], title: str, note: str,
               section: str, key: str, items: Callable[[Any], dict[str, str]],
               mode: str) -> None:
    """A switch per thing, over one list in the config.

    Not a schema page. What it switches is a *list*, and the switches themselves come
    from a registry or from the hub - which `common/` may not reach for, because nothing
    in it may import a domain package. The hub may, so the rendering lives here.
    """
    ui.label(title).classes("hub-card-title")
    ui.label(note).classes("hub-help mt-1")
    body = ui.column().classes("w-full gap-0")
    ui.timer(0.01,
             lambda: _fill_kinds(library, rerender, body, section, key, items, mode),
             once=True)


def _listed(value) -> set[str]:
    """A stored list, however the config layer hands it over - a list from JSON, or the
    comma string the ini holds."""
    if isinstance(value, str):
        value = value.split(",")
    return {str(item).strip() for item in (value or []) if str(item).strip()}


async def _fill_kinds(library, rerender: Callable[[], None], body, section: str,
                      key: str, items: Callable[[Any], dict[str, str]],
                      mode: str) -> None:
    try:
        values = await run.io_bound(library.config_values)
        known = await run.io_bound(items, library)
    except Exception as exc:  # noqa: BLE001 - a settings page says why, never 500s
        with body:
            ui.label(f"Could not read the settings: {exc}").classes("hub-help mt-2")
        return

    stored = _listed((values.get(section) or {}).get(key))
    # An `enabled` list reads empty as everything, so what is on is the whole set until
    # somebody turns one off.
    on = (set(known) - stored) if mode == "hidden" else (stored or set(known))

    async def flip(name: str, wanted_on: bool) -> None:
        after = (on | {name}) if wanted_on else (on - {name})
        if mode == "hidden":
            store = sorted(set(known) - after)
        else:
            # Everything on stores nothing, which is what keeps a source added later
            # switched on rather than quietly excluded.
            store = [] if after >= set(known) else sorted(after)
        try:
            await run.io_bound(library.put_config, {section: {key: store}})
        except Exception as exc:  # noqa: BLE001
            ui.notify(f"Could not save that: {exc}", type="negative")
            return
        rerender()

    with body, ui.element("div").classes("hub-card w-full mt-2"):
        for name, label in sorted(known.items(), key=lambda pair: pair[1]):
            with ui.row().classes("items-center gap-3 w-full no-wrap hub-setting-row"):
                ui.switch(value=name in on,
                          on_change=lambda e, n=name: flip(n, bool(e.value))) \
                    .props("dense color=positive")
                ui.label(label).classes("hub-setting")


async def _vps_foot(library, rerender: Callable[[], None], body) -> None:
    """When the catalog was last asked, and the way to ask now.

    A schedule is a setting and the schema renders it; "do it now" is not a setting and
    has nowhere in a schema page to live, so a page may carry a foot for the one thing
    that is an act rather than a value.
    """
    try:
        state = await run.io_bound(library.vps_sync_state)
    except Exception as exc:  # noqa: BLE001 - a settings page says why, never 500s
        with body:
            ui.label(f"Could not read the sync state: {exc}").classes("hub-help mt-2")
        return

    async def now() -> None:
        # Held: an ongoing notification never times out on its own.
        checking = ui.notification("Checking VPSdb...", spinner=True, timeout=None)
        try:
            done = await run.io_bound(library.sync_vps)
        except Exception as exc:  # noqa: BLE001
            ui.notify(f"Could not check: {exc}", type="negative")
            return
        finally:
            checking.dismiss()
        # "Already current" is the ordinary outcome and says itself; a positive toast
        # for it would make the rare one look the same as the common one.
        ui.notify("Catalog updated" if done.get("changed") else "Already up to date",
                  type="positive" if done.get("changed") else "info")
        rerender()

    when = str(state.get("checked") or "")
    with body, ui.element("div").classes("hub-card w-full mt-2"):
        with ui.row().classes("items-center gap-3 w-full no-wrap"):
            ui.label("Last checked").classes("hub-setting")
            ui.label(when.replace("T", " ").replace("Z", " UTC") if when
                     else "Never").classes("hub-help")
            ui.space()
            ui.button("Check now", icon="sync", on_click=now) \
                .props("flat dense no-caps size=sm").classes("hub-action")


# section -> what to draw under its settings. Only where a page has an act in it.
FOOTERS: dict[str, Callable] = {"vpsdb": _vps_foot}


def _checks_library() -> None:
    ui.label("Library checks").classes("hub-card-title")
    ui.label("Each check runs over every game. Turn one off here to silence it "
             "everywhere; dismiss it on a single game to silence it just there.") \
        .classes("hub-help mt-1")
    from hubui.sections import CHECKS
    with ui.element("div").classes("hub-card w-full mt-2"):
        for _, name, description, _pred in CHECKS:
            with ui.row().classes("items-start gap-3 w-full no-wrap py-1"):
                ui.checkbox(value=True).props("dense").classes("shrink-0")
                with ui.column().classes("gap-0 grow min-w-0"):
                    ui.label(name).classes("hub-setting")
                    ui.label(description).classes("hub-help")


# A page is either built from the schema - naming only the section it shows - or
# hand-written where it is not settings at all. Nothing in between: a page that half
# reads the schema is a page that drifts from it.
# key -> (title, section, the one thing the page cannot say row by row). A note said
# once beats the same sentence under thirty-five switches, which is what a generated
# per-option description turns into.
SCHEMA_PAGES: dict[str, tuple[str, str, str]] = {
    "general": ("General", "general", ""),
    "vps": ("Virtual Pinball Spreadsheet", "vpsdb", VPS_NOTE),
}

# The two kind pages are not schema pages. What they switch is a *list* in the config,
# and the switches themselves come from the two registries - which `common/` may not
# import, because nothing in it may reach up into a domain package. The hub may, so the
# rendering lives on this side of that line.
# key -> (title, note, config section, config key, what to switch, how the list reads).
# `hidden` stores what is off; `enabled` stores what is on and reads empty as all - the
# shape `asset_sources` already ships with. Both leave an empty list meaning "everything",
# so a kind or a source added in a later version arrives switched on either way.
KIND_PAGES: dict[str, tuple[str, str, str, str, Callable[[Any], dict[str, str]], str]] = {
    "media_kinds": ("Media kinds", KEPT_NOTE, "general", "hidden_media_kinds",
                    lambda _: dict(media_label_map()), "hidden"),
    "asset_kinds": ("Asset kinds", KEPT_NOTE, "general", "hidden_asset_kinds",
                    lambda _: {spec.kind: spec.label for spec in ASSET_SPECS
                               if spec.kind not in ALWAYS_KEPT}, "hidden"),
    "media_sources": ("Media sources", SOURCES_NOTE, "media", "asset_sources",
                      lambda library: {s["id"]: s["name"]
                                       for s in library.media_sources()}, "enabled"),
}

PAGES: dict[str, Callable[[], None]] = {
    "checks_library": _checks_library,
}


def build(state: dict, rerender: Callable[[], None],
          go: Callable[[str], None] | None = None, library=None) -> None:
    current = state.get("settings_page") or "general"
    with ui.row().classes("w-full h-full gap-4 no-wrap items-stretch"):
        index = ui.column().classes("gap-0 shrink-0 overflow-auto") \
            .style("width:230px")
        with index:
            for group, items in INDEX:
                ui.label(group).classes("hub-group")
                for key, label in items:
                    row = ui.label(label).classes("hub-index-item")
                    if key == current:
                        row.classes(add="hub-index-on")
                    row.on("click", lambda k=key: (state.update(settings_page=k),
                                                   deeplink.sync(state),
                                                   rerender()))
            ui.label("Managed elsewhere").classes("hub-group")
            for label, section, why in ELSEWHERE:
                item = ui.label(label).classes("hub-index-item")
                item.tooltip(why)
                if go is not None and section != "settings":
                    item.on("click", lambda sec=section: go(sec))
        with ui.column().classes("grow min-w-0 overflow-auto"):
            schema_page = SCHEMA_PAGES.get(current)
            kind_page = KIND_PAGES.get(current)
            page = PAGES.get(current)
            if kind_page is not None and library is not None:
                _kind_page(library, rerender, *kind_page)
            elif schema_page is not None and library is not None:
                _schema_page(library, rerender, *schema_page)
            elif page is not None:
                page()
            else:
                label = next((lbl for _, items in INDEX for key, lbl in items
                              if key == current), current)
                ui.label(label).classes("hub-card-title")
                with ui.element("div").classes("hub-card w-full mt-2"):
                    ui.label(STUBS.get(current, "Not designed yet.")) \
                        .classes("hub-help")
                    ui.label("Not built.").classes("text-xs opacity-50 mt-2")
