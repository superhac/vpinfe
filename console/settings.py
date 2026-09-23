"""Settings: the panel, with the install as its subject.

A grouped rail beside one open page, which is the shape the details pane already uses -
the index is the map of the product, and it is the thing VPin Studio gets right about
its preferences even though it throws the rest of the app away to show it.

Everything on a page is drawn through `console/panel.py`. A config control is the one
place that carries its explanation beneath it rather than in a tooltip: a key's name
says what it is called, not what turning it off costs.

One settings grammar, wherever a page is reached from. `build_system` draws this
install's own and the device panel draws another machine's, from one declaration and
through one renderer - what differs is only which install answers.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from nicegui import run, ui

from common import config_schema, feature_checks, install_identity, path_checks, tokens
from common.games.asset_registry import ALWAYS_KEPT, ASSET_SPECS
from common.i18n import t
from common.labels import humanize
from common.media_specs import media_label_map
from console import binding_editor, deeplink, input_watch, offload, panel, theme_picker, verbs, when
from console import commands as commands_help
from console.data import Library

logger = logging.getLogger("vpinfe.console.settings")

# Wider than the pane's rail: these are page names rather than section names, and
# "Virtual Pinball Spreadsheet" ellipses at the pane's width.
RAIL_PX = 230

# What switching one off does, and the two things it deliberately does not do. Said
# where it applies to every switch on the page rather than repeated under each.
KEPT_NOTE = ("What this library collects. Turning one off stops this install showing and "
             "counting it; the files stay where they are, and a table that will not "
             "launch still says so.")

# Every source that ships is listed, switched off included: "why is that catalog not
# coming up" is answered by seeing it sitting there off.
SOURCES_NOTE = (t("console.settings.online_catalogs_searched_artwork"))

# The library's answer, not this install's, so two machines reading one library report
# the same gaps. Turning one off stops it being counted, never fixes what it found.
CHECKS_NOTE = t("console.settings.checks_note")


async def _write(library: Library, section: str, key: str, value: Any) -> bool:
    """One setting, written when it is set.

    No save bar: a control that changes a value writes it, which is what every other
    control in the Console does. The reason a write failed is the API's own message, never
    the status line - `raise_for_status` throws the body away.
    """
    try:
        await run.io_bound(library.put_config, {section: {key: value}})
    except Exception as exc:  # noqa: BLE001 - the reason belongs on the page
        ui.notify(t("console.settings.could_not_save", exc=(exc)), type="negative")
        return False
    return True


# Tools a setting can ask for by name, where a control cannot do the job. Routed the way
# `type` is, so declaring one is a line in the schema rather than a branch here. A name
# nothing serves falls back to the control for its type: a surface that has not been
# taught the tool should still be able to edit the value badly rather than not at all.
def _frontend_theme(option: dict, value: Any, save: Callable[[Any], Any],
                    **_: Any) -> Callable[[], None]:
    """The active theme, and the way to where it is chosen."""
    def draw() -> None:
        with ui.element("div").classes("console-fact-edit"):
            ui.label(str(value or "")).classes("console-fact-value truncate min-w-0")
            panel.link(t("console.settings.change_on_themes"),
                       to="/console?view=themes")()

    return draw


EDITORS: dict[str, Callable[..., Callable[[], None]]] = {
    config_schema.EDITOR_BINDING: binding_editor.rows,
    config_schema.EDITOR_CONSOLE_THEME: theme_picker.tiles,
    config_schema.EDITOR_FRONTEND_THEME: _frontend_theme,
}


def value_for(option: dict, raw: Any) -> Any:
    """A stored value as its declared type, or the default where it will not fit.

    Values read out of a program's own file are strings, and not every one of them
    matches what that program says the setting is: an integer written once as `0.0`
    stays that way, and a closed set of answers has no option spelled "". A settings
    page that raises on either is a page that will not draw at all, so the declared
    type wins and a value that cannot meet it falls back to the default.
    """
    said = str(raw if raw is not None else "").strip()
    kind = str(option.get("type") or "")
    if not said:
        said = str(option.get("default") or "").strip()
    if not said:
        return False if kind == "bool" else ""

    if kind == "bool":
        return said.strip().lower() not in ("0", "false", "no", "off", "")
    if kind in ("int", "number"):
        try:
            number = float(said)
        except ValueError:
            return _fallback_number(option, kind)
        return int(number) if kind == "int" else number
    if kind == "choice":
        offered = option.get("choices") or {}
        keys = offered.keys() if isinstance(offered, dict) else offered
        if said not in keys:
            return str(option.get("default") or "") if str(
                option.get("default") or "") in keys else next(iter(keys), "")
    return said


def _fallback_number(option: dict, kind: str) -> Any:
    try:
        number = float(str(option.get("default") or "").strip() or 0)
    except ValueError:
        number = 0
    return int(number) if kind == "int" else number


def control_for(option: dict, value: Any, save: Callable[[Any], Any], *,
                writable: bool = True, rerender: Callable[[], None] | None = None,
                check: dict | None = None,
                suggestions: dict[str, Any] | None = None,
                section_values: dict[str, Any] | None = None) -> Callable[[], None]:
    """The control a declared value's type asks for.

    Driven by the declaration, never by the key's name: something added to the schema -
    or to an app's launcher fields - renders here without this file being touched.

    `save` takes the new value and answers whether it was written. Passed in rather than
    built from a section and a key, because the same grammar now draws two things that
    are stored quite differently: a setting goes to a config section, and a launcher
    field goes to a launcher.
    """
    editor = EDITORS.get(str(option.get("editor") or ""))
    if editor is not None:
        return editor(option, value, save, section=section_values or {},
                      writable=writable, rerender=rerender)

    kind = option.get("type")
    off = not writable
    found = check or {}
    state = panel.value_state(str(found.get("state") or ""),
                              str(found.get("reason") or ""))

    if option.get("suggest"):
        # Offered and not imposed: what produced the list can be wrong - a network that
        # filters multicast has nothing on it - so anything may still be typed.
        offered = (suggestions or {}).get(option["suggest"]) or {}

        # Only where this setting is carrying a mark. The redraw exists to refresh one -
        # `network.library_url` is what a feature check points at, and answering it has
        # to clear the badge that led here. Every other suggested setting changes nothing
        # the page is showing about anything else, and rebuilding for those costs four
        # round trips and puts a long page back at the top under the pointer.
        marks = bool(found)

        async def save_suggested(event: Any) -> None:
            if await save(str(event.value or "").strip()) and marks and rerender is not None:
                rerender()

        return panel.combo(str(value or ""), offered, save_suggested, disabled=off,
                           status=state)

    if kind == "bool":
        # Through the declared type, not `bool()`. A setting nobody has stored answers
        # with its declared default, and that is the string "false" - which is a
        # perfectly true string, and drew every untouched switch as on.
        return panel.switch(bool(value_for(option, value)),
                            lambda e: save(bool(e.value)), disabled=off)
    if kind == "choice" and option.get("choices"):
        # Passed through when it is already a mapping. A theme names its choices
        # `{value: label}`, and flattening that to a list would put the stored value on
        # screen where the label belongs.
        choices = option["choices"]
        named = option.get("choice_labels") or {}
        if named and not isinstance(choices, dict):
            choices = {value: named.get(value, value) for value in choices}
        return panel.select(choices if isinstance(choices, dict) else list(choices),
                            str(value or ""), lambda e: save(e.value), disabled=off)
    if kind == "int":
        return panel.number(
            value, lambda e: save("" if e.value is None else int(e.value)), disabled=off)
    if kind == "number":
        # Not `int`: a theme declares scale factors and opacities, and a control that
        # formats them as whole numbers shows a value that is not the one stored.
        return panel.number(
            value, lambda e: save(None if e.value is None else float(e.value)),
            disabled=off, whole=False, low=option.get("min"), high=option.get("max"),
            step=option.get("step"))
    if kind == "text" and option.get("lines"):
        return panel.field(str(value or ""), lambda text: save(text),
                           lines=int(option["lines"]), disabled=off)
    if kind == "list":
        # One line, comma separated, which is how the file holds it. A chip editor would
        # be nicer and would need to know whether order matters; it does for some.
        return panel.field(
            ", ".join(str(v) for v in (value or [])),
            lambda text: save([p.strip() for p in text.split(",") if p.strip()]),
            disabled=off)
    if option.get("path"):
        # A path is the one value that can be well-formed and still wrong, and it fails
        # much later - at launch, as a file-not-found. Re-checked after a write rather
        # than guessed at here: the answer is about this machine's disk, not the text.
        async def save_path(text: str) -> None:
            if await save(text) and rerender is not None:
                rerender()

        return panel.field(str(value or ""), save_path, disabled=off, status=state)
    return panel.field(str(value or ""), lambda text: save(text), disabled=off)


def _by_group(options: list[dict]) -> list[dict]:
    """The section's settings gathered under their headings, the ungrouped last.

    Gathered rather than assumed contiguous: two settings of one group can be declared
    either side of another, and a renderer emitting a heading on every change prints one
    twice. Declaration order decides everything else, so a page is ordered by moving a
    line in the schema.
    """
    ordered: dict[str, list[dict]] = {}
    for option in options:
        ordered.setdefault(str(option.get("group") or ""), []).append(option)
    loose = ordered.pop("", [])
    return [option for group in ordered.values() for option in group] + loose


def _saver(source: Any, section: str, key: str) -> Callable[[Any], Any]:
    """Write one setting to a config section, for the control grammar to call."""
    async def save(value: Any) -> bool:
        return await _write(source, section, key, value)

    return save


def _kind_page(library: Library, rerender: Callable[[], None], note: str,
               section: str, key: str, items: Callable[[Any], dict[str, str]],
               mode: str) -> None:
    """A switch per thing, over one list in the config.

    Not a schema page. What it switches is a *list*, and the switches themselves come
    from a registry or from the API - which `common/` may not reach for, because nothing
    in it may import a domain package. The Console may, so the rendering lives here.
    """
    body = ui.column().classes("w-full gap-0")
    ui.timer(0.01,
             lambda: _fill_kinds(library, rerender, body, note, section, key, items,
                                 mode),
             once=True)


def _listed(value: Any) -> set[str]:
    """A stored list, however the config layer hands it over - a list from JSON, or the
    comma string the ini holds."""
    if isinstance(value, str):
        value = value.split(",")
    return {str(item).strip() for item in (value or []) if str(item).strip()}


async def _fill_kinds(library: Library, rerender: Callable[[], None], body: Any, note: str,
                      section: str, key: str,
                      items: Callable[[Any], dict[str, str]], mode: str) -> list:
    """The switches, drawn into `body` - or returned when `body` is None, for a page that
    orders them among its own settings rather than beside them."""
    try:
        # The library's, not this install's: two devices reading one library would otherwise
        # hold two answers to a question about one set of files.
        policy = await offload.io(library.library_policy)
        known = await offload.io(items, library)
    except Exception as exc:  # noqa: BLE001 - a settings page says why, never 500s
        said = [panel.intro(t("said.could_not_read_the_settings", exc=(exc)))]
        if body is None:
            return said
        with body:
            panel.facts(ui, said)
        return said

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
            ui.notify(t("console.settings.could_not_save", exc=(exc)), type="negative")
            return
        rerender()

    # Bound by a call rather than captured off the loop variable, which a lambda
    # would read only when it fires.
    def flipper(name: str) -> Callable[[Any], Any]:
        return lambda event: flip(name, bool(event.value))

    entries: list[tuple[Any, Any]] = [panel.lede(note)]
    for name, label in sorted(known.items(), key=lambda pair: pair[1]):
        entries.append((label, panel.switch(name in on, flipper(name))))
    if body is None:
        return entries
    with body:
        panel.facts(ui, entries)
    return entries


async def _kind_rows(library: Library, rerender: Callable[[], None],
                     page: str) -> list:
    """One registry's switches as entries, for a page that orders them among its own."""
    found = KIND_PAGES.get(page)
    if found is None:
        return []
    note, _section, name, items, mode = found
    return await _fill_kinds(library, rerender, None, note, "", name, items, mode)


async def _vps_foot(library: Library, rerender: Callable[[], None]) -> list[tuple[Any, Any]]:
    """When the catalog was last asked, and the way to ask now.

    A schedule is a setting and the schema renders it; "do it now" is not a setting and
    has nowhere in a schema page to live, so a page may carry a foot for the one thing
    that is an act rather than a value.

    Rows rather than a drawing, because they join the page's one list. A second grid
    sizes a label column of its own and its values start somewhere else entirely.
    """
    try:
        state = await offload.io(library.vps_sync_state)
    except Exception as exc:  # noqa: BLE001 - a settings page says why, never 500s
        return [panel.intro(t("console.settings.could_not_read_sync", exc=(exc)))]

    async def now() -> None:
        # Held: an ongoing notification never times out on its own.
        checking = ui.notification(t("console.settings.checking_vpsdb"), spinner=True, timeout=None)
        try:
            done = await offload.io(library.sync_vps)
        except Exception as exc:  # noqa: BLE001
            ui.notify(t("console.settings.could_not_check", exc=(exc)), type="negative")
            return
        finally:
            checking.dismiss()
        # "Already current" is the ordinary outcome and says itself; a positive toast
        # for it would make the rare one look the same as the common one.
        ui.notify(t("console.settings.vpsdb_updated") if done.get("changed")
                else t("console.settings.already_date"),
                  type="positive" if done.get("changed") else "info")
        rerender()

    # No heading of its own: the group above already names the catalog, and a second
    # one here read as a separate subject.
    return [_last_checked(str(state.get("checked") or ""), now)]


def _last_checked(checked_at: str, now: Callable[[], Any]) -> tuple[Any, Any]:
    """When something kept was last read, and the act that reads it now."""
    def checked() -> None:
        with ui.element("div").classes("console-fact-edit"):
            shown = ui.label(when.ago(checked_at) or t("word.never")) \
                .classes("console-fact-value truncate min-w-0")
            if checked_at:
                shown.tooltip(when.local(checked_at))
            panel.action(t("console.settings.check_now"), now, icon=verbs.REFRESH, inline=True)()

    return (t("console.settings.last_checked"), checked)


async def _themes_foot(library: Library, rerender: Callable[[], None]) -> list[tuple[Any, Any]]:
    try:
        held = await offload.io(library.themes)
    except Exception as exc:  # noqa: BLE001 - a settings page says why, never 500s
        return [panel.intro(t("console.settings.could_not_read_themes", exc=exc))]

    async def now() -> None:
        checking = ui.notification(t("console.settings.checking_themes"), spinner=True,
                                   timeout=None)
        try:
            await offload.io(library.themes, True)
        except Exception as exc:  # noqa: BLE001
            ui.notify(t("console.settings.could_not_check", exc=exc), type="negative")
            return
        finally:
            checking.dismiss()
        rerender()

    return [_last_checked(str(held.get("checked") or ""), now)]


async def _input_foot(library: Library, rerender: Callable[[], None]) -> list[tuple[Any, Any]]:
    """The input detector, under the bindings that name what it sees.

    Here because it is the same question one row up asked backwards. A binding says
    *this key does that*; somebody who does not know which physical button is which
    cannot use the row at all until something tells them. It sets nothing.
    """
    return [(panel.HEADING, t("word.input_detector")),
            (panel.FULL, input_watch.strip)]


# section -> what to draw under its settings. Only where a page has an act in it, or a
# reading that answers a question its settings raise.
FOOTERS: dict[str, Callable] = {"vpsdb": _vps_foot, "themes": _themes_foot,
                                 "input": _input_foot}

# page -> the line under its heading. Optional: a page whose name says the whole thing
# takes none.
PAGE_NOTES: dict[str, str] = {
    "vpinfe.commands": "console.settings.run_whoever_vpinfe_running",
    "frontend.table_commands": "console.settings.run_whoever_vpinfe_running",
    "vpinfe.console": "console.settings.note_console",
    "vpinfe.logger": "console.settings.note_logger",
    "frontend.themes": "console.settings.note_themes",
    "frontend.chromium": "console.settings.note_chromium",
    "hardware.output": "console.settings.note_output",
    "frontend.presentation": "console.settings.note_presentation",
    "vpinfe.tools": "console.settings.note_tools",
    "library.updates": "console.settings.note_updates",
    "library.audit": "console.settings.note_audit",
    "vpinfe.vpxmobile": "console.settings.note_vpxmobile",
}


def page_head(key: str) -> None:
    """A page's name above its settings, and the line saying what it is for.

    `panel.header`'s treatment rather than a heading inside the panel: the cyan one is
    for a group within a page, and using it for the page's own name ranked the two the
    same.
    """
    said = PAGE_NOTES.get(key, "")
    panel.header(_page_label(key), t(said) if said else "")


# The two kind pages are not schema pages. What they switch is a *list* in the config,
# and the switches themselves come from the two registries - which `common/` may not
# import, because nothing in it may reach up into a domain package. The Console may, so the
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
    "library_checks": (CHECKS_NOTE, "", "hidden_checks",
                       lambda _: _check_labels(), "hidden"),
}


def _check_labels() -> dict[str, str]:
    from console.sections import CHECKS
    return {key: name for key, name, _description, _predicate in CHECKS}

PAGES: dict[str, Callable[[], None]] = {}



def _page_label(key: str) -> str:
    """A page's name, from the one place it is written.

    Identity is searched too: it is pinned by `system_pages` rather than declared in the
    index, so looking only at the index answered a page the rail draws with its own key.
    """
    pages = [page for _group, group_pages in DEVICE_INDEX for page in group_pages]
    pages.append(IDENTITY_PAGE)
    found = next((label for item, label, _kind, _sections, _feature in pages
                  if item == key), "")
    return t(found) if found else key


# A section that heads a page shared with others, where the key makes a poor heading:
# `windows.playfield` humanizes to "Windows Playfield", and the screen is the Playfield.
SECTION_LABELS: dict[str, str] = {
    "windows.playfield": "console.settings.section_playfield",
    "real_dmd": "console.settings.section_real_dmd",
    "windows.backglass": "console.settings.section_backglass",
    "windows.score_view": "console.settings.section_score_view",
}


def _section_label(key: str) -> str:
    """What to call a config section on screen.

    A page's own name where a page is that one section, otherwise a declared heading,
    otherwise the key made readable.
    """
    named = next((label for _group, pages in DEVICE_INDEX
                  for _item, label, _kind, sections, _feature in pages
                  if sections == (key,)), "") or SECTION_LABELS.get(key, "")
    return t(named) if named else " ".join(humanize(part) for part in key.split("."))


# `install` and `themes` appear on no page below, deliberately: the first is the device's
# identity and is edited in Details, and the second is read-only over HTTP wherever it is
# served from.
# A device's pages, in the shape this page uses for this install's own: grouped, named in a
# person's words, one page per topic rather than one per config section. Several sections
# can back one page - a machine's screens are four of them - because how the config file
# is divided is not how somebody looks for a setting.
#
# group -> ((page key, label, kind, sections it draws, feature), ...)
# Every page names a feature, `core` being the one every install has. `kind` picks the
# renderer.
SCHEMA_PAGE, KIND_PAGE, BUILT_PAGE = "schema", "kind", "built"

DevicePage = tuple[str, str, str, tuple[str, ...], str]

DEVICE_INDEX: tuple[tuple[str, tuple[DevicePage, ...]], ...] = (
    # The install itself, as against the cabinet it drives, what a player sees, what it
    # collects and what it talks to. Identity leads it and is pinned by `system_pages`.
    ("console.settings.group_vpinfe", (
        ("vpinfe.network", "console.settings.page_network", SCHEMA_PAGE, ("network",),
                 install_identity.CORE),
        # How much is written down and where it goes. The records themselves are a
        # place of their own under System, so this page is named for the act rather
        # than for them - two things called Logs is one too many.
        ("vpinfe.logger", "console.settings.page_logger", SCHEMA_PAGE, ("logger",),
                 install_identity.CORE),
        ("vpinfe.console", "console.settings.page_console", SCHEMA_PAGE, ("console",),
                 install_identity.CORE),
        ("vpinfe.commands", "console.settings.page_commands", SCHEMA_PAGE, ("commands",),
                 install_identity.CORE),
        # This install's, not the library's: nvtop answers Metrics and ffmpeg would
        # answer media, so an OS dependency belongs to the machine that has to have it.
        ("vpinfe.tools", "console.settings.page_tools", SCHEMA_PAGE, ("tools",),
                 install_identity.CORE),
        ("vpinfe.vpxmobile", "console.settings.page_vpxmobile", SCHEMA_PAGE,
                 ("vpxmobile",), "devices"),
    )),
    ("console.settings.group_hardware", (
        ("hardware.displays", "console.settings.page_displays", SCHEMA_PAGE,
         ("windows.playfield", "windows.backglass", "windows.score_view", "real_dmd"),
         "frontend"),
        ("hardware.input", "console.settings.page_input", SCHEMA_PAGE, ("input",), "frontend"),
        ("hardware.output", "console.settings.page_output", SCHEMA_PAGE, ("dof",), "frontend"),
    )),
    ("console.settings.group_library", (
        ("library.media", "console.settings.page_media", SCHEMA_PAGE, ("media",), "library"),
        ("library.assets", "console.settings.page_assets", SCHEMA_PAGE, ("assets",), "library"),
        ("library.audit", "console.settings.page_audit", SCHEMA_PAGE,
                ("vpsdb",), "library"),
        ("library.updates", "console.settings.page_updates", SCHEMA_PAGE, ("updates",),
                "library"),
    )),
    ("console.settings.group_frontend", (
        ("frontend.presentation", "console.settings.page_presentation", SCHEMA_PAGE,
                ("presentation",), "frontend"),
        ("frontend.behavior", "console.settings.page_behavior", SCHEMA_PAGE, ("behavior",),
                "frontend"),
        ("frontend.themes", "console.settings.page_themes", SCHEMA_PAGE, ("themes",), "frontend"),
        ("frontend.table_commands", "console.settings.page_table_commands", SCHEMA_PAGE,
                ("table_commands",), "frontend"),
        ("frontend.chromium", "console.settings.page_chromium", SCHEMA_PAGE, ("chromium",),
                "frontend"),
    )),
)

# A schema page that also draws switches from a registry, ordered among its settings
# rather than beside them.
# page -> ((registry, its heading, the schema heading it sits above), ...). An empty
# third entry puts the block at the foot.
PAGE_KINDS: dict[str, tuple[tuple[str, str, str], ...]] = {
    "library.audit": (("library_checks", "console.settings.heading_reporting", ""),),
    "library.media": (("media_kinds", "console.settings.heading_kinds", "Local Sources"),
              ("media_sources", "console.settings.heading_online_sources", "Wheels")),
    "library.assets": (("asset_kinds", "console.settings.heading_kinds", "Local Sources"),),
}


def pages_for_features(features: Any) -> list[tuple[str, DevicePage]]:
    """(group, page) for every page the features an install has can answer for.

    `core` is held whatever arrives, including nothing. Identity and features are not
    filtered here at all - `system_pages` puts them in front - because an install with
    everything switched off has to be able to switch something on, and that screen is
    the only way in.
    """
    held = ({str(f).strip().lower() for f in (features or [])}
            or set(install_identity.FEATURES)) | {install_identity.CORE}
    return [(group, page) for group, pages in DEVICE_INDEX for page in pages
            if page[4] in held]


# What a person calls each feature. The key names the thing and the label says what you
# do with it, which is why `devices` reads as Device Management on screen.
FEATURE_LABELS = {
    install_identity.LIBRARY: "console.settings.feature_label_library",
    install_identity.FRONTEND: "console.settings.feature_label_frontend",
    install_identity.DEVICES: "console.settings.feature_label_device_management",
    install_identity.OVERVIEW: "console.settings.feature_label_overview",
}

# What switching one on gets you. The name says which feature; this says what the install
# then does, which is the half a person switching it on is actually choosing between.
FEATURE_NOTES = {
    install_identity.LIBRARY: "console.settings.feature.curate_game_library_machine",
    install_identity.FRONTEND: "console.settings.feature.launch_games_machine",
    install_identity.DEVICES: "console.settings.feature.manage_other_vpinfe_installs",
    install_identity.OVERVIEW: "console.settings.feature.add_front_page_summarising"
}


def features_said(features: Any) -> str:
    """What an install is for, in a person's words.

    `core` is left out: every install has it, so a list naming it prints the same word
    on every row. Anything else unrecognized is shown as it arrived, because a device
    reporting a feature this build has not heard of is a fact rather than a blank.
    """
    return ", ".join(t(FEATURE_LABELS.get(str(name), str(name)))
                     for name in (features or [])
                     if str(name) != install_identity.CORE)


IDENTITY = "vpinfe.install"

# The one page that is pinned rather than filtered: this is where features are switched
# on, so an install with none still has a way to fix itself from inside. Not a schema
# page - `features` is a list in the file and a closed set on screen, and a
# comma-separated text field is the wrong control for that.
IDENTITY_PAGE: DevicePage = (IDENTITY, "console.settings.page_install", BUILT_PAGE,
                             ("install",),
                             install_identity.CORE)

# The same group the rest of the install's own pages are in, so it leads them rather than
# sitting in a group of one. `system_pages` puts it first and nothing filters it.
IDENTITY_GROUP = "console.settings.group_vpinfe"


def system_pages(features: Any) -> list[tuple[str, DevicePage]]:
    """This install's own index: identity first, then whatever its features can answer
    for."""
    return [(IDENTITY_GROUP, IDENTITY_PAGE), *pages_for_features(features)]


def _page_holding(section: str) -> str:
    """Which page draws a config section, or "" where none does."""
    return next((page[0] for _group, pages in DEVICE_INDEX for page in pages
                 if section in page[3]), "")


def pages_in_trouble(items: Any) -> dict[str, list[Any]]:
    """Unmet requirements, keyed by the page that carries the setting.

    A requirement whose setting is on no page is logged rather than counted: a badge
    that leads nowhere is worse than no badge, and this is a mistake in the index rather
    than in the install.
    """
    found: dict[str, list[Any]] = {}
    for item in items:
        # Only the ones a settings page can fix. A launcher is not a setting, and it
        # carries its own mark on the entry that leads to it.
        if item.where != feature_checks.WHERE_SETTINGS:
            continue
        page = _page_holding(item.section)
        if not page:
            logger.warning("No settings page draws %s, so nothing can lead to %s.%s",
                           item.section, item.section, item.key)
            continue
        found.setdefault(page, []).append(item)
    return found


def field_marks(items: Any, checks: list[dict]) -> dict[tuple[str, str], dict]:
    """What to draw beside each path field: what the disk said, then what a feature needs.

    The second overrides the first for the case that matters. A blank path draws nothing
    on its own, because an optional one left empty is a choice - and a required one left
    empty is exactly what the badge leading here is pointing at.
    """
    found = {(str(check.get("section") or ""), str(check.get("key") or "")): dict(check)
             for check in checks or []}
    for item in items:
        state = panel.REQUIRED if item.state == path_checks.UNSET else item.state
        found[(item.section, item.key)] = {"state": state, "reason": item.reason}
    return found


def local_trouble() -> list[Any]:
    """What this install's enabled features are missing.

    Asked of this machine's own configuration rather than over the API: a path is only
    answerable by the machine holding it, and this is that machine. Its launchers go with
    it, because whether a table can be played is now a question about one of them.
    """
    from common.games import launchers, locations
    from common.paths import get_ini_config

    store = launchers.get_launcher_store()
    held = locations.configured()
    return feature_checks.unmet(
        get_ini_config(),
        launcher=launchers.default_for("vpx", store.launchers()),
        locations=[(one, locations.state_of(one)) for one in held])


def build_library_page(library: Library, rerender: Callable[[], None], key: str,
                       kind: str) -> None:
    """A library page, drawn where a device's rail asks for it.

    These are this install's own: what the library collects, and what it is checked for.
    They reach for registries and for its client rather than for a config schema, which
    is why they are not schema pages and are only offered on an install that holds a
    library.
    """
    if kind == BUILT_PAGE:
        drawn = PAGES.get(key)
        if drawn is None:
            panel.facts(ui, [panel.intro(t("console.settings.not_built_yet"))])
            return
        drawn()
        return

    found = KIND_PAGES.get(key)
    if found is None:
        panel.facts(ui, [panel.intro(t("console.settings.not_built_yet"))])
        return
    note, _section, name, items, mode = found
    _kind_page(library, rerender, note, "", name, items, mode)


def section_rows(source: Any, section: str, options: list[dict], values: dict,
                 writable: bool, rerender: Callable[[], None],
                 checks: dict[tuple[str, str], dict] | None = None,
                 suggestions: dict[str, Any] | None = None,
                ) -> list[tuple[Any, Any]]:
    """One section's settings as fact rows, from whatever is serving them.

    `source` is anything with `put_config` - this install's own client for itself, or
    the client that reaches another machine. Which is the whole reason a device's
    settings page and this one are one page: the schema decides the controls and the
    source decides where the write lands.
    """
    current = dict(values.get(section) or {})
    # What every setting in this section is *effectively* set to, defaults included. An
    # editor that answers for a whole section - which binding two actions both claim -
    # cannot see an action still on its default from `current` alone, because a value
    # equal to its default is not stored.
    effective = {one["key"]: current.get(one["key"], one.get("default"))
                 for one in options}
    entries: list[tuple[Any, Any]] = []
    if not writable:
        entries.append(panel.intro(t("console.settings.read_install")))

    names_groups = any(option.get("group") for option in options)
    heading = ""
    for option in _by_group(options):
        group = str(option.get("group_label") or "")
        if not group and names_groups:
            group = t("console.settings.group_other")
        if group and group != heading:
            entries.append((panel.HEADING, group))
        heading = group
        value = current.get(option["key"], option.get("default"))
        entries.append((option.get("label") or humanize(option["key"]),
                        control_for(
                            option, value,
                            _saver(source, section, option["key"]),
                            writable=writable, rerender=rerender,
                            check=(checks or {}).get((section, option["key"])),
                            suggestions=suggestions,
                            section_values=effective)))
        if option.get("description"):
            entries.append(panel.note(option["description"]))
        # Under the last field of a pair, where somebody has just read what it does and
        # is about to type into it.
        if section == "commands" and option["key"] == "on_vpinfe_exit":
            commands_help.add_to(entries, tokens.VPINFE)
        elif section == "table_commands" and option["key"] == "on_exit":
            commands_help.add_to(entries, tokens.TABLE)
    return entries


async def build_device_page(source: Any, context: dict[str, Any], schema: list[dict],
                            values: dict, sections: tuple[str, ...],
                            checks: dict[tuple[str, str], dict] | None = None,
                            suggestions: dict[str, Any] | None = None,
                            blocks: list[tuple[str, list]] | None = None) -> None:
    """One page of a device's settings, drawn exactly as this install's are.

    Several config sections can make one page - a machine's screens are four of them -
    with a heading each where there is more than one. How the config file is divided is
    not how somebody looks for a setting, which is why the pages are declared rather
    than taken from the schema's own shape.

    `checks` is what to draw beside each path field, and only the install being drawn can
    supply it. The machine holding a path answers for it, so asking this one about
    another machine's disk would put a red cross on a file that is perfectly fine over
    there - which is why a device's pages pass none.
    """
    def rerender() -> None:
        rebuild = context.get("rebuild")
        if rebuild is not None:
            ui.timer(0.01, rebuild, once=True)

    drawn = [block for block in schema
             if str(block.get("name")) in sections and block.get("options")]
    if not drawn:
        panel.facts(ui, [panel.intro(t("console.settings.device_declares_nothing_page"))])
        return

    entries: list[tuple[Any, Any]] = []
    for block in drawn:
        name = str(block.get("name"))
        if len(drawn) > 1:
            entries.append((panel.HEADING, _section_label(name)))
        entries += section_rows(source, name, block["options"], values,
                                bool(block.get("writable")), rerender, checks,
                                suggestions)
        # A page may carry a foot for the one thing on it that is an act rather than a
        # value. Only where this install's own client is what serves the page: these reach
        # for the library, which another machine's client cannot answer for.
        foot = FOOTERS.get(name)
        if foot is not None and source is context.get("library"):
            entries += await foot(source, rerender)
    panel.facts(ui, _spliced(entries, blocks or []))


def _spliced(entries: list, blocks: list[tuple[str, list]]) -> list:
    """Registry blocks put above the heading each one names, or at the foot.

    By heading rather than by index: a block says which part of the page it belongs
    above, and moving a setting in the schema moves the heading with it.
    """
    for above, rows in blocks:
        at = next((i for i, one in enumerate(entries)
                   if one[0] is panel.HEADING and str(one[1]) == above), len(entries))
        entries = entries[:at] + rows + entries[at:]
    return entries



def build_system(library: Library, state: dict[str, Any], redraw: Callable[[], None],
                 discovery: dict[str, Any]) -> None:
    """This install's own configuration: the index, and the page it opens.

    Its own entry point rather than a section of the device panel, because it is about
    the install you are reading the Console from and needs nothing selected to be about
    one.
    """
    pages = system_pages(discovery.get("features"))
    known = {page[0]: page for _group, page in pages}
    chosen = str(state.get("settings_page") or "")
    # A page this install has no answer for is not a place to land: an address written
    # while `library` was on still names Media Kinds after it has been switched off.
    if chosen not in known:
        chosen = pages[0][1][0]
    state["settings_page"] = chosen

    # What is misconfigured, marked at every level on the way to the setting that fixes
    # it: the group, then the page, then the field's own cross.
    hurt = pages_in_trouble(state.get("trouble") or [])
    groups_hurt = {group for group, page in pages if page[0] in hurt}

    entries: list[tuple[Any, ...]] = []
    heading = ""
    for group, page in pages:
        if group != heading:
            entries.append((panel.GROUP, group, "",
                            panel.trouble_mark() if group in groups_hurt else None))
            heading = group
        found = hurt.get(page[0]) or []
        entries.append((page[0], page[1], "",
                        panel.trouble_mark(_said(found)) if found else None))

    def pick(key: str) -> None:
        state["settings_page"] = key
        redraw()
        # The address was read on arrival and never written again, so a page opened by
        # hand was lost on the next reload - and a reload is not always something you
        # chose.
        deeplink.sync(state)

    work = panel.sections(entries, chosen, pick, rail_px=RAIL_PX)
    with work:
        body = ui.column().classes("min-w-0 overflow-auto gap-0 console-workbench-body "
                                   "console-settings-body")
    # On a timer, because a page reads the schema and the values over HTTP and the draw
    # it is part of runs on the event loop, where the client refuses a call.
    ui.timer(0.01,
             lambda: _draw_system_page(library, redraw, body, known[chosen], discovery,
                                       state.get("trouble") or []),
             once=True)


def _said(items: Any) -> str:
    """The reasons behind one mark, in the words the check already wrote for the person
    who has to fix them. De-duplicated: two features needing one setting is two entries
    saying the same sentence."""
    return " ".join(dict.fromkeys(item.reason for item in items if item.reason))


async def _draw_system_page(library: Library, redraw: Callable[[], None], body: Any,
                            page: DevicePage, discovery: dict[str, Any],
                            trouble: Any) -> None:
    key, _label, kind, sections, _feature = page
    if key == IDENTITY:
        with body:
            page_head(key)
            await _identity_page(library, str(discovery.get("display_name") or ""),
                                 redraw)
        return
    if kind != SCHEMA_PAGE:
        with body:
            page_head(key)
            build_library_page(library, redraw, key, kind)
        return
    try:
        schema = await offload.io(library.config_schema)
        values = await offload.io(library.config_values)
        checks = await offload.io(library.config_path_checks)
        offered = await _suggestions(library, schema, sections)
    except Exception as exc:  # noqa: BLE001 - a settings page says why, never 500s
        with body:
            panel.facts(ui, [panel.intro(t("said.could_not_read_the_settings", exc=(exc)))])
        return
    blocks = []
    for registry, heading, above in PAGE_KINDS.get(key, ()):
        rows = await _kind_rows(library, redraw, registry)
        blocks.append((above, [(panel.HEADING, t(heading)), *rows]))
    with body:
        page_head(key)
        await build_device_page(library, {"library": library, "rebuild": redraw},
                                schema, values, sections,
                                checks=field_marks(trouble, checks),
                                suggestions=offered, blocks=blocks)


async def _suggestions(library: Library, schema: list[dict],
                       sections: tuple[str, ...]) -> dict[str, Any]:
    """The live lists this page's settings say are worth offering.

    Asked for only where a setting on this page declares one, so opening Displays does
    not go and look at the network.
    """
    wanted = {str(option.get("suggest") or "")
              for block in schema if str(block.get("name")) in sections
              for option in block.get("options") or []}
    offered: dict[str, Any] = {}

    if config_schema.SUGGEST_LIBRARIES in wanted:
        found = await offload.io(library.discovered_installs)
        # Only the ones that have a library to read. An install that just launches games
        # has nothing to offer another that does the same.
        offered[config_schema.SUGGEST_LIBRARIES] = {
            str(install.get("url") or ""): _install_label(install)
            for install in found
            if install_identity.LIBRARY in (install.get("features") or [])}

    if config_schema.SUGGEST_THEMES in wanted:
        known = await offload.io(library.themes)
        # Keyed by what is stored, labelled by what the theme calls itself - they are
        # usually the same word and a theme is free to make them differ.
        offered[config_schema.SUGGEST_THEMES] = {
            str(theme.get("key") or ""): str(theme.get("name") or theme.get("key") or "")
            for theme in (known.get("themes") or []) if theme.get("key")}

    if config_schema.SUGGEST_COLLECTIONS in wanted:
        # `collections()` answers from what the Collections page last read, which on
        # this page is nothing. This is already off the event loop, so read.
        held = await offload.io(library.load_collections)
        offered[config_schema.SUGGEST_COLLECTIONS] = {
            str(row.get("name") or ""): str(row.get("name") or "")
            for row in held if row.get("name")}

    return offered


def _install_label(install: dict) -> str:
    """What a discovered install is called in a list, with its address.

    Both, because a name is what somebody recognizes and the address is what they are
    actually choosing - and two machines on one network can share a name.
    """
    name = str(install.get("display_name") or "").strip()
    url = str(install.get("url") or "")
    return f"{name} - {url}" if name else url


async def _identity_page(library: Library, reported: str,
                         redraw: Callable[[], None]) -> None:
    """What this install is called, and what it is for."""
    try:
        values = await offload.io(library.config_values)
    except Exception as exc:  # noqa: BLE001 - a settings page says why, never 500s
        panel.facts(ui, [panel.intro(t("said.could_not_read_the_settings", exc=(exc)))])
        return
    held = dict(values.get("install") or {})
    on = _listed(held.get("features"))

    async def rename(text: str) -> None:
        await _write(library, "install", "display_name", text.strip())

    async def flip(name: str, wanted_on: bool) -> None:
        # Switching the last one off is allowed. An install for nothing is a real state
        # and this page is still here in it: everything you need to make it for
        # something belongs to `core`.
        after = (on | {name}) if wanted_on else (on - {name})
        # In the order the install declares them, so the file reads the same however the
        # switches were thrown.
        if await _write(library, "install", "features",
                        [name for name in install_identity.FEATURES if name in after]):
            _take_the_page_again()

    # Bound by a call rather than captured off the loop variable, which a lambda
    # would read only when it fires.
    def flipper(name: str) -> Callable[[Any], Any]:
        return lambda event: flip(name, bool(event.value))

    language = config_schema.option("install", "language")

    async def relanguage(event: Any) -> None:
        if await _write(library, "install", "language", event.value):
            _take_the_page_again()

    entries: list[tuple[Any, Any]] = [
        # The name it reports with nothing set is its hostname, so the placeholder is
        # that answer rather than the word for it.
        (t("word.name"), panel.field(str(held.get("display_name") or ""),
                                                 rename,
                             placeholder=reported)),
        panel.note(t("console.settings.what_install_called_where")),
    ]
    if language is not None:
        entries.append((language.label or humanize(language.key),
                        panel.select(list(language.choices),
                                     str(held.get("language") or language.default),
                                     relanguage)))
        if language.description:
            entries.append(panel.note(language.description))
    entries += [
        (panel.HEADING, t("console.settings.features")),
        panel.intro(t("console.settings.what_install_each_one")),
    ]
    for name in install_identity.FEATURES:
        entries.append((t(FEATURE_LABELS[name]),
                        panel.switch(name in on, flipper(name))))
        entries.append(panel.note(t(FEATURE_NOTES[name])))
    panel.facts(ui, entries)


def _take_the_page_again() -> None:
    """Reload, because what just changed decides how the page is built.

    Features pick the nav sections, this index, and the capabilities the shell read on
    the way in. Redrawing under them would leave all three describing the install as it
    was, and the address already carries where you are standing.
    """
    ui.navigate.reload()
