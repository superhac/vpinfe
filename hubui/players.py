"""Players: what each one is, and what it can be asked to do."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from nicegui import ui

# What a kind of player can do when nobody can ask it. A vpx_mobile device runs VPX and
# not VPinFE, so it declares nothing, ever - the hub knows its abilities from the kind.
IMPLIED_BY_KIND: dict[str, set[str]] = {
    "vpx_mobile": {"launch"},
}

PRESENT, ABSENT, UNKNOWN = "present", "absent", "unknown"

_BADGE = {
    PRESENT: ("positive", "check_circle", "Available"),
    ABSENT: ("grey", "remove_circle_outline", "Not offered"),
    UNKNOWN: ("warning", "help_outline", "Cannot be determined"),
}


def capability_state(player: dict[str, Any], capability: str,
                     local_install_id: str | None,
                     local_capabilities: set[str]) -> str:
    """One of three answers, never two.

    "Cannot be determined" is its own state on purpose. Collapsing it into "not offered"
    tells someone their hardware lacks a feature when the truth is that nothing has
    asked it - which is a worse error than saying nothing.
    """
    kind = player.get("kind", "vpinfe")
    if kind in IMPLIED_BY_KIND:
        return PRESENT if capability in IMPLIED_BY_KIND[kind] else ABSENT
    if player.get("install_id") == local_install_id:
        return PRESENT if capability in local_capabilities else ABSENT
    # A remote VPinFE player declares its own capabilities, and the hub has no route to
    # ask it: httpapi/players.py records what a player said about itself and nothing more.
    return UNKNOWN


def build_detail(player: dict[str, Any], player_capabilities: list[str],
          local_install_id: str | None, local_capabilities: set[str]) -> None:
    with ui.column().classes("w-full p-4 gap-3"):
        with ui.row().classes("items-center gap-3"):
            ui.icon("sports_esports", size="28px").classes("text-primary")
            with ui.column().classes("gap-0"):
                ui.label(player.get("display_name") or "Player").classes("text-lg")
                ui.label(f"{player.get('kind', 'vpinfe')} · {player.get('address') or '-'}") \
                    .classes("text-xs opacity-70")

        ui.separator()
        ui.label("Capabilities").classes("text-sm opacity-70")
        with ui.column().classes("w-full gap-1"):
            for capability in player_capabilities:
                state = capability_state(player, capability, local_install_id,
                                         local_capabilities)
                colour, icon, label = _BADGE[state]
                with ui.row().classes("items-center gap-2 w-full"):
                    ui.icon(icon).classes(f"text-{colour}")
                    ui.label(capability.replace("_", " ")).classes("w-40")
                    ui.badge(label, color=colour).props("outline")


def build_roster(roster: list[dict[str, Any]],
                 on_open: Callable[[dict[str, Any]], None]) -> None:
    """The players this hub knows, as a page rather than as nav entries.

    One entry per player in the nav read fine with one player and would not with ten -
    and a roster accumulates entries for installs that never come back, so its length
    is not something the nav can be sized for.
    """
    with ui.column().classes("w-full p-4 gap-2"):
        ui.label(f"{len(roster)} player(s)").classes("text-xs opacity-60")
        for player in roster:
            with ui.card().classes("w-full cursor-pointer").on("click",
                                                               lambda p=player: on_open(p)):
                with ui.row().classes("items-center gap-3 w-full"):
                    ui.icon("sports_esports" if player.get("kind") == "vpinfe"
                            else "tablet_android", size="22px").classes("text-primary")
                    with ui.column().classes("gap-0"):
                        ui.label(player.get("display_name") or "player").classes("text-sm")
                        ui.label(f"{player.get('kind', 'vpinfe')} \u00b7 "
                                 f"{player.get('address') or '-'}").classes("text-xs opacity-60")
                    ui.space()
                    ui.icon("chevron_right").classes("opacity-40")
