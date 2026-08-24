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

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from nicegui import run, ui

from hubui import mediamap
from hubui.data import Library

# Which group a section belongs to, in the order they are shown.
# Short, because the outline and the body would otherwise say the same three phrases
# twice on one screen. What each group means is carried by the lens sitting in it and
# by the sections themselves, not by shouting the scope.
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

# Past this the workbench is for working rather than comparing, and the two want
# opposite things: comparing wants several sections open and held still while the
# selection moves, working wants one of them with the window to itself. So the outline
# is a table of contents below this width and a selector above it - one control, doing
# the job the width is for. Reported by the browser, since only it knows the width.
WORK_FROM_PX = 900


@dataclass(frozen=True)
class Section:
    """One block in the panel: what it is called and how to draw it.

    `name` is the fixed word the outline shows; `label` takes the game's context
    because a heading that counts something has to count this game's - and, for the
    one section a lens governs, say which build it is counting. `build` is async
    because a section may need a fetch.
    """

    key: str
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
    # Builds are serialised, and a superseded one gives up rather than drawing.
    # Without this the panel doubles: clearing happens before the tables fetch and the
    # drawing after it, so two builds that overlap both clear an empty container and
    # then both append. A drag can start three - the divider, the mode it settles, and
    # the window listener - so this is the ordinary case, not the rare one.
    lock: asyncio.Lock = state.setdefault("build_lock", asyncio.Lock())
    state["build_seq"] = mine = state.get("build_seq", 0) + 1
    async with lock:
        if state["build_seq"] != mine:
            return
        await _draw(container, title, library, game_id, state)


async def _draw(container: ui.column, title: ui.column, library: Library,
                game_id: str | None, state: dict[str, Any]) -> None:
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
        # `lens` is a table id or "" for the folder's shared files, and it resets per
        # game because a table id means nothing to the next one. `redraws` is how the
        # lens reaches the sections that follow it without rebuilding the panel.
        # The picked slot lives with the client, not this build of the panel: a mode
        # change rebuilds and would otherwise forget it. Kept across games too, which
        # is what sweeping one kind down a list needs.
        state.setdefault("slot", {"kind": None})
        context = {"library": library, "game": game, "game_id": game_id,
                   "tables": tables, "state": state, "lens": "", "redraws": [],
                   "slot": state["slot"]}

        async def rebuild() -> None:
            await build(container, title, library, game_id, state)

        context["rebuild"] = rebuild
        work = state.get("mode") == "work"
        opened = open_sections(state)
        if work:
            # Held across games, so a sweep does not re-pick it at every stop.
            known = {section.key for section in SECTIONS}
            if state.get("section") not in known:
                state["section"] = "media"
        entries: dict[str, ui.element] = {}
        # The outline must not scroll with what it points at, so the row is the fixed
        # frame and only the body column scrolls inside it.
        with ui.row().classes("w-full grow min-h-0 no-wrap gap-0"):
            _outline(entries, opened, context, work)
            # A grid, so one rule decides whether the dock sits under the body or
            # beside it. Under is a vertical split of the workbench; beside is the
            # work layout. In both the dock is outside the scroll, which is what
            # makes "always visible" true rather than usually true.
            with ui.element("div").classes("grow min-w-0 h-full hub-workbench-main"):
                body = ui.column().classes("min-w-0 h-full overflow-auto gap-0 "
                                           "hub-workbench-body")
                context["dock"] = ui.column().classes("min-w-0 gap-0 hub-dock")
        with body:
            if work:
                await _one_section(context, state["section"])
            else:
                await _stacked_sections(context, opened, entries)


async def _one_section(context: dict[str, Any], key: str) -> None:
    """The chosen section, with the window to itself."""
    section = next(item for item in SECTIONS if item.key == key)
    heading = ui.label(section.label(context)).classes("hub-work-title")
    await section.build(context)

    async def relabel() -> None:
        heading.text = section.label(context)

    context["redraws"].append(relabel)


async def _stacked_sections(context: dict[str, Any], opened: set[str],
                            entries: dict[str, ui.element]) -> None:
    """Every section, with the ones you opened still open.

    Flat on purpose: ownership is a property of a section, not an axis to group by.
    Said instead by the one section a lens governs, in its own heading.
    """
    for item in SECTIONS:
        await _section(item, context, opened, entries)


def _outline(entries: dict[str, ui.element], opened: set[str],
             context: dict[str, Any], work: bool) -> None:
    """Contents when comparing, a selector when working.

    Below the work width it scrolls to a section and opens it, leaving everything else
    where it was - which is what lets a side nav and several-sections-open coexist.
    Above it, it picks the one section that gets the window.
    """
    with ui.column().classes("shrink-0 h-full overflow-auto gap-0 pr-1 hub-outline") \
            .style("width:132px"):
        for section in SECTIONS:
            item = ui.label(section.name).classes("hub-outline-item")
            lit = (context["state"].get("section") == section.key if work
                   else section.key in opened)
            if lit:
                item.classes(add="hub-outline-on")
            item.on("click", lambda key=section.key: _choose(context, key, work))
            entries[section.key] = item


def _choose(context: dict[str, Any], key: str, work: bool) -> None:
    """Reveal it, or make it the one on screen - whichever the width is for."""
    if not work:
        _reveal(key)
        return
    context["state"]["section"] = key
    asyncio.create_task(context["rebuild"]())


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

    expansion = ui.expansion(section.label(context), value=section.key in opened,
                             on_value_change=remember).classes("w-full") \
        .props(f"id=wb-{section.key}")
    with expansion, ui.column().classes("w-full gap-0"):
        await section.build(context)

    async def relabel() -> None:
        # So the scope in the heading is still true after the lens moves, and readable
        # with the section shut - which is the whole reason it is in the heading.
        expansion.text = section.label(context)

    context["redraws"].append(relabel)


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
    return label + (f", {borrowed} borrowed)" if borrowed else ")") + _media_scope(context)


def _media_scope(context: dict[str, Any]) -> str:
    """Which build this section is answering for, in its own heading.

    The only section a lens governs, so the only one that says so. Silent for a
    one-table folder: nothing to scope to, and nobody meets the concept.
    """
    tables = [table for table in context["tables"] if table.get("id")]
    if len(tables) < 2:
        return ""
    if not context["lens"]:
        return " \u00b7 shared"
    return " \u00b7 " + _ellipsize(
        _short_names(tables).get(context["lens"], context["lens"]), 24)


def _ellipsize(name: str, limit: int) -> str:
    """Shorten from the middle: trimming either end alone makes two builds read alike."""
    if len(name) <= limit:
        return name
    head = (limit - 1) // 2
    return name[:head] + "\u2026" + name[len(name) - (limit - 1 - head):]


def _short_names(tables: list[dict[str, Any]]) -> dict[str, str]:
    """What tells these builds apart, which is rarely the front of the name.

    Files in one folder share a long head - game, maker, year - so trimming from the
    right leaves every pill reading the same. The shared head comes off instead.
    """
    stems = {}
    for table in tables:
        name = table.get("filename") or table["id"]
        stems[table["id"]] = name[:-4] if name.lower().endswith(".vpx") else name
    values = list(stems.values())
    head = values[0]
    for value in values[1:]:
        while head and not value.startswith(head):
            head = head[:-1]
    # Back to a word boundary, so no name starts mid-word.
    head = head[:max(head.rfind(" "), head.rfind(")"), head.rfind("-")) + 1]
    return {tid: (stem[len(head):].strip(" -_") or stem) for tid, stem in stems.items()}


def _lens(context: dict[str, Any]) -> None:
    """Which build the sections below answer for.

    Only where a folder holds more than one. One table means one answer, so the
    control never appears and nobody meets the concept - the common case by a long way.
    """
    tables = [table for table in context["tables"] if table.get("id")]
    if len(tables) < 2:
        return

    pills: dict[str, ui.element] = {}
    short = _short_names(tables)

    async def pick(table_id: str) -> None:
        # The picked slot survives the switch. Looking at the same kind across two
        # builds is the reason to have a lens at all; closing the panel would make
        # the comparison two clicks instead of none.
        context["lens"] = table_id
        for key, pill in pills.items():
            pill.classes(add="hub-lens-on") if key == table_id \
                else pill.classes(remove="hub-lens-on")
        note.text = _lens_note(table_id)
        for redraw in context["redraws"]:
            await redraw()

    with ui.row().classes("items-center gap-1 w-full px-3 pt-1 hub-lens"):
        ui.label("Viewing as").classes("hub-lens-label")
        for table_id in [""] + [t["id"] for t in tables]:
            pill = ui.label(_ellipsize(short.get(table_id, "Shared"), 18)) \
                .classes("hub-lens-pill")
            if table_id == context["lens"]:
                pill.classes(add="hub-lens-on")
            pill.on("click", lambda tid=table_id: pick(tid))
            # Still truncated where a tail is long; the whole filename is a hover away.
            pill.tooltip(next((t.get("filename") or t["id"] for t in tables
                               if t["id"] == table_id), "Every table in this game"))
            pills[table_id] = pill
    # After the control, not before it: this is the consequence of the pill you picked.
    note = ui.label(_lens_note(context["lens"])).classes("hub-help px-3 pb-1")


def _lens_note(table_id: str) -> str:
    return ("Named for this .vpx. Only this table uses them." if table_id else
            "Named for the folder. Every table in this game uses them.")


async def _media_block(context: dict[str, Any]) -> None:
    """The map, and whatever tile is picked out of it."""
    # Inside the section it scopes, so there is no question what it applies to.
    _lens(context)
    library, game_id = context["library"], context["game_id"]
    holder = ui.column().classes("w-full gap-0")

    async def draw() -> None:
        table_id = context["lens"]
        entries = await run.io_bound(library.media_for, game_id, table_id or None)
        holder.clear()
        with holder:
            mediamap.build(entries, _prefix(game_id, table_id),
                           on_pick=lambda kind: _pick_slot(context, kind, draw),
                           selected=context["slot"]["kind"])
        dock = context.get("dock")
        if dock is not None:
            dock.clear()
            kind = context["slot"]["kind"]
            if kind and kind in entries:
                with dock:
                    _slot(context, kind, entries[kind], draw)

    context["redraws"].append(draw)
    await draw()


def _pick_slot(context: dict[str, Any], kind: str, draw) -> None:
    """Clicking the picked tile again puts the panel away."""
    slot = context["slot"]
    slot["kind"] = None if slot["kind"] == kind else kind
    asyncio.create_task(draw())


def _slot(context: dict[str, Any], kind: str, entry: dict[str, Any], draw) -> None:
    """One slot: what is there, how it got to be the one used, and what to do about it.

    The three facts are the whole point of the surface - does it resolve, how specific
    is the match, where did the file come from - and this is where they stop being a
    tooltip and become something you can act on.
    """
    library, game_id = context["library"], context["game_id"]
    table_id = context["lens"]
    label = mediamap.LABELS.get(kind, kind)

    async def place(event: Any) -> None:
        data = await event.file.read()
        try:
            await run.io_bound(library.place_media, game_id, table_id, kind,
                               event.file.name, data)
        except Exception as exc:
            ui.notify(f"Could not place it: {exc}", type="negative")
            return
        ui.notify(f"{label} placed", type="positive")
        await draw()

    async def remove() -> None:
        try:
            result = await run.io_bound(library.remove_media, game_id, table_id, kind)
        except Exception as exc:
            ui.notify(f"Could not remove it: {exc}", type="negative")
            return
        gone = len(result.get("removed") or [])
        ui.notify(f"Removed {gone} file(s)" if gone else
                  "Nothing to remove at this level", type="positive" if gone else "info")
        await draw()

    # Preview and details are separate boxes so one rule can put them side by side.
    # Docked under the map there is height for neither a tall preview nor a tall
    # column of controls, and stacking them is what put the actions below the fold.
    with ui.column().classes("w-full gap-1 hub-slot p-2"):
        ui.label(label).classes("hub-card-title")
        with ui.element("div").classes("hub-slot-body"):
            with ui.element("div").classes("hub-slot-preview"):
                if entry.get("present"):
                    ui.html(f'<img src="{_prefix(game_id, table_id)}/{kind}">')
                else:
                    ui.label(f"No {label.lower()} for this "
                             f"{'build' if table_id else 'game'}.").classes("hub-help")
            with ui.column().classes("hub-slot-details gap-1"):
                if entry.get("present"):
                    _rows(ui, {"File": entry.get("file") or "-",
                               "Resolved": entry.get("via") or "-",
                               "Origin": entry.get("origin") or "-"})
                # Labelled, because an unlabelled uploader falls back to Quasar's byte
                # counter - "0.0B / 0.00%" where the name of the action should be.
                ui.upload(on_upload=place, auto_upload=True, max_files=1,
                          label="Replace" if entry.get("present") else "Add a file") \
                    .props("flat dense").classes("w-full")
                ui.label("Placed here, it is named for "
                         + ("this .vpx." if table_id else "the folder.")) \
                    .classes("hub-help")
                with ui.row().classes("items-center gap-1 w-full").style("flex-wrap:wrap"):
                    if entry.get("present"):
                        ui.button("Remove", on_click=remove) \
                            .props("flat dense no-caps size=sm")
                    # Disabled rather than omitted, so what the slot is for is legible
                    # before either exists. Both parked in HUBUI section 10.
                    ui.button("Search sources").props("flat dense no-caps size=sm") \
                        .set_enabled(False)
                    ui.button("Capture").props("flat dense no-caps size=sm") \
                        .set_enabled(False)
                # A disabled control with no reason reads as broken. One line, because
                # a Quasar button that is disabled takes no pointer events and so can
                # carry no tooltip.
                ui.label("Sources and capture are not built yet.").classes("hub-help")


async def _identity_block(context: dict[str, Any]) -> None:
    game = context["game"]
    with ui.column().classes("gap-0 hub-form"):
        _identity_rows(game)


def _identity_rows(game: dict[str, Any]) -> None:
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


async def _forget_table(context: dict[str, Any], table: dict[str, Any]) -> None:
    """Drop a gone table's record, once the user says it is not coming back.

    Confirmed because it is the only destructive thing on this surface, and the dialog
    names the file rather than the id - the id is ours, the filename is what the user
    recognises. The hub refuses the request outright if the .vpx is back, so a stale
    panel cannot delete a table that returned while it was open.
    """
    filename = table.get("filename") or "this table"
    with ui.dialog() as confirm, ui.card():
        ui.label("Forget this table?").classes("hub-card-title")
        ui.label(filename).classes("text-xs opacity-70 break-all")
        ui.label("Its record goes; no file is deleted, because there is none. Put the "
                 ".vpx back and refresh and it returns as a new table.").classes("text-xs")
        with ui.row().classes("justify-end gap-2 w-full"):
            ui.button("Cancel", on_click=lambda: confirm.submit(False)).props("flat")
            ui.button("Forget", on_click=lambda: confirm.submit(True)).props("color=negative")

    if not await confirm:
        return
    try:
        await run.io_bound(context["library"].forget_table,
                           context["game_id"], table.get("id") or "")
    except Exception as exc:
        ui.notify(f"Could not forget it: {exc}", type="negative")
        return
    ui.notify("Table forgotten", type="positive")
    await context["rebuild"]()


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
                ui.space()
                ui.button(icon="delete_outline",
                          on_click=lambda _, t=table: _forget_table(context, t)) \
                    .props("flat dense size=sm color=warning") \
                    .tooltip("Forget this table")
            else:
                ui.badge(table.get("app") or "?", color="secondary").props("outline")


def _rows(target: Any, values: dict[str, str]) -> None:
    for label, value in values.items():
        with target.row().classes("items-center gap-2 w-full px-3 py-0"):
            target.label(label).classes("text-xs opacity-60 w-20")
            target.label(str(value)).classes("text-xs truncate")


SECTIONS: tuple[Section, ...] = (
    Section("identity", "Identity", lambda _: "Identity", _identity_block),
    Section("media", "Media", _media_label, _media_block),
    Section("tables", "Tables", _tables_label, _tables_block),
)
