"""The panel that follows the selection.

Sections are declared, grouped by what they belong to, and remember which of them are
open. That last part is what makes stepping down a list a comparison rather than a run
of unrelated screens: the panel is rebuilt for every selection, so without a record the
shape you arranged is gone on the next arrow key.

The grouping is the answer to how a game and its tables sit together. Not a toggle
between them - which things are whose. A section under "This table" follows the lens
above it; the rest are the game's whatever build you are looking at.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from nicegui import run, ui

from hubui import mediamap
from hubui.data import Library

# Which group a section belongs to, in the order they are shown.
OWNERS = (("game", "This game"), ("table", "This table"), ("folder", "Whole folder"))

# Sections open when nobody has said otherwise. The map is the question people
# actually have about a game, and its shape answers before a label is read.
DEFAULT_OPEN = frozenset({"media"})

# Below this the outline costs more than it gives: 132px of it against a 320px
# workbench leaves the map too narrow to read, and the section headers are already
# a list of what is here. It earns its place once there is room for both.
#
# Enforced in CSS by a container query, not here. Quasar resizes the pane live while
# you drag and only tells the server on release, so a server-side threshold changed
# the layout a beat after you let go - which is exactly when you can no longer see
# what you were aiming at.
OUTLINE_FROM_PX = 520


@dataclass(frozen=True)
class Section:
    """One block in the panel: what it is called, whose it is, and how to draw it.

    `name` is the fixed word the outline shows; `label` takes the game's context
    because a heading that counts something has to count this game's. `build` is
    async because a section may need a fetch.
    """

    key: str
    owner: str
    name: str
    label: Callable[[dict[str, Any]], str]
    build: Callable[[dict[str, Any]], Any]


def open_sections(state: dict[str, Any]) -> set[str]:
    """The set this client has open, seeded once from the defaults."""
    if "open_sections" not in state:
        state["open_sections"] = set(DEFAULT_OPEN)
    return state["open_sections"]


async def build(container: ui.column, title: ui.column, library: Library,
                game_id: str | None, state: dict[str, Any] | None = None) -> None:
    """Fill the panel, and the name that lives up in the panel's header row."""
    state = state if state is not None else {}
    container.clear()
    title.clear()
    with container:
        if game_id is None:
            _title(title, "Game Details", "Select a game")
            return
        game = next((entry for entry in library.games if entry["id"] == game_id), None)
        if game is None:
            _title(title, "Game Details", "Not in this library")
            return
        _title(title, game.get("name") or "",
               f"{game.get('manufacturer') or '?'} {game.get('year') or ''}")

        # Off the loop, always. This is an HTTP call to our own process: made on the
        # event loop it blocks the server from answering it, the request times out
        # after 15s, and the browser reports the socket as lost rather than slow.
        tables = await run.io_bound(library.tables_for, game_id)
        context = {"library": library, "game": game, "game_id": game_id,
                   "tables": tables, "state": state}

        opened = open_sections(state)
        entries: dict[str, ui.element] = {}
        # The outline must not scroll with what it points at, so the row is the fixed
        # frame and only the body column scrolls inside it.
        with ui.row().classes("w-full grow min-h-0 no-wrap gap-0"):
            _outline(entries, opened)
            body = ui.column().classes("grow min-w-0 h-full overflow-auto gap-0 "
                                       "hub-workbench-body")
        with body:
            for owner, heading in OWNERS:
                mine = [section for section in SECTIONS if section.owner == owner]
                if not mine:
                    continue
                ui.label(heading).classes("hub-group")
                for section in mine:
                    await _section(section, context, opened, entries)


def _outline(entries: dict[str, ui.element], opened: set[str]) -> None:
    """A table of contents, not a selector.

    Clicking scrolls to a section and opens it rather than replacing what is shown -
    which is what lets a left-hand nav and several-sections-open coexist. A selector
    could only ever show one, and comparing across games needs more than one.
    """
    with ui.column().classes("shrink-0 h-full overflow-auto gap-0 pr-1 hub-outline") \
            .style("width:132px"):
        for owner, heading in OWNERS:
            mine = [section for section in SECTIONS if section.owner == owner]
            if not mine:
                continue
            ui.label(heading).classes("hub-group")
            for section in mine:
                item = ui.label(section.name).classes("hub-outline-item")
                if section.key in opened:
                    item.classes(add="hub-outline-on")
                item.on("click", lambda key=section.key: _reveal(key))
                entries[section.key] = item


def _reveal(key: str) -> None:
    """Scroll a section into view. Opening it is the expansion's own doing."""
    ui.run_javascript(
        f"document.getElementById('wb-{key}')"
        "?.scrollIntoView({behavior:'smooth', block:'start'})")


async def _section(section: Section, context: dict[str, Any], opened: set[str],
                   entries: dict[str, ui.element]) -> None:
    def remember(event: Any, key: str = section.key) -> None:
        opened.add(key) if event.value else opened.discard(key)
        # The outline reflects the sections; it does not drive them. Whichever way a
        # section was toggled, both places have to agree afterwards.
        item = entries.get(key)
        if item is not None:
            item.classes(add="hub-outline-on") if event.value \
                else item.classes(remove="hub-outline-on")

    with ui.expansion(section.label(context), value=section.key in opened,
                      on_value_change=remember).classes("w-full") \
            .props(f"id=wb-{section.key}"), \
            ui.column().classes("w-full gap-0"):
        await section.build(context)


def _title(target: ui.column, name: str, subtitle: str) -> None:
    with target:
        ui.label(name).classes("text-base hub-workbench-title leading-tight truncate")
        ui.label(subtitle).classes("text-xs hub-workbench-label leading-none truncate")


def _prefix(game_id: str, table_id: str) -> str:
    return (f"/api/v1/games/{game_id}/tables/{table_id}/media" if table_id
            else f"/api/v1/games/{game_id}/media")


def _media_label(context: dict[str, Any]) -> str:
    present, borrowed, total = mediamap.summary(
        context["library"].media.get(context["game_id"], {}))
    label = f"Media ({present}/{total}"
    return label + (f", {borrowed} borrowed)" if borrowed else ")")


async def _media_block(context: dict[str, Any]) -> None:
    """The map, and - only where a folder holds more than one build - a lens over it.

    One table means one answer, so the control never appears and nobody meets the
    concept. That is the common case by a long way.
    """
    library, game_id = context["library"], context["game_id"]
    tables = context["tables"]
    chosen = {"table": ""}
    note = ui.label().classes("hub-help px-2")
    holder = ui.column().classes("w-full gap-0")

    async def draw() -> None:
        table_id = chosen["table"]
        entries = await run.io_bound(library.media_for, game_id, table_id or None)
        note.text = ("Named for this .vpx. Only this table uses them."
                     if table_id else
                     "Named for the folder. Every table in this game uses them.")
        holder.clear()
        with holder:
            mediamap.build(entries, _prefix(game_id, table_id))

    async def pick(event: Any) -> None:
        chosen["table"] = event.value or ""
        await draw()

    if len(tables) > 1:
        options = {"": "Shared"}
        options.update({table["id"]: table.get("filename") or table["id"]
                        for table in tables if table.get("id")})
        ui.select(options, value="", label="Viewing as", on_change=pick) \
            .props("dense outlined").classes("w-full px-2 pt-1")
    else:
        note.set_visibility(False)
    await draw()


async def _identity_block(context: dict[str, Any]) -> None:
    game = context["game"]
    _rows(ui, {
        "VPS id": game.get("vps_id") or "-",
        "ROM": game.get("rom") or "-",
        "Type": game.get("type") or "-",
        "Themes": ", ".join(game.get("themes") or []) or "-",
    })


def _tables_label(context: dict[str, Any]) -> str:
    tables = context["tables"]
    gone = [table for table in tables if table.get("absent_since")]
    label = f"Tables ({len(tables)})"
    return label + (f" - {len(gone)} not on disk" if gone else "")


async def _tables_block(context: dict[str, Any]) -> None:
    for table in context["tables"]:
        with ui.row().classes("items-center gap-2 w-full px-3"):
            name = ui.label(table.get("filename") or "").classes("text-xs truncate")
            since = str(table.get("absent_since") or "")
            if since:
                # Stated, not judged: how long it has been gone is what tells a deletion
                # from a share that was late mounting, and that call is the user's.
                name.classes(add="opacity-60")
                ui.badge(f"gone since {since[:10]}", color="warning").props("outline")
            else:
                ui.badge(table.get("app") or "?", color="secondary").props("outline")


def _rows(target: Any, values: dict[str, str]) -> None:
    for label, value in values.items():
        with target.row().classes("items-center gap-2 w-full px-3 py-0"):
            target.label(label).classes("text-xs opacity-60 w-20")
            target.label(str(value)).classes("text-xs truncate")


SECTIONS: tuple[Section, ...] = (
    Section("identity", "game", "Identity", lambda _: "Identity", _identity_block),
    Section("media", "table", "Media", _media_label, _media_block),
    Section("tables", "folder", "Tables", _tables_label, _tables_block),
)
