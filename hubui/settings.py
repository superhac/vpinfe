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
from hubui import panel

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



def _page_label(key: str) -> str:
    """A page's name, from the one place it is written."""
    return next((label for _group, pages in DEVICE_INDEX
                 for item, label, _kind, _sections, _role in pages if item == key), key)


def _section_label(key: str) -> str:
    """What to call a config section on screen.

    A page's own name where a page is that one section, otherwise the key made readable.
    `windows.playfield` is two words joined by a dot, and humanize alone leaves the dot.
    """
    named = next((label for _group, pages in DEVICE_INDEX
                  for _item, label, _kind, sections, _role in pages
                  if sections == (key,)), "")
    return named or " ".join(humanize(part) for part in key.split("."))


# `install` and `themes` appear on no page below, deliberately: the first is the device's
# identity and is edited in Details, and the second is read-only over HTTP wherever it is
# served from.
# A device's pages, in the shape this page uses for the hub's own: grouped, named in a
# person's words, one page per topic rather than one per config section. Several sections
# can back one page - a machine's screens are four of them - because how the config file
# is divided is not how somebody looks for a setting.
#
# group -> ((page key, label, kind, sections it draws, role), ...)
# `role` filters; empty means any install. `kind` picks the renderer.
SCHEMA_PAGE, KIND_PAGE, BUILT_PAGE = "schema", "kind", "built"

DevicePage = tuple[str, str, str, tuple[str, ...], str]

DEVICE_INDEX: tuple[tuple[str, tuple[DevicePage, ...]], ...] = (
    ("Library", (
        ("media_kinds", "Media Kinds", KIND_PAGE, (), "hub"),
        ("asset_kinds", "Asset Kinds", KIND_PAGE, (), "hub"),
        ("media_sources", "Media Sources", KIND_PAGE, (), "hub"),
        ("checks_library", "Library Checks", BUILT_PAGE, (), "hub"),
    )),
    ("Hardware", (
        ("displays", "Displays", SCHEMA_PAGE,
         ("displays", "windows.playfield", "windows.backglass", "windows.scoreview"),
         "device"),
        ("input", "Input", SCHEMA_PAGE, ("input",), "device"),
        ("feedback", "Peripherals", SCHEMA_PAGE, ("dof", "libdmdutil"), "device"),
    )),
    ("VPinFE", (
        ("general", "General", SCHEMA_PAGE, ("general",), ""),
        ("frontend", "Frontend", SCHEMA_PAGE, ("frontend",), "device"),
        ("media", "Media", SCHEMA_PAGE, ("media",), "hub"),
    )),
    ("Integrations", (
        ("vps", "Virtual Pinball Spreadsheet", SCHEMA_PAGE, ("vpsdb",), "hub"),
        ("vpinplay", "VPinPlay", SCHEMA_PAGE, ("vpinplay",), ""),
        ("mobile", "VPX Mobile", SCHEMA_PAGE, ("mobile",), "hub"),
    )),
    ("Diagnostics", (
        ("logs", "Logs", SCHEMA_PAGE, ("logger",), ""),
        ("network", "Network", SCHEMA_PAGE, ("network",), ""),
    )),
)


def pages_for_roles(roles) -> list[tuple[str, DevicePage]]:
    """(group, page) for every page the roles a device serves can answer for."""
    held = {str(role).strip().lower() for role in (roles or [])} or {"hub", "device"}
    return [(group, page) for group, pages in DEVICE_INDEX for page in pages
            if not page[4] or page[4] in held]


def build_library_page(library, rerender: Callable[[], None], key: str,
                       kind: str) -> None:
    """A library page, drawn where a device's rail asks for it.

    These are the hub's own: what the library collects, and what it is checked for. They
    reach for registries and for the hub's client rather than for a config schema, which
    is why they are not schema pages and are only offered on an install that holds a
    library.
    """
    if kind == BUILT_PAGE:
        drawn = PAGES.get(key)
        if drawn is None:
            panel.facts(ui, [panel.intro(STUBS.get(key, "Not built yet."))])
            return
        drawn()
        return

    found = KIND_PAGES.get(key)
    if found is None:
        panel.facts(ui, [panel.intro(STUBS.get(key, "Not built yet."))])
        return
    note, _section, name, items, mode = found
    _kind_page(library, rerender, note, "", name, items, mode)


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


async def build_device_page(source, context: dict[str, Any], schema: list[dict],
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
        # A page may carry a foot for the one thing on it that is an act rather than a
        # value. Only where the hub's own client is what serves the page: these reach
        # for the library, which another machine's client cannot answer for.
        foot = FOOTERS.get(name)
        if foot is not None and source is context.get("library"):
            entries += await foot(source, rerender)
    panel.facts(ui, entries)
