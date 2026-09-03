"""The Hub UI shell: nav, content and the workbench that follows the selection."""

from __future__ import annotations

import asyncio
from typing import Any

from nicegui import run, ui

from hubui import collections as collections_page
from hubui import deeplink, games, grid, sections, tageditor, theme, views, workbench
from hubui import devices as devices_page
from hubui import media as media_page
from hubui import settings as settings_page
from hubui.api import HubClient
from hubui.data import Library

# Both panel headers are pinned to this, so the two toggles sit at the same height
# whatever their labels do. Left to the text, one was 52px and the other 22px.
HEADER_H_PX = 52

# Wide enough for the longest label at the nested indent, with the scrollbar the
# rail now needs: "Collections" indented is the widest thing in here.
NAV_WIDE_PX = 252
WORKBENCH_WIDE_PX = 320
# What the panel needs to hold its three regions, not the smallest a pane can be.
# Below this the honest move is the rail, which is one click away.
WORKBENCH_MIN_PX = 320
# Past the work width, so the divider reaches every mode on its own and Full is the far
# end of one continuum rather than the only way in. Short of squeezing the list out -
# that is Full's job, and Full has a control that brings it back.
WORKBENCH_MAX_PX = 1000
# A collection is authored rather than swept: its rule and its result sit side by
# side, and the dock only splits two-column past 900px. Per subject, which is what
# section 5 says pane geometry should be - the width that suits a game grid does not
# suit this.
WORKBENCH_COLLECTION_PX = 900
# Below a desk-sized window the nav gives up its labels rather than its fifth of the
# screen. The rail already existed as a manual toggle and simply never fired on size;
# width drives that same state rather than adding a second way to collapse, so a toggle
# by hand still wins afterwards. Phone is not addressed - that needs a different shell,
# and the phone-shaped job has its own surface.
NAV_NARROW_PX = 1100
# One rail width for both panels - they collapse to the same thing.
RAIL_PX = 57

# Every entry is a place, not a thing. Jobs used to sit here and does not any more:
# it is transient, it belongs in the header where it is visible from every page, and a
# rail slot is too expensive for something that is empty most of the time. Logs moved
# under Settings > Diagnostics with the rest of the troubleshooting surface, and Gallery
# is gone - the media map in the details pane answers "what is missing here" and the
# Media section answers "what is missing anywhere", which is what it was reaching for.
# Grouped, because four of these are what the library holds and the rest are not.
# HUBUI section 16.1: a subject is a place, not transient state - so Tables and Tags are
# rail entries rather than a mode a dropdown puts the Games page into. `casino` is the
# asset registry's own icon for a table; the rail should not invent a second one.
# Library is a rail entry like the rest, with the four it holds nested under it - not a
# bare heading, which would be the one thing in this rail that is not a place. It is a
# disclosure rather than a destination: a row that both navigated and collapsed would
# make one click mean two things, and the children are the destinations.
NAV_PARENT = ("library", "Library", "inventory_2")

NAV_GROUPS: tuple[tuple[tuple[str, str, str] | None,
                        tuple[tuple[str, str, str], ...]], ...] = (
    (None, (("overview", "Overview", "space_dashboard"),)),
    # Media sits with the grains of the library it is one of, ahead of the two that
    # organize it rather than being part of it.
    (NAV_PARENT, (("games", "Games", "sports_esports"),
                  ("tables", "Tables", "casino"),
                  ("media", "Media", "perm_media"),
                  ("collections", "Collections", "collections_bookmark"),
                  ("tags", "Tags", "sell"))),
    (None, (("devices", "Devices", "devices"),
            ("extensions", "Extensions", "extension"),
            ("settings", "Settings", "tune"))),
)

NAV_ITEMS = tuple(item for _parent, items in NAV_GROUPS for item in items)

# What the header calls each destination. A section owns a subject too, but that is a
# fact about the data behind the page, not a caption for it - printing "one row is one
# collection" over a page of cards described something that was not on the screen.
SECTIONS = {
    "overview": "Overview",
    "games": "Games",
    "tables": "Tables",
    "tags": "Tags",
    "collections": "Collections",
    "media": "Media",
    "devices": "Devices",
    "extensions": "Extensions",
    "settings": "Settings",
}


# What the panel says when nothing is selected, per page. Named for what *that* page
# selects: three of them select something and the rest do not, and one asking for a game
# on a page with no games is the panel describing a different screen.
EMPTY_PANE = {
    "games": ("Game Details", "Select a game"),
    "tables": ("Table Details", "Select a table"),
    "collections": ("Collection", "Select a collection"),
    "media": ("Media", "Select a kind of media"),
}

# The pages the pane has a role on. Media is one of them: a row is one game's slot, so
# the panel opens on it the way it does for a game. Everywhere else it is hidden -
# `render` adds `hub-no-pane` - and the user's own open/closed and width are left alone,
# so coming back to a page that selects something restores what they arranged.
WORKBENCH_VIEWS = frozenset(EMPTY_PANE)


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


# The title is per page, not from ui.run: one process serves both this and the Manager
# UI, so an app-wide title puts the other surface's name in this one's tab.
@ui.page("/hub", title="VPinFE Hub")
async def hub_page(view: str = "", game: str = "", table: str = "", section: str = "",
                   slot: str = "", settings: str = "") -> None:
    """The hub. Query parameters say where in it, so a place can be linked to."""
    # The palette and Quasar's dark mode are two separate switches. The toggle button
    # that used to own the second one is gone, so it is set here - without it the shell
    # renders light while the tokens stay dark.
    ui.dark_mode(True)
    theme.apply_colors(dark=True)
    theme.apply_flair()
    grid.install_filters()
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
                             "collection": None}
    # Before anything is built, so the first render is the place asked for rather than
    # the front door followed by a jump.
    deeplink.apply(state, {"view": view, "game": game, "table": table,
                           "section": section, "slot": slot, "settings": settings},
                   views=[key for key, _label, _icon in NAV_ITEMS],
                   sections=[item.key for item in workbench.SECTIONS])

    labels: list[ui.label] = []
    destinations: dict[str, ui.row] = {}

    def set_mini(mini: bool) -> None:
        """Collapse the nav to an icon rail rather than hiding it.

        Hiding it entirely costs you the map; mini keeps every destination reachable
        and one click away, which is the point of a rail.
        """
        state["mini"] = mini
        left.props(add="mini") if mini else left.props(remove="mini")
        for label in labels:
            label.set_visibility(not mini)
        nav_icon.props(f'name={"menu" if mini else "menu_open"}')
        # Centring the rail's icons is the stylesheet's job, under .q-drawer--mini:
        # the padding that offsets them is !important, which no class here outranks.

    def on_window_width(width: int) -> None:
        if state.get("nav_collapsed_by_full"):
            return
        wants_rail = width < NAV_NARROW_PX
        if wants_rail != state["mini"] and wants_rail != state.get("nav_by_hand"):
            set_mini(wants_rail)

    ui.on("hub_window_px", lambda event: on_window_width(int(event.args or 0)))

    def toggle_mini() -> None:
        """The nav's own control. Setting it by hand takes it out of Full's care: an
        explicit choice outranks the one Full made on your behalf, so leaving Full
        will not undo it."""
        state.pop("nav_collapsed_by_full", None)
        # Remembered, so a width change does not undo what was just asked for by hand.
        state["nav_by_hand"] = not state["mini"]
        set_mini(not state["mini"])


    with ui.left_drawer(value=True).props(f"width={NAV_WIDE_PX} bordered") as left:
        # A nav header row carrying the collapse control - the shape 2.x already uses
        # (`manager-nav-header`). It is the panel's own chrome, so it costs nothing that
        # was not already the panel, and nothing floats over the grid.
        nav_header = ui.row() \
            .classes("items-center gap-3 w-full hub-nav-header")
        with nav_header:
            # The icon is the control, not the bar it sits in. A whole clickable header
            # collapses the panel when someone meant to click the name in it, and hangs
            # the tooltip off the middle of a wide row where it points at nothing.
            nav_icon = ui.icon("menu_open", size="24px") \
                .classes("opacity-70 shrink-0 cursor-pointer hub-panel-toggle") \
                .on("click", lambda: toggle_mini())
            nav_icon.tooltip("Show or hide the navigation")
            # Larger and heavier than a nav item, like HA's own title. Row height may
            # differ from the items below - that is fine and expected; what has to stay
            # aligned is the icon column, which does not depend on the label's size.
            labels.append(ui.label("VPinFE Hub")
                          .classes("whitespace-nowrap hub-nav-title"))
        for parent, items in NAV_GROUPS:
            held: list[ui.row] = []
            if parent is not None:
                _nav_parent(parent, state, labels, held)
            for key, label, icon in items:
                # redraw, not render: a destination whose rows are read on demand has
                # to read them before it draws, and arriving is when that is first true.
                _nav_item(key, label, icon, state, lambda: redraw(), labels,
                          destinations, nested=parent is not None, held=held)
            if parent is not None:
                # After the children exist: the caret leads `held`, and a group left
                # closed last time has to draw closed rather than open and then blink.
                _show_group(state[f"{parent[0]}_open"], held[0], held)
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


    splitter = ui.splitter(reverse=True, limits=(WORKBENCH_MIN_PX, WORKBENCH_MAX_PX),
                           value=WORKBENCH_WIDE_PX) \
        .props("unit=px").classes("w-full h-full")
    with splitter.after, ui.column().classes("w-full h-full gap-0 hub-workbench"):
        # The selected game's name shares the row with the toggle rather than sitting
        # under it - same class list, same height and same gutter as the nav's header,
        # so neither the icon's inset from the edge nor its height can drift.
        workbench_header = ui.row() \
            .classes("items-center gap-2 px-3 w-full justify-between "
                     "no-wrap hub-panel-header") \
            .style(f"min-height:{HEADER_H_PX}px")
        with workbench_header:
            # min-w-0 lets the column shrink below its content so the title truncates
            # instead of pushing the toggle onto a second line; shrink-0 keeps the
            # toggle at its own size while that happens.
            workbench_title = ui.column().classes("gap-0 min-w-0 overflow-hidden")
            with ui.row().classes("items-center gap-1 shrink-0 no-wrap"):
                # Their own row so they can go with the panel: at the rail there is
                # nothing to step through, and they do not fit beside a 57px header.
                workbench_actions = ui.row() \
                    .classes("items-center gap-1 shrink-0 no-wrap")
                with workbench_actions:
                    # Stepping the list from in here, so a sweep does not need the grid
                    # on screen - which is the point of Full.
                    ui.button(icon="keyboard_arrow_up", on_click=lambda: _step(-1)) \
                        .props("flat dense round size=sm").tooltip("Previous game")
                    ui.button(icon="keyboard_arrow_down", on_click=lambda: _step(1)) \
                        .props("flat dense round size=sm").tooltip("Next game")
                    full_icon = ui.button(icon="open_in_full",
                                          on_click=lambda: toggle_full()) \
                        .props("flat dense round size=sm") \
                        .tooltip("Give the workbench the whole window")
                # Outside that row: it is the only way back once the rest have gone.
                workbench_icon = ui.icon("menu_open", size="24px") \
                    .classes("opacity-70 shrink-0 cursor-pointer hub-panel-toggle") \
                    .on("click", lambda: show_workbench(not state["workbench"]))
                workbench_icon.tooltip("Show or hide the workbench")
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
        workbench_actions.set_visibility(shown)
        # A rail is panel the whole way down, with no window in it - the stylesheet
        # stops cutting the band to transparent, or the page grid shows through 57px.
        splitter.classes(remove="hub-rail") if shown \
            else splitter.classes(add="hub-rail")
        # justify-end, not justify-center: the header keeps its 18px right padding, and
        # centring inside a padded box put the icon 27px in. Held to the right, the
        # padding alone places it exactly where it sits when the panel is open.
        workbench_header.classes(add="justify-end", remove="justify-between") \
            if not shown else \
            workbench_header.classes(add="justify-between", remove="justify-end")


    with splitter.before:
        # 2.x's own 24px at the sides and bottom, which is what separates the content
        # from the two panels either side and lets the backdrop read as a backdrop.
        # None at the top: the header band starts there, and it is the thing that has
        # to line up with the other two panes' headers.
        content = ui.column().classes("w-full h-full gap-0 px-6 pb-6")

    def toggle_full() -> None:
        """The list never goes away - it steps back to the rail every panel here
        collapses to, and this control is what brings it forward again.

        The nav goes to its rail with it. Full means "give this the screen", and
        leaving the 220px gutter behind makes that two gestures instead of one - on a
        1100px window it is the difference between reaching the work width and not.
        Only the nav Full collapsed comes back, so a nav you had already put away
        stays away.
        """
        state["full"] = not state.get("full")
        splitter.classes(add="hub-full") if state["full"] \
            else splitter.classes(remove="hub-full")
        full_icon.props(f'icon={"close_fullscreen" if state["full"] else "open_in_full"}')
        if state["full"]:
            if not state["mini"]:
                state["nav_collapsed_by_full"] = True
                set_mini(True)
            if not state["workbench"]:
                show_workbench(True)
        elif state.pop("nav_collapsed_by_full", None):
            set_mini(False)

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

    def remember_width(event: Any) -> None:
        """Keep the width a drag settled on. Quasar only reports it on release, which
        is exactly when it is worth keeping."""
        try:
            value = float(event.value or 0)
        except (TypeError, ValueError):
            return
        if value > RAIL_PX:
            state["workbench_px"] = value

    splitter.on_value_change(remember_width)

    async def show_game(row: dict | None) -> None:
        """What the grid has selected is what the workbench is about.

        Both grids land here, and which one you are on decides what a row means: under
        Games a row is a folder, under Tables it is one file inside one. There is no
        control to keep in step - the place you are in is the answer, which is what
        section 16.1 bought by making a subject a rail entry rather than a dropdown.
        """
        # A selection is the only thing that opens the pane. Arriving at a section does
        # not, because there is nothing selected yet to be about.
        if row and not state["workbench"]:
            show_workbench(True)
        by_table = state["view"] == "tables"
        state["game"] = (row or {}).get("game_id" if by_table else "id")
        state["table"] = (row or {}).get("id") if by_table else ""
        await workbench.build(panel, workbench_title, library, state["game"], state,
                              state["table"])
        deeplink.sync(state)

    async def show_slot(row: dict | None) -> None:
        """A media row is one slot of one game, so the panel opens on that slot.

        The row says which lens it belongs to - a shared file has no table, a file
        named for one carries it - so this needs no control and cannot disagree with
        the grid. The same landing the Games grid uses for a media cell.
        """
        if row and not state["workbench"]:
            show_workbench(True)
        state["game"] = (row or {}).get("game_id")
        state["table"] = (row or {}).get("table") or ""
        if row:
            state["section"] = "media"
            state.setdefault("slot", {"kind": None})["kind"] = row.get("kind")
        await workbench.build(panel, workbench_title, library, state["game"], state,
                              state["table"])
        deeplink.sync(state)

    async def show_collection(row: dict | None) -> None:
        """What the grid has selected is what the workbench is about - the same rule
        Games follows, so the panel never needs a control of its own."""
        if row and not state["workbench"]:
            show_workbench(True)
        if row and not state.get("collection_width_set"):
            # Once, on the first selection. Widening on every one would fight a drag.
            state["collection_width_set"] = True
            splitter.set_value(max(splitter.value or 0, WORKBENCH_COLLECTION_PX))
        state["collection"] = (row or {}).get("id")
        await workbench.build_collection(panel, workbench_title, library,
                                         state["collection"], state)

    def open_device(device) -> None:
        state["view"] = "devices"
        state["device"] = device
        render()
        deeplink.sync(state)

    def clear_workbench() -> None:
        """Empty the pane. Sync, so render() can call it without awaiting a rebuild."""
        workbench_title.clear()
        panel.clear()
        # The same two-line shape a selected game gets, so the header does not change
        # height or alignment as the selection comes and goes.
        heading, prompt = EMPTY_PANE.get(state["view"], ("Game Details", "Select a game"))
        with workbench_title:
            ui.label(heading) \
                .classes("text-base hub-workbench-title leading-tight truncate")
            ui.label(prompt).classes("text-xs hub-workbench-label leading-none truncate")

    def page_header() -> None:
        """The page's name, and the actions that belong to the page rather than a row.

        The name and nothing else - the selection is named in the workbench header,
        which is the pane that is about it. Here rather than in an app header because
        each pane already owns its chrome, and a fourth band would cost height on every
        page for one line.
        """
        title = SECTIONS.get(state["view"], state["view"].title())
        # The band the other two panes' headers use, so the page name sits in a fixed
        # rhythm rather than at whatever height its text makes. Not aligned *across*
        # panes - the nav's band is taller than its minimum and starts inside its own
        # padding, and matching that would be a magic number against an accident.
        # The title carries the buttons' 32px line height so the band centres one
        # height: centring boxes of different heights aligns boxes, not baselines.
        with ui.row().classes("items-center gap-2 w-full no-wrap") \
                .style(f"min-height:{HEADER_H_PX}px"):
            ui.label(title).classes("grow min-w-0 truncate hub-page-title")
            ui.button("Look for new tables", icon="refresh",
                      on_click=_look_for_new_tables) \
                .props("flat dense no-caps size=sm").classes("shrink-0 hub-action") \
                .tooltip("Re-read the game folders and pick up anything added or removed")
            # Jobs is a header affordance, always visible, never a destination. Empty is
            # the normal state and it says so rather than showing a zero.
            ui.button("No active jobs", icon="pending_actions") \
                .props("flat dense no-caps size=sm").classes("shrink-0 opacity-70")

    def render() -> None:
        # A game shown beside a different destination is stale by definition.
        clear_workbench()
        # The pane is not closed with it. It was, on the grounds that one left open
        # describes nothing - but it has an empty state now, and `clear_workbench`
        # names it for whichever page you have arrived at. Its width and whether it is
        # open are how the workspace is arranged, and rearranging it on every move
        # between sections is the shell taking a decision back.
        #
        # On a page with no subject it goes entirely, rail included. Nothing there can
        # fill it, so the strip would be a control that reopens an empty panel.
        splitter.classes(remove="hub-no-pane") if state["view"] in WORKBENCH_VIEWS \
            else splitter.classes(add="hub-no-pane")
        # The page you are on stays lit while you are on it.
        for key, row in destinations.items():
            row.classes(add="hub-nav-active") if key == state["view"] \
                else row.classes(remove="hub-nav-active")
        content.clear()
        with content:
            page_header()
            view = state["view"]
            if view == "overview":
                sections.overview(library, devices, discovery, go)
            elif view == "games":
                games.build(library.game_rows(), library.kinds_present(), library,
                            show_game, state, redraw)
            elif view == "tables":
                games.build_tables(library.table_rows(), library, show_game, state,
                                   redraw)
            elif view == "tags":
                tageditor.build(library.tag_rows(), library, redraw)
            elif view == "collections":
                collections_page.build(library.collections(), library, show_collection,
                                       state, redraw)
            elif view == "media":
                media_page.build(library.media_rows(), library, show_slot, state,
                                 redraw)
            elif view == "extensions":
                sections.extensions(devices)
            elif view == "settings":
                settings_page.build(state, render, go, library)
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

    def redraw() -> None:
        """Render, first reading anything the new subject needs.

        The by-file lens is a second walk of every folder, so it is read when somebody
        asks for it rather than at startup - and off the loop, because render() runs on
        it and the client refuses an HTTP call there.
        """
        if state["view"] == "tables" and not library.has_table_rows():
            async def read_then_draw() -> None:
                await run.io_bound(library.load_tables)
                render()
            asyncio.create_task(read_then_draw())
            return
        if state["view"] == "collections" and not library.has_collections():
            async def read_collections_then_draw() -> None:
                await run.io_bound(library.load_collections)
                render()
            asyncio.create_task(read_collections_then_draw())
            return
        if state["view"] == "media" and not library.has_media_rows():
            async def read_media_then_draw() -> None:
                await run.io_bound(library.load_media_rows)
                render()
            asyncio.create_task(read_media_then_draw())
            return
        render()

    # Reported once on load and on every settle after a resize. Debounced, because a
    # drag fires this continuously and each one is a round trip.
    ui.run_javascript("""
    (() => {
      let t = null;
      const say = () => emitEvent('hub_window_px', window.innerWidth);
      window.addEventListener('resize', () => {
        clearTimeout(t);
        t = setTimeout(say, 150);
      });
      say();
    })()
    """)

    # A tooltip on the control that opened a menu sits on top of it. Watched once here
    # rather than wired per menu: menus portal into the body, so one observer sees them
    # all, and the alternative is remembering this on every menu ever added.
    ui.run_javascript("""
    (() => {
      const open = () => document.querySelector('.q-menu') !== null;
      const say = () => document.body.classList.toggle('hub-menu-open', open());
      new MutationObserver(say).observe(document.body, {childList: true});
      say();
    })()
    """)

    # The saved views, read before anything draws: a grid asks for them while it is
    # being built, which is on the loop, and the client refuses an HTTP call there.
    await run.io_bound(library.warm, games.SCOPE + views.VIEWS_SUFFIX,
                       f"{games.SCOPE}.tables" + views.VIEWS_SUFFIX)

    def go(view: str) -> None:
        state["view"] = view
        # redraw, not render: a destination whose data is read on demand has to read it
        # before it draws, and arriving is exactly when that is first true.
        redraw()
        deeplink.sync(state)

    # An address naming a game means the pane it opens, not just the section. Restored
    # after the shell exists, because that is what show_game builds into - and through
    # show_game rather than around it, so a link lands on exactly the state a click
    # would have produced.
    landing = (state.get("game")
               if state["view"] in ("games", "tables") else None)
    # An address that names a section has to read what that section needs, because the
    # first draw goes straight to render() and only redraw() reads on the way in. Both
    # of these drew empty from a link and filled in on the next click.
    if state["view"] == "tables":
        await run.io_bound(library.load_tables)
    if state["view"] == "collections":
        await run.io_bound(library.load_collections)
    if state["view"] == "media":
        await run.io_bound(library.load_media_rows)
    await workbench.build(panel, workbench_title, library, None, state)
    render()
    if landing:
        # Shaped as the lens in play expects it, so the one handler reads it the same
        # way whether it came from a click or from the address bar.
        await show_game({"game_id": landing, "id": state.get("table") or landing}
                        if state["view"] == "tables" else {"id": landing})


def _nav_parent(parent: tuple[str, str, str], state: dict[str, Any],
                labels: list, held: list) -> None:
    """The row a group of entries sits under, which opens and closes them.

    A disclosure, not a place: it has no page of its own, so a click that navigated
    would have to pick one of its children and the caret would then mean something
    different from the row it sits on.
    """
    key, label, icon = parent
    state.setdefault(f"{key}_open", True)

    def toggle() -> None:
        state[f"{key}_open"] = not state[f"{key}_open"]
        _show_group(state[f"{key}_open"], caret, held)

    row = ui.row().classes("items-center gap-3 cursor-pointer w-full no-wrap "
                           "hub-nav-row").on("click", toggle)
    with row:
        ui.icon(icon, size="24px").classes("opacity-70 shrink-0")
        labels.append(ui.label(label).classes("hub-nav-item whitespace-nowrap"))
        ui.space()
        caret = ui.icon("expand_more", size="20px").classes("opacity-60 shrink-0")
        labels.append(caret)
    row.tooltip(label)
    # Applied after the children exist, from the shell that owns the loop.
    held.append(caret)


def _show_group(open_now: bool, caret: Any, held: list) -> None:
    """Rows in, caret with them. The caret joins `labels` so it goes when the rail
    collapses to icons - there is nothing to disclose in a column of glyphs."""
    caret.props(f'name={"expand_more" if open_now else "chevron_right"}')
    for row in held:
        if row is not caret:
            row.set_visibility(open_now)


def _nav_item(key: str, label: str, icon: str, state: dict[str, Any], render,
              labels: list, destinations: dict, nested: bool = False,
              held: list | None = None) -> None:
    def choose() -> None:
        state["view"] = key
        state["device"] = None
        render()
        deeplink.sync(state)

    row = ui.row().classes("items-center gap-3 cursor-pointer w-full no-wrap "
                           "hub-nav-row" + (" hub-nav-row--nested" if nested else "")) \
        .on("click", choose)
    with row:
        ui.icon(icon, size="24px").classes("opacity-70 shrink-0")
        # `no-wrap` on the row and nowrap on the label. A rail entry is one line by
        # definition, and the rail scrolls once there are enough of them - which takes a
        # scrollbar's width off every row and was enough to break "Collections" in two.
        labels.append(ui.label(label)
                      .classes("hub-nav-item whitespace-nowrap"))
    # The tooltip is what makes the collapsed rail usable at all, and it costs nothing
    # while expanded.
    row.tooltip(label)
    destinations[key] = row
    if held is not None and nested:
        held.append(row)


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
