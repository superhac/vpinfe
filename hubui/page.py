"""The Hub UI shell: nav, content and the workbench that follows the selection."""

from __future__ import annotations

import asyncio
from typing import Any

from nicegui import run, ui

from hubui import devices as devices_page
from hubui import games, sections, theme, workbench
from hubui import settings as settings_page
from hubui.api import HubClient
from hubui.data import Library

# Both panel headers are pinned to this, so the two toggles sit at the same height
# whatever their labels do. Left to the text, one was 52px and the other 22px.
HEADER_H_PX = 52

NAV_WIDE_PX = 220
WORKBENCH_WIDE_PX = 320
WORKBENCH_MIN_PX = 260
# Past the work width, so the divider reaches every mode on its own and Full is the far
# end of one continuum rather than the only way in. Short of squeezing the list out -
# that is Full's job, and Full has a control that brings it back.
WORKBENCH_MAX_PX = 1000
# One rail width for both panels - they collapse to the same thing.
RAIL_PX = 57

# Every entry is a place, not a thing. Jobs used to sit here and does not any more:
# it is transient, it belongs in the header where it is visible from every page, and a
# rail slot is too expensive for something that is empty most of the time. Logs moved
# under Settings > Diagnostics with the rest of the troubleshooting surface, and Gallery
# is gone - the media map in the details pane answers "what is missing here" and the
# Media section answers "what is missing anywhere", which is what it was reaching for.
NAV_ITEMS = (
    ("overview", "Overview", "space_dashboard"),
    ("games", "Games", "sports_esports"),
    ("collections", "Collections", "collections_bookmark"),
    ("media", "Media", "perm_media"),
    ("devices", "Devices", "devices"),
    ("extensions", "Extensions", "extension"),
    ("settings", "Settings", "tune"),
)

# Section title, and what one row is. The second half is the load-bearing part: a
# section owns a subject, and a view is a preset of columns over it.
SECTIONS = {
    "overview": ("Overview", None),
    "games": ("Games", "game"),
    "collections": ("Collections", "collection"),
    "media": ("Media", "media slot"),
    "devices": ("Devices", "device"),
    "extensions": ("Extensions", "extension"),
    "settings": ("Settings", None),
}


def _read_hub() -> dict[str, Any]:
    """Every blocking call the page needs, made once off the event loop.

    The Hub UI consumes its own process over HTTP, so a synchronous page handler asking
    the API for 147 games deadlocks: uvicorn cannot answer a request it is blocked
    inside. Keeping the loop free is the cost of the boundary, and it is worth paying -
    the alternative is importing the services, which is what the boundary exists to
    prevent.
    """
    client = HubClient()
    library = Library(client)
    library.load()
    capabilities = client.capabilities()
    return {
        "library": library,
        "discovery": client.discovery(),
        "devices": client.devices(),
        "device_capabilities": [entry["name"] for entry in capabilities
                                if "device" in (entry.get("residency") or [])],
        "local_capabilities": {entry["name"] for entry in capabilities},
    }


@ui.page("/hub")
async def hub_page() -> None:
    # The palette and Quasar's dark mode are two separate switches. The toggle button
    # that used to own the second one is gone, so it is set here - without it the shell
    # renders light while the tokens stay dark.
    ui.dark_mode(True)
    theme.apply_colors(dark=True)
    theme.apply_flair()
    # The shell takes the viewport once, here, and every height below it is flex. The
    # old layout gave each pane its own calc(100vh - N) against chrome that later
    # changed, so a pane collapsed the moment the header it was subtracting went away.
    ui.query(".nicegui-content").classes("p-0 gap-0 h-screen")

    # The shell first, then wait for the browser to have it, and only then read the
    # hub. Reading first meant a page function that took two seconds to return, and
    # nicegui abandons a response that is not ready in three - which surfaced as a
    # reload loop and a page whose handlers were never wired, not as a slow page.
    with ui.column().classes("w-full h-full items-center justify-center gap-3") as loading:
        ui.spinner(size="lg").classes("text-primary")
        ui.label("Reading the hub").classes("text-sm opacity-60")

    await ui.context.client.connected()
    loaded = await run.io_bound(_read_hub)
    loading.delete()

    library = loaded["library"]
    discovery = loaded["discovery"]
    devices = loaded["devices"]
    device_capabilities = loaded["device_capabilities"]
    local_capabilities = loaded["local_capabilities"]

    state: dict[str, Any] = {"view": "overview", "device": None, "mini": False,
                             "workbench": True, "settings_page": "general",
                             "subject": "game"}

    labels: list[ui.label] = []
    nav_rows: list[ui.row] = []
    destinations: dict[str, ui.row] = {}

    def toggle_mini() -> None:
        """Collapse the nav to an icon rail rather than hiding it.

        Hiding it entirely costs you the map; mini keeps every destination reachable
        and one click away, which is the point of a rail.
        """
        state["mini"] = not state["mini"]
        left.props(add="mini") if state["mini"] else left.props(remove="mini")
        for label in labels:
            label.set_visibility(not state["mini"])
        nav_icon.props(f'name={"menu" if state["mini"] else "menu_open"}')
        for row in nav_rows:
            # Centred on the rail: left-aligned icons under a 220px gutter look centred
            # and under a 57px one plainly are not.
            row.classes(add="justify-center", remove="px-3") if state["mini"] \
                else row.classes(add="px-3", remove="justify-center")


    with ui.left_drawer(value=True).props(f"width={NAV_WIDE_PX} bordered") as left:
        # A nav header row carrying the collapse control - the shape 2.x already uses
        # (`manager-nav-header`). It is the panel's own chrome, so it costs nothing that
        # was not already the panel, and nothing floats over the grid.
        nav_header = ui.row() \
            .classes("items-center gap-3 cursor-pointer w-full hub-nav-header") \
            .on("click", lambda: toggle_mini())
        with nav_header:
            nav_icon = ui.icon("menu_open", size="24px").classes("opacity-70")
            # Larger and heavier than a nav item, like HA's own title. Row height may
            # differ from the items below - that is fine and expected; what has to stay
            # aligned is the icon column, which does not depend on the label's size.
            labels.append(ui.label("VPinFE Hub")
                          .classes("whitespace-nowrap hub-nav-title"))
        nav_header.tooltip("Show or hide the navigation")
        nav_rows.append(nav_header)
        for key, label, icon in NAV_ITEMS:
            _nav_item(key, label, icon, state, lambda: render(), labels, nav_rows,
                      destinations)
        ui.space()
        foot = ui.column().classes("items-center gap-1 px-3 py-3 w-full") \
            .style("border-top:1px solid rgba(255,255,255,0.10)")
        with foot:
            # Large enough to actually read the mark. It joins `labels` so it hides with
            # the rail - an 820px square badge has nothing legible left at 57px, so
            # scaling it down there would be worse than dropping it.
            labels.append(ui.image(theme.LOGO).classes("w-28 h-28 mx-auto"))
        with foot:
            with ui.column().classes("gap-0"):
                labels.append(ui.label(f"v{discovery.get('app_version') or '?'}")
                              .classes("text-xs opacity-70"))
                # Update availability is not on the API: check_for_app_updates lives in
                # managerui and is never served, so an API consumer cannot ask. Left as
                # a slot rather than reached for across the boundary.
                labels.append(ui.label("").classes("text-xs hub-label"))
        nav_rows.append(foot)


    splitter = ui.splitter(reverse=True, limits=(WORKBENCH_MIN_PX, WORKBENCH_MAX_PX),
                           value=WORKBENCH_WIDE_PX) \
        .props("unit=px").classes("w-full h-full")
    with splitter.after, ui.column().classes("w-full h-full gap-0 hub-workbench"):
        # The selected game's name shares the row with the toggle rather than sitting
        # under it - same class list, same height and same gutter as the nav's header,
        # so neither the icon's inset from the edge nor its height can drift.
        workbench_header = ui.row() \
            .classes("items-center gap-2 px-3 cursor-pointer w-full justify-between "
                     "no-wrap hub-panel-header") \
            .style(f"min-height:{HEADER_H_PX}px") \
            .on("click", lambda: show_workbench(not state["workbench"]))
        with workbench_header:
            # min-w-0 lets the column shrink below its content so the title truncates
            # instead of pushing the toggle onto a second line; shrink-0 keeps the
            # toggle at its own size while that happens.
            workbench_title = ui.column().classes("gap-0 min-w-0 overflow-hidden")
            with ui.row().classes("items-center gap-1 shrink-0 no-wrap"):
                # Stepping the list from in here, so a sweep does not need the grid on
                # screen - which is the point of Full.
                ui.button(icon="keyboard_arrow_up", on_click=lambda: _step(-1)) \
                    .props("flat dense round size=sm").on("click.stop", lambda: None) \
                    .tooltip("Previous game")
                ui.button(icon="keyboard_arrow_down", on_click=lambda: _step(1)) \
                    .props("flat dense round size=sm").on("click.stop", lambda: None) \
                    .tooltip("Next game")
                full_icon = ui.button(icon="open_in_full", on_click=lambda: toggle_full()) \
                    .props("flat dense round size=sm").on("click.stop", lambda: None) \
                    .tooltip("Give the workbench the whole window")
                workbench_icon = ui.icon("menu_open", size="24px") \
                    .classes("opacity-70 shrink-0")
        workbench_header.tooltip("Show or hide the workbench")
        # The scrolling belongs to the workbench's body column now, so the outline
        # beside it can stay put while that scrolls.
        panel = ui.column().classes("w-full gap-0 grow min-h-0 overflow-hidden")


    def show_workbench(shown: bool) -> None:
        """Collapse to a rail, never away.

        Hiding it outright left no control to bring it back, which is the only reason
        the floating tab existed. A rail keeps its own toggle on screen, so both panels
        collapse the same way and nothing overlays the grid.
        """
        state["workbench"] = shown
        workbench_icon.props(f'name={"menu_open" if shown else "menu"}')
        # The floor moves with the state. Held at WORKBENCH_MIN_PX the pane cannot be
        # dragged down to a useless sliver while it is open, and the rail is below that
        # floor - so collapsing has to lower it first or Quasar clamps the value back.
        splitter._props["limits"] = [RAIL_PX if not shown else WORKBENCH_MIN_PX,
                                     WORKBENCH_MAX_PX]
        splitter.update()
        # The width you chose, not the width it opens at: show_workbench runs on every
        # selection, so restoring the constant here snapped the pane back to 320 every
        # time you clicked a game.
        splitter.set_value(state.get("workbench_px", WORKBENCH_WIDE_PX) if shown
                           else RAIL_PX)
        panel.set_visibility(shown)
        workbench_title.set_visibility(shown)
        # justify-end, not justify-center: the header keeps its 18px right padding, and
        # centring inside a padded box put the icon 27px in. Held to the right, the
        # padding alone places it exactly where it sits when the panel is open.
        workbench_header.classes(add="justify-end", remove="justify-between") \
            if not shown else \
            workbench_header.classes(add="justify-between", remove="justify-end")


    with splitter.before:
        # 2.x's own 24px. It is dead space by the numbers, but it is what separates the
        # content from the two panels either side and lets the backdrop read as a
        # backdrop rather than a hairline.
        content = ui.column().classes("w-full h-full gap-0 p-6")

    def toggle_full() -> None:
        """The list never goes away - it steps back to the rail every panel here
        collapses to, and this control is what brings it forward again."""
        state["full"] = not state.get("full")
        splitter.classes(add="hub-full") if state["full"] \
            else splitter.classes(remove="hub-full")
        full_icon.props(f'icon={"close_fullscreen" if state["full"] else "open_in_full"}')
        if state["full"] and not state["workbench"]:
            show_workbench(True)
        asyncio.create_task(apply_mode())

    def _step(delta: int) -> None:
        """Move the focused row, which is what the workbench follows. Sent as the key
        the grid already handles rather than reaching into its API, so the buttons and
        the keyboard cannot drift apart."""
        key = "ArrowDown" if delta > 0 else "ArrowUp"
        ui.run_javascript(
            "(() => { const c = document.querySelector('.ag-body-viewport "
            ".ag-cell-focus') || document.querySelector('.ag-body-viewport .ag-cell');"
            " if (c) { c.focus(); c.dispatchEvent(new KeyboardEvent('keydown', "
            "{key: '" + key + "', bubbles: true})); } })()")

    async def apply_mode() -> None:
        """Compare below the work width, work above it; Full is always work.

        Read off the controls that set the width rather than measured in the browser,
        so the mode cannot lag the thing that changed it.
        """
        mode = "work" if (state.get("full") or
                          _splitter_px() >= workbench.WORK_FROM_PX) else "compare"
        if mode == state.get("mode"):
            return
        state["mode"] = mode
        await workbench.build(panel, workbench_title, library, state.get("game"), state)

    async def on_window_resize(event: Any) -> None:
        """The one case the controls cannot cover.

        Resizing the window moves the workbench without touching the divider, so the
        width it was told about goes stale - and a workbench at 500px still showing one
        section because it was 1000px a moment ago is the wrong answer. The browser
        sends what it actually measures, debounced, and only that case needs it.
        """
        try:
            px = float(event.args or 0)
        except (TypeError, ValueError):
            return
        mode = "work" if px >= workbench.WORK_FROM_PX else "compare"
        if mode == state.get("mode"):
            return
        state["mode"] = mode
        await workbench.build(panel, workbench_title, library, state.get("game"), state)

    ui.on("hub_resize", on_window_resize)
    ui.run_javascript(
        "window.addEventListener('resize', () => { clearTimeout(window.__hubRz);"
        " window.__hubRz = setTimeout(() => { const w ="
        " document.querySelector('.hub-workbench');"
        " if (w) emitEvent('hub_resize', w.clientWidth); }, 250); });")

    def _splitter_px() -> float:
        try:
            return float(splitter.value or 0)
        except (TypeError, ValueError):
            return 0.0

    def remember_width(event: Any) -> None:
        """Keep the width a drag settled on. Quasar only reports it on release, which
        is exactly when it is worth keeping."""
        try:
            value = float(event.value or 0)
        except (TypeError, ValueError):
            return
        if value > RAIL_PX:
            state["workbench_px"] = value
        asyncio.create_task(apply_mode())

    splitter.on_value_change(remember_width)

    async def show_game(row: dict | None) -> None:
        # A selection is the only thing that opens the pane. Arriving at a section does
        # not, because there is nothing selected yet to be about.
        if row and not state["workbench"]:
            show_workbench(True)
        state["game"] = (row or {}).get("id")
        await workbench.build(panel, workbench_title, library, state["game"], state)

    def open_device(device) -> None:
        state["view"] = "devices"
        state["device"] = device
        render()

    def clear_workbench() -> None:
        """Empty the pane. Sync, so render() can call it without awaiting a rebuild."""
        workbench_title.clear()
        panel.clear()
        # The same two-line shape a selected game gets, so the header does not change
        # height or alignment as the selection comes and goes.
        with workbench_title:
            ui.label("Game Details") \
                .classes("text-base hub-workbench-title leading-tight truncate")
            ui.label("Select a game").classes("text-xs hub-workbench-label leading-none truncate")

    def crumb() -> None:
        """Section and selection, in one line, at the top of the content pane.

        It lives here rather than in an app header because each pane already owns its
        own chrome in this shell, and adding a fourth band across the top would cost
        height on every page to serve one line of text.
        """
        title, subject = SECTIONS.get(state["view"], (state["view"].title(), None))
        # Games can be shown at more than one subject, so the crumb reads the live
        # choice rather than the section's default - it is the sentence that tells the
        # user what a row means, and it must not contradict the control above it.
        if state["view"] == "games":
            subject = games.SUBJECTS.get(state["subject"], subject).rstrip("s").lower()
        with ui.row().classes("items-center gap-2 w-full no-wrap pb-3"):
            with ui.row().classes("items-center gap-2 grow min-w-0"):
                ui.html(f"<span class='hub-crumb'>VPinFE &nbsp;/&nbsp; <b>{title}</b></span>")
                if subject:
                    ui.label(f"one row is one {subject}") \
                        .classes("hub-help hub-crumb-note")
            ui.button("Look for new tables", icon="refresh",
                      on_click=_look_for_new_tables) \
                .props("flat dense no-caps size=sm").classes("shrink-0") \
                .tooltip("Re-read the game folders and pick up anything added or removed")
            # Jobs is a header affordance, always visible, never a destination. Empty is
            # the normal state and it says so rather than showing a zero.
            ui.button("No active jobs", icon="pending_actions") \
                .props("flat dense no-caps size=sm").classes("shrink-0 opacity-70")

    def render() -> None:
        # A game shown beside a different destination is stale by definition.
        clear_workbench()
        # ...and so is an open pane. Changing section collapses it: the pane is about
        # the selection, the selection did not survive the move, and a pane left open
        # describing nothing is worse than one the next click reopens.
        if state.get("_last_view") != state["view"]:
            state["_last_view"] = state["view"]
            show_workbench(False)
        # The page you are on stays lit while you are on it.
        for key, row in destinations.items():
            row.classes(add="hub-nav-active") if key == state["view"] \
                else row.classes(remove="hub-nav-active")
        content.clear()
        with content:
            crumb()
            view = state["view"]
            if view == "overview":
                sections.overview(library, devices, discovery, go)
            elif view == "games":
                games.build(library.game_rows(), library.kinds_present(), show_game,
                            state, render)
            elif view == "collections":
                sections.collections(library)
            elif view == "media":
                sections.media(library, lambda gid: show_game({"id": gid}))
            elif view == "extensions":
                sections.extensions(devices)
            elif view == "settings":
                settings_page.build(state, render, go)
            elif view == "devices":
                if state["device"] is None:
                    devices_page.build_registry(devices, open_device)
                else:
                    ui.button("All devices", icon="arrow_back",
                              on_click=lambda: open_device(None)) \
                        .props("flat dense no-caps").classes("ml-2 mt-2")
                    devices_page.build_detail(state["device"], device_capabilities,
                                              discovery.get("install_id"),
                                              local_capabilities)
            else:
                _placeholder(view)

    def go(view: str) -> None:
        state["view"] = view
        render()

    await workbench.build(panel, workbench_title, library, None, state)
    render()


def _nav_item(key: str, label: str, icon: str, state: dict[str, Any], render,
              labels: list, rows: list, destinations: dict) -> None:
    def choose() -> None:
        state["view"] = key
        state["device"] = None
        render()

    row = ui.row().classes("items-center gap-3 cursor-pointer w-full hub-nav-row") \
        .on("click", choose)
    with row:
        ui.icon(icon, size="24px").classes("opacity-70")
        labels.append(ui.label(label).classes("hub-nav-item"))
    # The tooltip is what makes the collapsed rail usable at all, and it costs nothing
    # while expanded.
    row.tooltip(label)
    rows.append(row)
    destinations[key] = row


def _placeholder(view: str) -> None:
    with ui.column().classes("w-full items-center p-8 gap-2"):
        ui.icon("construction", size="32px").classes("opacity-40")
        ui.label(f"{view.title()} is not built yet").classes("text-sm opacity-60")


async def _look_for_new_tables() -> None:
    """Start a refresh and say so; watching it is the jobs affordance's job."""
    try:
        await run.io_bound(HubClient().refresh_library)
    except Exception as exc:
        # Already running is the ordinary case here, not a failure worth a trace.
        ui.notify(f"Could not start: {exc}", type="warning")
        return
    ui.notify("Looking for tables added or removed", type="positive")
