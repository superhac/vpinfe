"""Settings: the panel, with the install as its subject.

A grouped rail beside one open page, which is the shape the details pane already uses -
the index is the map of the product, and it is the thing VPin Studio gets right about
its preferences even though it throws the rest of the app away to show it.

Everything on a page is drawn through `hubui/panel.py`. A config control is the one
place that carries its explanation beneath it rather than in a tooltip: a key's name
says what it is called, not what turning it off costs.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from nicegui import run, ui

from common.games.asset_registry import ALWAYS_KEPT, ASSET_SPECS
from common.labels import humanize
from common.media_specs import media_label_map
from hubui import deeplink, panel

logger = logging.getLogger("vpinfe.hubui.settings")

# Wider than the pane's rail: these are page names rather than section names, and
# "Virtual Pinball Spreadsheet" ellipses at the pane's width.
RAIL_PX = 230

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

# group -> (key, label) - VPinFE first, because that is the thing being configured and
# everything else is either downstream of it or somebody else's software.
INDEX: tuple[tuple[str, tuple[tuple[str, str], ...]], ...] = (
    ("VPinFE", (("general", "General"), ("library", "Library"),
                ("media_kinds", "Media Kinds"), ("asset_kinds", "Asset Kinds"),
                ("media_sources", "Media Sources"),
                ("appearance", "Appearance"), ("startup", "Startup"))),
    ("Validation", (("checks_library", "Library Checks"),
                    ("checks_media", "Media Checks"),
                    ("checks_script", "Script Checks"))),
    ("Integrations", (("vps", "Virtual Pinball Spreadsheet"),
                      ("vpinplay", "VPinPlay"), ("webhooks", "Webhooks"))),
    ("Diagnostics", (("logs", "Logs"), ("jobs", "Job History"),
                     ("support", "Support Bundle"))),
)

# label -> (section, why it lives there). Shown as rail entries that navigate, not as a
# duplicate page: a setting with two homes has two answers, and one is always stale.
ELSEWHERE: tuple[tuple[str, str, str], ...] = (
    ("Displays, Input, Launchers", "devices",
     "They belong to one device, and only make sense with that device named."),
    ("Frontend Themes", "settings",
     "A theme carries its own settings; they are shown with the theme."),
    ("Extension Settings", "extensions",
     "Each extension declares its own; hubui renders what it declares."),
    ("Collection Rules", "collections",
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


async def _write(library, section: str, key: str, value: Any) -> bool:
    """One setting, written when it is set.

    No save bar: a control that changes a value writes it, which is what every other
    control in the hub does. The reason a write failed is the API's own message, never
    the status line - `raise_for_status` throws the body away.
    """
    try:
        await run.io_bound(library.put_config, {section: {key: value}})
    except Exception as exc:  # noqa: BLE001 - the reason belongs on the page
        ui.notify(f"Could not save that: {exc}", type="negative")
        return False
    return True


def _control(library, section: str, option: dict, value: Any,
             writable: bool, rerender: Callable[[], None] | None = None,
             checks: dict[tuple[str, str], dict] | None = None) -> Callable[[], None]:
    """The control a setting's type asks for.

    Driven by the schema's `type`, never by the key's name: a setting added to
    config_schema renders here without this file being touched, which is the whole
    point of the schema being served rather than restated.
    """
    key = option["key"]
    kind = option.get("type")
    off = not writable

    if kind == "bool":
        return panel.switch(
            bool(value),
            lambda e: _write(library, section, key, bool(e.value)), disabled=off)
    if kind == "choice" and option.get("choices"):
        return panel.select(
            list(option["choices"]), str(value or ""),
            lambda e: _write(library, section, key, e.value), disabled=off)
    if kind == "int":
        return panel.number(
            value,
            lambda e: _write(library, section, key,
                             "" if e.value is None else int(e.value)), disabled=off)
    if kind == "list":
        # One line, comma separated, which is how the file holds it. A chip editor would
        # be nicer and would need to know whether order matters; it does for some.
        return panel.field(
            ", ".join(str(v) for v in (value or [])),
            lambda text: _write(library, section, key,
                                [p.strip() for p in text.split(",") if p.strip()]),
            disabled=off)
    if option.get("path"):
        # A path is the one setting that can be well-formed and still wrong, and it fails
        # much later - at launch, as a file-not-found. Re-checked after a write rather
        # than guessed at here: the answer is about this machine's disk, not the text.
        found = (checks or {}).get((section, key)) or {}

        async def save_path(text: str) -> None:
            if await _write(library, section, key, text) and rerender is not None:
                rerender()

        return panel.field(
            str(value or ""), save_path, disabled=off,
            status=panel.value_state(str(found.get("state") or ""),
                                     str(found.get("reason") or "")))
    return panel.field(
        str(value or ""),
        lambda text: _write(library, section, key, text), disabled=off)


def _schema_page(library, rerender: Callable[[], None],
                 section: str, note: str = "") -> None:
    """A settings page built from what the install says it has.

    Nothing here names a setting. The section is named; everything in it - label, help,
    control, legal values - comes from the schema, so this page cannot drift from the
    config file the way a hand-written one does.
    """
    body = ui.column().classes("w-full gap-0")
    # Filled off the event loop. These calls go to our own process, so making them here
    # blocks the server from answering them and the page waits for its own timeout.
    ui.timer(0.01, lambda: _fill(library, rerender, body, section, note), once=True)


async def _fill(library, rerender: Callable[[], None], body, section: str,
                note: str) -> None:
    try:
        schema = await run.io_bound(library.config_schema)
        values = await run.io_bound(library.config_values)
    except Exception as exc:  # noqa: BLE001 - a settings page says why, never 500s
        with body:
            panel.facts(ui, [panel.intro(f"Could not read the settings: {exc}")])
        return

    # Whether each path setting finds anything. One call for the whole page rather than
    # one per field, and never fatal: a page that cannot say whether a path is good is
    # still a page, and the fields stay usable without their marks.
    checks: dict[tuple[str, str], dict] = {}
    try:
        for found in await run.io_bound(library.config_path_checks):
            checks[(found.get("section", ""), found.get("key", ""))] = found
    except Exception:  # noqa: BLE001
        logger.info("Could not check the path settings", exc_info=True)

    block = next((s for s in schema if s.get("name") == section), None)
    if block is None:
        with body:
            panel.facts(ui, [panel.intro("This install declares no settings here.")])
        return

    writable = bool(block.get("writable"))
    current = dict(values.get(section) or {})
    entries: list[tuple[Any, Any]] = []
    if note:
        entries.append(panel.intro(note))
    if not writable:
        # Disabled rather than live and silently failing, and the reason said once.
        entries.append(panel.intro("Read-only on this install."))
    for option in block["options"]:
        value = current.get(option["key"], option.get("default"))
        # The schema's label, or the key humanized as an explicit fallback where nothing
        # has named it - never the schema's label put through that same rule again.
        entries.append((option.get("label") or humanize(option["key"]),
                        _control(library, section, option, value, writable,
                                 rerender, checks)))
        if option.get("description"):
            entries.append(panel.note(option["description"]))

    if section in FOOTERS:
        entries += await FOOTERS[section](library, rerender)
    with body:
        panel.facts(ui, entries)


def _kind_page(library, rerender: Callable[[], None], note: str,
               section: str, key: str, items: Callable[[Any], dict[str, str]],
               mode: str) -> None:
    """A switch per thing, over one list in the config.

    Not a schema page. What it switches is a *list*, and the switches themselves come
    from a registry or from the hub - which `common/` may not reach for, because nothing
    in it may import a domain package. The hub may, so the rendering lives here.
    """
    body = ui.column().classes("w-full gap-0")
    ui.timer(0.01,
             lambda: _fill_kinds(library, rerender, body, note, section, key, items,
                                 mode),
             once=True)


def _listed(value) -> set[str]:
    """A stored list, however the config layer hands it over - a list from JSON, or the
    comma string the ini holds."""
    if isinstance(value, str):
        value = value.split(",")
    return {str(item).strip() for item in (value or []) if str(item).strip()}


async def _fill_kinds(library, rerender: Callable[[], None], body, note: str,
                      section: str, key: str,
                      items: Callable[[Any], dict[str, str]], mode: str) -> None:
    try:
        # The library's, not this install's: two devices reading one hub would otherwise
        # hold two answers to a question about one set of files.
        policy = await run.io_bound(library.library_policy)
        known = await run.io_bound(items, library)
    except Exception as exc:  # noqa: BLE001 - a settings page says why, never 500s
        with body:
            panel.facts(ui, [panel.intro(f"Could not read the settings: {exc}")])
        return

    stored = _listed(policy.get(key))
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
            await run.io_bound(library.put_library_policy, {key: store})
        except Exception as exc:  # noqa: BLE001 - the reason belongs on the page
            ui.notify(f"Could not save that: {exc}", type="negative")
            return
        rerender()

    entries: list[tuple[Any, Any]] = [panel.intro(note)]
    for name, label in sorted(known.items(), key=lambda pair: pair[1]):
        entries.append((label, panel.switch(
            name in on, lambda e, n=name: flip(n, bool(e.value)))))
    with body:
        panel.facts(ui, entries)


async def _vps_foot(library, rerender: Callable[[], None]) -> list[tuple[Any, Any]]:
    """When the catalog was last asked, and the way to ask now.

    A schedule is a setting and the schema renders it; "do it now" is not a setting and
    has nowhere in a schema page to live, so a page may carry a foot for the one thing
    that is an act rather than a value.

    Rows rather than a drawing, because they join the page's one list. A second grid
    sizes a label column of its own and its values start somewhere else entirely.
    """
    try:
        state = await run.io_bound(library.vps_sync_state)
    except Exception as exc:  # noqa: BLE001 - a settings page says why, never 500s
        return [panel.intro(f"Could not read the sync state: {exc}")]

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

    def checked() -> None:
        with ui.element("div").classes("hub-fact-edit"):
            ui.label(when.replace("T", " ").replace("Z", " UTC") if when else "Never") \
                .classes("hub-fact-value truncate min-w-0")
            panel.action("Check now", now, icon="sync", inline=True)()

    return [(panel.HEADING, "Catalog"), ("Last checked", checked)]


# section -> what to draw under its settings. Only where a page has an act in it.
FOOTERS: dict[str, Callable] = {"vpsdb": _vps_foot}


def _checks_library() -> None:
    from hubui.sections import CHECKS
    entries: list[tuple[Any, Any]] = [panel.intro(
        "Each check runs over every game. Turn one off here to silence it everywhere; "
        "dismiss it on a single game to silence it just there.")]
    for _, name, description, _pred in CHECKS:
        entries.append((name, panel.switch(True, lambda e: None)))
        entries.append(panel.note(description))
    panel.facts(ui, entries)


# A page is either built from the schema - naming only the section it shows - or
# hand-written where it is not settings at all. Nothing in between: a page that half
# reads the schema is a page that drifts from it.
# key -> (config section, the one thing the page cannot say row by row). A note said
# once beats the same sentence under thirty-five switches, which is what a generated
# per-option description turns into.
# No title: the lit rail row is the page's name, and INDEX above is where it is written.
SCHEMA_PAGES: dict[str, tuple[str, str]] = {
    "general": ("general", ""),
    "vps": ("vpsdb", VPS_NOTE),
}

# The two kind pages are not schema pages. What they switch is a *list* in the config,
# and the switches themselves come from the two registries - which `common/` may not
# import, because nothing in it may reach up into a domain package. The hub may, so the
# rendering lives on this side of that line.
# key -> (note, config section, config key, what to switch, how the list reads).
# `hidden` stores what is off; `enabled` stores what is on and reads empty as all - the
# shape `asset_sources` already ships with. Both leave an empty list meaning "everything",
# so a kind or a source added in a later version arrives switched on either way.
KIND_PAGES: dict[str, tuple[str, str, str, Callable[[Any], dict[str, str]], str]] = {
    "media_kinds": (KEPT_NOTE, "", "hidden_media_kinds",
                    lambda _: dict(media_label_map()), "hidden"),
    "asset_kinds": (KEPT_NOTE, "", "hidden_asset_kinds",
                    lambda _: {spec.kind: spec.label for spec in ASSET_SPECS
                               if spec.kind not in ALWAYS_KEPT}, "hidden"),
    "media_sources": (SOURCES_NOTE, "", "asset_sources",
                      lambda library: {s["id"]: s["name"]
                                       for s in library.media_sources()}, "enabled"),
}

PAGES: dict[str, Callable[[], None]] = {
    "checks_library": _checks_library,
}

# A rail entry that leaves Settings rather than opening a page here.
GO = "go:"


def _page_label(key: str) -> str:
    """This page's name, from the one place it is written."""
    return next((label for _, items in INDEX for item, label in items if item == key),
                key)


def _section_label(key: str) -> str:
    """What to call a config section on screen.

    This page's own name for it where there is one, so a device's Settings and the
    hub's agree; otherwise the key made readable. `windows.playfield` is two words
    joined by a dot, and humanize alone leaves the dot in.
    """
    named = _page_label(key)
    if named != key:
        return named
    return " ".join(humanize(part) for part in key.split("."))


def _rail_entries() -> list[tuple[Any, str, str]]:
    """The rail: every page, grouped, then where the rest of them live.

    "Managed elsewhere" navigates rather than duplicating - the entry is the link, so
    there is no page here that could go stale against the object's own.
    """
    entries: list[tuple[Any, str, str]] = []
    for group, items in INDEX:
        entries.append((panel.GROUP, group, ""))
        entries.extend((key, label, "") for key, label in items)
    entries.append((panel.GROUP, "Managed elsewhere", ""))
    entries.extend((f"{GO}{section}", label, why)
                   for label, section, why in ELSEWHERE)
    return entries


def build(state: dict, rerender: Callable[[], None],
          go: Callable[[str], None] | None = None, library=None) -> None:
    current = state.get("settings_page") or "general"

    def pick(key: str) -> None:
        if key.startswith(GO):
            section = key[len(GO):]
            if go is not None and section != "settings":
                go(section)
            return
        state.update(settings_page=key)
        deeplink.sync(state)
        rerender()

    work = panel.sections(_rail_entries(), current, pick, rail_px=RAIL_PX)
    with work, ui.column().classes("w-full min-w-0 overflow-auto gap-0 "
                                   "hub-workbench-body"):
        panel.header(_page_label(current))
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
            panel.facts(ui, [panel.intro(STUBS.get(current, "Not designed yet.")),
                             panel.intro("Not built.")])


# `install` and `themes` appear on no page below, deliberately: the first is the device's
# identity and is edited in Details, and the second is read-only over HTTP wherever it is
# served from.
# A device's pages, in the shape this page uses for the hub's own: grouped, named in a
# person's words, one page per topic rather than one per config section. Several sections
# can back one page - a machine's screens are four of them - because how the config file
# is divided is not how somebody looks for a setting.
#
# group -> ((page key, label, sections it draws), ...)
DEVICE_INDEX: tuple[tuple[str, tuple[tuple[str, str, tuple[str, ...]], ...]], ...] = (
    ("Machine", (
        ("displays", "Displays",
         ("displays", "windows.playfield", "windows.backglass", "windows.scoreview")),
        ("input", "Input", ("input",)),
        ("feedback", "Feedback Devices", ("dof", "libdmdutil")),
    )),
    ("VPinFE", (
        ("general", "General", ("general",)),
        ("frontend", "Frontend", ("frontend",)),
        ("media", "Media", ("media",)),
    )),
    ("Integrations", (
        ("vps", "Virtual Pinball Spreadsheet", ("vpsdb",)),
        ("vpinplay", "VPinPlay", ("vpinplay",)),
        ("mobile", "VPX Mobile", ("mobile",)),
    )),
    ("Diagnostics", (
        ("logs", "Logs", ("logger",)),
        ("network", "Network", ("network",)),
    )),
)


def section_rows(source, section: str, options: list[dict], values: dict,
                 writable: bool, rerender: Callable[[], None],
                 checks: dict[tuple[str, str], dict] | None = None,
                ) -> list[tuple[Any, Any]]:
    """One section's settings as fact rows, from whatever is serving them.

    `source` is anything with `put_config` - the hub's own client for this install, or
    the client that reaches another machine. Which is the whole reason a device's
    settings page and this one are one page: the schema decides the controls and the
    source decides where the write lands.
    """
    current = dict(values.get(section) or {})
    entries: list[tuple[Any, Any]] = []
    if not writable:
        entries.append(panel.intro("Read-only on this install."))
    for option in options:
        value = current.get(option["key"], option.get("default"))
        entries.append((option.get("label") or humanize(option["key"]),
                        _control(source, section, option, value, writable,
                                 rerender, checks)))
        if option.get("description"):
            entries.append(panel.note(option["description"]))
    return entries


def build_device_page(source, context: dict[str, Any], schema: list[dict],
                      values: dict, sections: tuple[str, ...]) -> None:
    """One page of a device's settings, drawn exactly as this install's are.

    Several config sections can make one page - a machine's screens are four of them -
    with a heading each where there is more than one. How the config file is divided is
    not how somebody looks for a setting, which is why the pages are declared rather
    than taken from the schema's own shape.

    Path checks are not fetched. The machine holding a path answers for it, and asking
    this one about another machine's disk would put a red cross on a file that is
    perfectly fine over there.
    """
    def rerender() -> None:
        rebuild = context.get("rebuild")
        if rebuild is not None:
            ui.timer(0.01, rebuild, once=True)

    blocks = [block for block in schema
              if str(block.get("name")) in sections and block.get("options")]
    if not blocks:
        panel.facts(ui, [panel.intro("This device declares nothing on this page.")])
        return

    entries: list[tuple[Any, Any]] = []
    for block in blocks:
        name = str(block.get("name"))
        # A heading only where the page draws more than one section: over a page that
        # is one section it would name the page a second time.
        if len(blocks) > 1:
            entries.append((panel.HEADING, _section_label(name)))
        entries += section_rows(source, name, block["options"], values,
                                bool(block.get("writable")), rerender)
    panel.facts(ui, entries)
