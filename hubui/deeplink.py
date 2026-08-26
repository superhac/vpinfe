"""The address bar as the record of where you are.

So a place can be linked to, and so a reload lands where you were - which matters
because a reload is not always something you chose: a hub restart takes every open
page with it.

replaceState, not pushState: picking a different game is not navigation, and a back
button that steps through every row somebody arrowed past is worse than one that
leaves the section. The vocabularies of what is valid are passed in rather than
imported, which is what keeps this out of a cycle with the page it serves.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from typing import Any
from urllib.parse import urlencode

from nicegui import ui

# What the address carries, and where each comes from. Ordered, so the same place
# always produces the same address and two of them can be compared by eye.
_FIELDS = (
    ("view", lambda state: state.get("view") or ""),
    ("game", lambda state: state.get("game") or ""),
    ("table", lambda state: state.get("table") or ""),
    # "none" rather than nothing: every section closed is somewhere you asked to be,
    # and leaving it out of the address would reopen one on the next reload.
    ("section", lambda state: _section(state)),
    ("slot", lambda state: _slot_kind(state)),
    ("settings", lambda state: state.get("settings_page") or ""),
)

# Only where they mean something. A slot on the devices page is noise in an address
# somebody is meant to be able to read.
_ONLY_ON = {"game": "games", "table": "games", "section": "games", "slot": "games",
            "settings": "settings"}


# What the address calls a panel with nothing open.
NO_SECTION = "none"


def _section(state: dict[str, Any]) -> str:
    chosen = state.get("section")
    return NO_SECTION if chosen == "" else str(chosen or "")


def _slot_kind(state: dict[str, Any]) -> str:
    """The picked media kind, or "". Tolerant, because keeping the address current
    must never be the thing that takes the page down."""
    slot = state.get("slot")
    return str(slot.get("kind") or "") if isinstance(slot, dict) else ""


def query(state: dict[str, Any]) -> str:
    """The address for this state, without the path."""
    view = state.get("view") or ""
    return urlencode([(name, read(state)) for name, read in _FIELDS
                      if _ONLY_ON.get(name, view) == view and read(state)])


def sync(state: dict[str, Any]) -> None:
    """Put the current place in the address bar, without reloading anything."""
    tail = query(state)
    ui.run_javascript(
        f"history.replaceState(null, '', {json.dumps('/hub?' + tail if tail else '/hub')})")


def apply(state: dict[str, Any], params: dict[str, str], *,
          views: Iterable[str], sections: Iterable[str]) -> None:
    """Seed the state from an address somebody arrived on.

    Only what is recognised: a link can be old or hand-typed, and neither should be an
    error - what does not fit is dropped and the default stands. A game id is taken as
    given, because whether it exists is the library's question.
    """
    def clean(name: str) -> str:
        return str(params.get(name) or "").strip().lower()

    if clean("view") in set(views):
        state["view"] = clean("view")
    if str(params.get("game") or "").strip():
        state["game"] = str(params["game"]).strip()
    if str(params.get("table") or "").strip():
        state["table"] = str(params["table"]).strip()
        state["subject"] = "table"
    # Every rail's keys, not one rail's: an address can name a table section while the
    # subject is still being worked out, and dropping it here would land on the default
    # and quietly ignore half the link.
    if clean("section") == NO_SECTION:
        state["section"] = ""
    elif clean("section") in set(sections):
        state["section"] = clean("section")
    if clean("slot"):
        state.setdefault("slot", {"kind": None})
        state["slot"]["kind"] = clean("slot")
    if clean("settings"):
        state["settings_page"] = clean("settings")
