"""Settings: a grouped index beside a content pane, inside the shell.

The index is the point. A flat list of pages hides the shape of the product; a grouped
one is a map of it, and it is the thing VPin Studio gets right about its preferences
even though it throws the rest of the app away to show it. This keeps the shell.

Every control carries its explanation beneath it, not in a tooltip and not in a link.
That single habit is what makes a dense settings page readable.
"""

from __future__ import annotations

from collections.abc import Callable

from nicegui import ui

from hubui import deeplink

# group -> (key, label) - VPinFE first, because that is the thing being configured and
# everything else is either downstream of it or somebody else's software.
# An object's settings live with the object. What is left here is what belongs to the
# install as a whole and has no other owner - which is the only rule that keeps this
# section from becoming the bucket everything lands in. See ELSEWHERE.
INDEX: tuple[tuple[str, tuple[tuple[str, str], ...]], ...] = (
    ("VPinFE", (("general", "General"), ("library", "Library"),
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
    ("Themes", "settings",
     "A theme carries its own settings; they are shown with the theme."),
    ("Media sources", "media",
     "A source is a thing you add and remove, not a preference."),
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
    "vps": "Matching against the spreadsheet, and what an update notification means.",
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


def _general() -> None:
    ui.label("General").classes("hub-card-title")
    with ui.element("div").classes("hub-card w-full mt-2"):
        _setting("Install name",
                 "Shown wherever this install appears in a list, including on another "
                 "hub. Defaults to the hostname.",
                 lambda: ui.input(value="PinballPC").props("dense outlined")
                 .classes("w-80"))
        _setting("Confirm before exiting the frontend",
                 "Off by default. Worth turning on for a cabinet where the exit button "
                 "is easy to hit by accident.",
                 lambda: ui.switch(value=False).props("dense"))
        _setting("Send anonymous usage counts",
                 "Never on unless you turn it on, and it never includes table names, "
                 "file paths or anything about your library.",
                 lambda: ui.switch(value=False).props("dense"))


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


PAGES: dict[str, Callable[[], None]] = {
    "general": _general,
    "checks_library": _checks_library,
}


def build(state: dict, rerender: Callable[[], None],
          go: Callable[[str], None] | None = None) -> None:
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
            page = PAGES.get(current)
            if page is not None:
                page()
            else:
                label = next((lbl for _, items in INDEX for key, lbl in items
                              if key == current), current)
                ui.label(label).classes("hub-card-title")
                with ui.element("div").classes("hub-card w-full mt-2"):
                    ui.label(STUBS.get(current, "Not designed yet.")) \
                        .classes("hub-help")
                    ui.label("Not built.").classes("text-xs opacity-50 mt-2")
