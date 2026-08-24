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

from common.media_specs import media_family
from hubui import mediamap, mediaview
from hubui.data import Library

# Which group a section belongs to, in the order they are shown.
# Short, because the outline and the body would otherwise say the same three phrases
# twice on one screen. What each group means is carried by the lens sitting in it and
# by the sections themselves, not by shouting the scope.
# Where the split sits until somebody drags it. Enough for a preview and the facts
# under it without taking the map's room.
DOCK_PX = 300

# Dragged in the browser, reported once on release - a round trip per pointer move
# would lag badly. Guarded, because the panel is rebuilt on every section change.
_GRIP = """
if (!window.__hubDockGrip) {
  window.__hubDockGrip = true;
  let drag = null;
  document.addEventListener('pointerdown', (e) => {
    const grip = e.target.closest && e.target.closest('.hub-dock-grip');
    if (!grip) return;
    const main = grip.closest('.hub-workbench-main');
    const dock = main && main.querySelector('.hub-dock');
    if (!dock) return;
    e.preventDefault();
    drag = { y: e.clientY, from: dock.getBoundingClientRect().height, main };
    grip.setPointerCapture(e.pointerId);
  });
  document.addEventListener('pointermove', (e) => {
    if (!drag) return;
    e.preventDefault();
    const room = drag.main.getBoundingClientRect().height;
    // Both regions keep a floor, so a drag cannot leave either as a sliver.
    const next = Math.min(room - 160, Math.max(140, drag.from - (e.clientY - drag.y)));
    drag.main.style.setProperty('--dock-h', Math.round(next) + 'px');
  });
  const done = () => {
    if (!drag) return;
    const px = parseInt(drag.main.style.getPropertyValue('--dock-h'), 10);
    drag = null;
    if (px) emitEvent('hub_dock_px', px);
  };
  document.addEventListener('pointerup', done);
  document.addEventListener('pointercancel', done);
}
"""

# The section shown when nobody has said otherwise. The map is the question people
# actually have about a game, and its shape answers before a label is read.
DEFAULT_SECTION = "media"

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
    """One block in the panel: what it is called and how to draw it.

    `name` is the fixed word the outline shows; `label` takes the game's context
    because a heading that counts something has to count this game's - and, for the
    one section a lens governs, say which build it is counting. `build` is async
    because a section may need a fetch.

    `icon` is what the selector shows when there is no room for the word. Every section
    needs one, because a mode with no icon would simply vanish at that width.
    """

    key: str
    name: str
    icon: str
    label: Callable[[dict[str, Any]], str]
    build: Callable[[dict[str, Any]], Any]


def chosen_section(state: dict[str, Any]) -> str:
    """The section this client is on, seeded once and kept across games.

    Held across games so stepping down a list does not re-pick a section at every stop,
    which is what looking at one kind across a library needs.
    """
    known = {section.key for section in SECTIONS}
    if state.get("section") not in known:
        state["section"] = DEFAULT_SECTION
    return state["section"]


async def build(container: ui.column, title: ui.column, library: Library,
                game_id: str | None, state: dict[str, Any] | None = None) -> None:
    """Fill the panel, and the name that lives up in the panel's header row."""
    state = state if state is not None else {}
    # Registered once: the height a drag settled on has to survive the rebuild that a
    # section change causes, and the panel is what remembers it.
    if not state.get("dock_grip_bound"):
        state["dock_grip_bound"] = True
        ui.on("hub_dock_px", lambda e: state.__setitem__("dock_px", int(e.args or 0))
              if e.args else None)
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
        section = chosen_section(state)
        # Three regions, in reading order: which mode you are in, what that mode gives
        # you to browse, and what you are working on. The outline must not scroll with
        # what it points at, so this row is the fixed frame and only the body scrolls.
        with ui.row().classes("w-full grow min-h-0 no-wrap gap-0 hub-workbench-frame"):
            _outline(context, section)
            # A grid, so one rule decides whether work sits under browse or beside it.
            # Under is a vertical split; beside is what a wide window is for. In both
            # it is outside the scroll, which makes "always visible" true rather than
            # usually true.
            # A stored height, not the dock's content height, or the divider moves
            # with whatever kind of media you picked.
            with ui.element("div").classes("grow min-w-0 h-full hub-workbench-main") \
                    .style(f"--dock-h: {state.get('dock_px', DOCK_PX)}px"):
                body = ui.column().classes("min-w-0 h-full overflow-auto gap-0 "
                                           "hub-workbench-body")
                ui.element("div").classes("hub-dock-grip") \
                    .tooltip("Drag to resize")
                context["dock"] = ui.column().classes("min-w-0 gap-0 hub-dock")
        with body:
            await _one_section(context, section)
        ui.run_javascript(_GRIP)


async def _one_section(context: dict[str, Any], key: str) -> None:
    """The chosen section, with the window to itself."""
    section = next(item for item in SECTIONS if item.key == key)
    heading = ui.label(section.label(context)).classes("hub-work-title")
    await section.build(context)

    async def relabel() -> None:
        heading.text = section.label(context)

    context["redraws"].append(relabel)


def _outline(context: dict[str, Any], chosen: str) -> None:
    """Which mode the workbench is in. One meaning at every width.

    It used to be a table of contents when narrow and a selector when wide, and that is
    the only reason a width threshold ever existed: a control that changes meaning
    partway across the range needs somebody to guess where. It picks the section now,
    always - the stylesheet decides whether that reads as a column or a strip.
    """
    with ui.column().classes("shrink-0 h-full overflow-auto gap-0 pr-1 hub-outline"):
        for section in SECTIONS:
            item = ui.row().classes("items-center gap-2 no-wrap hub-outline-item")
            if section.key == chosen:
                item.classes(add="hub-outline-on")
            with item:
                ui.icon(section.icon, size="20px").classes("hub-outline-icon")
                ui.label(section.name).classes("hub-outline-text")
            # Carries the word when the width has taken it away, which is the whole
            # reason the labels can go.
            item.tooltip(section.name)
            item.on("click", lambda key=section.key: _choose(context, key))


def _choose(context: dict[str, Any], key: str) -> None:
    """Make it the section on screen."""
    context["state"]["section"] = key
    asyncio.create_task(context["rebuild"]())


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
            with dock:
                if kind and kind in entries:
                    _slot(context, kind, entries[kind], draw)
                else:
                    # The region is reserved either way, so it says what it is for
                    # rather than sitting there as an empty box. Named for what the
                    # user is looking at - the user sees - rather than for the slot
                    # they fill, which is our word and not theirs. No "above" or
                    # "beside" either: this region moves depending on the width.
                    with ui.column().classes("hub-dock-empty items-center gap-1"):
                        ui.label("No media chosen").classes("hub-dock-empty-title")
                        ui.label("Choose any media to see where it came from, "
                                 "and to replace it.").classes("hub-help")

    context["redraws"].append(draw)
    await draw()


def _preview(src: str, kind: str, label: str) -> None:
    """Present the file with an element that can actually play it.

    An <img> pointing at a .mp4 downloads the whole file and paints nothing - the slot
    looked empty for a video that is there, and on a library that is not local the
    fetch is long enough to read as the page having stopped. `preload="metadata"` is
    what keeps the poster frame cheap: enough to show it, not the whole video.
    """
    family = media_family(kind)
    if family == "video":
        # `#t=0.1` for the same reason the map tiles use it: metadata alone can leave
        # the frame blank, and an empty box behind a play button says nothing about
        # what is in the file.
        ui.html(f'<video src="{src}#t=0.1" preload="metadata" controls '
                f'playsinline></video>')
    elif family == "audio":
        ui.html(f'<audio src="{src}" preload="metadata" controls></audio>')
    elif family == "image":
        ui.html(f'<img src="{src}">')
    else:
        # A rule sheet is a document; there is no element that previews one usefully
        # in a panel this size, and a broken <img> would say it is missing.
        ui.link(f"Open {label.lower()}", src, new_tab=True).classes("hub-help")


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
        name = event.file.name
        try:
            going = await run.io_bound(library.displaced_by, game_id, table_id,
                                       kind, name)
        except Exception as exc:
            ui.notify(f"Could not check that slot: {exc}", type="negative")
            return
        if going and not await _confirm_replace(label, going):
            return

        data = await event.file.read()
        try:
            await run.io_bound(library.place_media, game_id, table_id, kind, name, data)
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

    # Widening only, and only from the build you are looking at. The other direction -
    # a shared file becoming one build's - reads as a move but takes the file away from
    # every other table in the folder, and in the shared lens there is no build in view
    # to say which one would get it. That one needs a decision, not a default.
    move_label = ""
    if (entry.get("present") and table_id
            and str(entry.get("via") or "") == "table"):
        move_label = "Share with every table"

    async def retier() -> None:
        """The build's own file takes the folder's name, so every table resolves it."""
        try:
            await run.io_bound(library.retier_media, game_id, kind, table_id, "")
        except Exception as exc:
            ui.notify(f"Could not move it: {exc}", type="negative")
            return
        ui.notify("Shared with every table", type="positive")
        for redraw in context["redraws"]:
            await redraw()

    # Preview and details are separate boxes so one rule can put them side by side.
    # Docked under the map there is height for neither a tall preview nor a tall
    # column of controls, and stacking them is what put the actions below the fold.
    with ui.column().classes("w-full gap-1 hub-slot p-2"):
        ui.label(label).classes("hub-card-title")
        with ui.element("div").classes("hub-slot-body"):
            with ui.element("div").classes("hub-slot-preview"):
                if entry.get("present"):
                    src = f"{_prefix(game_id, table_id)}/{kind}"
                    _preview(src, kind, label)
                    # Images only: a video here keeps its native controls, and those
                    # already carry a full-screen button of their own.
                    if media_family(kind) == "image":
                        ui.button("Enlarge", icon="open_in_full",
                                  on_click=lambda s=src, k=kind, la=label:
                                      mediaview.open_viewer(s, k, la)) \
                            .props("flat dense no-caps size=sm")
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
                with ui.row().classes("items-center gap-2 w-full").style("flex-wrap:wrap"):
                    if entry.get("present"):
                        ui.button("Remove", on_click=remove) \
                            .props("flat dense no-caps size=sm") \
                            .classes("hub-action hub-action--danger")
                    if move_label:
                        ui.button(move_label, on_click=retier) \
                            .props("flat dense no-caps size=sm").classes("hub-action")
                    # Disabled rather than omitted, so what the slot is for is legible
                    # before either exists. Both parked in HUBUI section 10.
                    ui.button("Search sources").props("flat dense no-caps size=sm") \
                        .classes("hub-action").set_enabled(False)
                    ui.button("Capture").props("flat dense no-caps size=sm") \
                        .classes("hub-action").set_enabled(False)
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


async def _confirm_replace(label: str, going: list[str]) -> bool:
    """Name what a drop would replace, and wait for a yes.

    The files are listed rather than counted because the surprising case is the one a
    count hides: a whole family goes at this tier, so a .mp4 dropped over a .png takes
    the .png with it and the user never named that file.
    """
    with ui.dialog() as confirm, ui.card():
        ui.label(f"Replace the {label.lower()} that is there?").classes("hub-card-title")
        for path in going:
            ui.label(path).classes("text-xs opacity-70 break-all")
        ui.label("Replaced files are deleted, not kept.").classes("text-xs")
        with ui.row().classes("justify-end gap-2 w-full"):
            ui.button("Cancel", on_click=lambda: confirm.submit(False)).props("flat")
            ui.button("Replace",
                      on_click=lambda: confirm.submit(True)).props("color=negative")
    return bool(await confirm)


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
    """One fact per line: the name, then the value, however narrow the panel gets.

    `no-wrap` keeps them on one line and `min-w-0` is what lets the value actually
    shrink - a flex child refuses to go below its content width without it, so the row
    stayed wide and wrapped instead of the value ellipsing.
    """
    for label, value in values.items():
        with target.row().classes("items-center gap-2 w-full no-wrap px-3 py-0"):
            target.label(label).classes("text-xs opacity-60 shrink-0 w-20")
            target.label(str(value)).classes("text-xs truncate grow min-w-0") \
                .tooltip(str(value))


SECTIONS: tuple[Section, ...] = (
    Section("identity", "Identity", "badge", lambda _: "Identity", _identity_block),
    Section("media", "Media", "perm_media", _media_label, _media_block),
    # Layers, because what this section holds is the builds of one game stacked on each
    # other - the same icon the app nav gives Media, for the section that is media.
    Section("tables", "Tables", "layers", _tables_label, _tables_block),
)
