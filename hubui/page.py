"""The Hub UI shell: nav, content and the panel that follows the selection."""

from __future__ import annotations

from typing import Any

from nicegui import run, ui

from hubui import games, inspector, players, theme
from hubui.api import HubClient
from hubui.data import Library

# Both panel headers are pinned to this, so the two toggles sit at the same height
# whatever their labels do. Left to the text, one was 52px and the other 22px.
HEADER_H_PX = 52

NAV_WIDE_PX = 220
DETAILS_WIDE_PX = 320
DETAILS_MIN_PX = 260
DETAILS_MAX_PX = 760
# One rail width for both panels - they collapse to the same thing.
RAIL_PX = 57

NAV_ITEMS = (
    ("games", "Games", "sports_esports"),
    ("collections", "Collections", "collections_bookmark"),
    ("jobs", "Jobs", "pending_actions"),
    ("players", "Players", "devices"),
    ("extensions", "Extensions", "extension"),
    ("settings", "Settings", "tune"),
    ("logs", "Logs", "article"),
)


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
        "roster": client.players(),
        "player_capabilities": [entry["name"] for entry in capabilities
                                if "player" in (entry.get("residency") or [])],
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
    roster = loaded["roster"]
    player_capabilities = loaded["player_capabilities"]
    local_capabilities = loaded["local_capabilities"]

    state: dict[str, Any] = {"view": "games", "player": None,
                             "mini": False, "details": True}

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


    splitter = ui.splitter(reverse=True, limits=(DETAILS_MIN_PX, DETAILS_MAX_PX),
                           value=DETAILS_WIDE_PX) \
        .props("unit=px").classes("w-full h-full")
    with splitter.after, ui.column().classes("w-full h-full gap-0 hub-details"):
        # The selected game's name shares the row with the toggle rather than sitting
        # under it - same class list, same height and same gutter as the nav's header,
        # so neither the icon's inset from the edge nor its height can drift.
        details_header = ui.row() \
            .classes("items-center gap-2 px-3 cursor-pointer w-full justify-between "
                     "no-wrap hub-panel-header") \
            .style(f"min-height:{HEADER_H_PX}px") \
            .on("click", lambda: show_details(not state["details"]))
        with details_header:
            # min-w-0 lets the column shrink below its content so the title truncates
            # instead of pushing the toggle onto a second line; shrink-0 keeps the
            # toggle at its own size while that happens.
            details_title = ui.column().classes("gap-0 min-w-0 overflow-hidden")
            details_icon = ui.icon("menu_open", size="24px").classes("opacity-70 shrink-0")
        details_header.tooltip("Show or hide details")
        # grow + min-h-0 is what lets a flex child scroll instead of pushing its
        # parent taller: without min-h-0 the panel grows to fit and the pane overflows.
        panel = ui.column().classes("w-full gap-0 grow min-h-0 overflow-auto "
                                    "hub-detail-body")


    def show_details(shown: bool) -> None:
        """Collapse to a rail, never away.

        Hiding it outright left no control to bring it back, which is the only reason
        the floating tab existed. A rail keeps its own toggle on screen, so both panels
        collapse the same way and nothing overlays the grid.
        """
        state["details"] = shown
        details_icon.props(f'name={"menu_open" if shown else "menu"}')
        # The floor moves with the state. Held at DETAILS_MIN_PX the pane cannot be
        # dragged down to a useless sliver while it is open, and the rail is below that
        # floor - so collapsing has to lower it first or Quasar clamps the value back.
        splitter._props["limits"] = [RAIL_PX if not shown else DETAILS_MIN_PX,
                                     DETAILS_MAX_PX]
        splitter.update()
        splitter.set_value(DETAILS_WIDE_PX if shown else RAIL_PX)
        panel.set_visibility(shown)
        details_title.set_visibility(shown)
        # justify-end, not justify-center: the header keeps its 18px right padding, and
        # centring inside a padded box put the icon 27px in. Held to the right, the
        # padding alone places it exactly where it sits when the panel is open.
        details_header.classes(add="justify-end", remove="justify-between") \
            if not shown else \
            details_header.classes(add="justify-between", remove="justify-end")


    with splitter.before:
        # 2.x's own 24px. It is dead space by the numbers, but it is what separates the
        # content from the two panels either side and lets the backdrop read as a
        # backdrop rather than a hairline.
        content = ui.column().classes("w-full h-full gap-0 p-6")

    async def show_game(row: dict | None) -> None:
        await inspector.build(panel, details_title, library, (row or {}).get("id"))

    def open_player(player) -> None:
        state["view"] = "players"
        state["player"] = player
        render()

    def clear_details() -> None:
        """Empty the pane. Sync, so render() can call it without awaiting a rebuild."""
        details_title.clear()
        panel.clear()
        # The same two-line shape a selected game gets, so the header does not change
        # height or alignment as the selection comes and goes.
        with details_title:
            ui.label("Game Details") \
                .classes("text-base hub-detail-title leading-tight truncate")
            ui.label("Select a game").classes("text-xs hub-detail-label leading-none truncate")

    def render() -> None:
        # A game shown beside a different destination is stale by definition.
        clear_details()
        # The page you are on stays lit while you are on it.
        for key, row in destinations.items():
            row.classes(add="hub-nav-active") if key == state["view"] \
                else row.classes(remove="hub-nav-active")
        content.clear()
        with content:
            view = state["view"]
            if view == "games":
                games.build(library.game_rows(), library.kinds_present(), show_game)
            elif view == "players":
                if state["player"] is None:
                    players.build_roster(roster, open_player)
                else:
                    ui.button("All players", icon="arrow_back",
                              on_click=lambda: open_player(None)) \
                        .props("flat dense no-caps").classes("ml-2 mt-2")
                    players.build_detail(state["player"], player_capabilities,
                                         discovery.get("install_id"), local_capabilities)
            else:
                _placeholder(view)

    await inspector.build(panel, details_title, library, None)
    render()


def _nav_item(key: str, label: str, icon: str, state: dict[str, Any], render,
              labels: list, rows: list, destinations: dict) -> None:
    def choose() -> None:
        state["view"] = key
        state["player"] = None
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
