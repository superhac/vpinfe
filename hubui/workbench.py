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
import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from nicegui import run, ui

from common.media_specs import media_family
from hubui import deeplink, mediamap, mediasource, mediaview, tiers
from hubui.data import Library

logger = logging.getLogger("vpinfe.hubui.workbench")

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
                game_id: str | None, state: dict[str, Any] | None = None,
                table_id: str = "") -> None:
    """Fill the panel, and the name that lives up in the panel's header row.

    `table_id` is the subject when the Tables lens is what selected it. Empty means the
    game itself, which is what the Games lens selects.
    """
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
        await _draw(container, title, library, game_id, state, table_id)


async def _draw(container: ui.column, title: ui.column, library: Library,
                game_id: str | None, state: dict[str, Any], table_id: str = "") -> None:
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
        made = f"{game.get('manufacturer') or '?'} {game.get('year') or ''}"
        _title(title, game.get("name") or "", made)

        # Off the loop, always. This is an HTTP call to our own process: made on the
        # event loop it blocks the server from answering it, the request times out
        # after 15s, and the browser reports the socket as lost rather than slow.
        tables = await run.io_bound(library.tables_for, game_id)
        # Named under the game once a file is the subject, so the header says which of
        # the four you are looking at without a control to read.
        chosen = next((t for t in tables if t.get("id") == table_id), None)
        if chosen is not None:
            with title:
                ui.label(_table_line(chosen)).classes("hub-workbench-table") \
                    .tooltip(str(chosen.get("filename") or ""))
        # `lens` is a table id or "" for the folder's shared files, and it resets per
        # game because a table id means nothing to the next one. `redraws` is how the
        # lens reaches the sections that follow it without rebuilding the panel.
        # The picked slot lives with the client, not this build of the panel: a mode
        # change rebuilds and would otherwise forget it. Kept across games too, which
        # is what sweeping one kind down a list needs.
        state.setdefault("slot", {"kind": None})
        # The lens is the grid's selection, not a control in here. Under Games that is
        # the game and the panel answers for shared files; under Tables it is one file
        # and the panel answers for that.
        context = {"library": library, "game": game, "game_id": game_id,
                   "tables": tables, "state": state, "lens": table_id, "redraws": [],
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
    deeplink.sync(context["state"])
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
    """The lens used to be repeated here. The header states it now, once."""
    return ""


def _go_to_table(context: dict[str, Any], table_id: str) -> None:
    """Follow a differing table into its own lens.

    The way out of the game's view and into the file's, rather than a second editor
    for one table's art embedded in a panel that is about the game.
    """
    if not table_id:
        return
    state = context["state"]
    state["subject"] = "table"
    state["table"] = table_id
    deeplink.sync(state)
    asyncio.create_task(context["rebuild"]())


def _table_line(table: dict[str, Any]) -> str:
    """Which of a game's tables this is, in the fewest words that tell them apart.

    Version and author rather than the filename: the names of one game's tables share
    forty characters and differ in two, so a header wide enough for the game is never
    wide enough for the file. The filename is a hover away, and it is the grid's job.
    """
    version = str(table.get("version") or "").strip()
    authors = ", ".join(str(a) for a in (table.get("authors") or []))
    said = " \u00b7 ".join(part for part in (version, authors[:28]) if part)
    return said or _tail(str(table.get("filename") or ""), 40)


def _tail(name: str, limit: int) -> str:
    """A filename cut from the front, keeping the end.

    The tables in one game share a long prefix and differ at the tail - "(Williams
    1993)12" against "(Williams 1993)lw" - so trimming the end trims the only half
    that tells them apart.
    """
    stem = name[:-4] if name.lower().endswith(".vpx") else name
    return stem if len(stem) <= limit else "\u2026" + stem[-(limit - 1):]


async def _media_block(context: dict[str, Any]) -> None:
    """The map, and whatever tile is picked out of it."""
    library, game_id = context["library"], context["game_id"]
    holder = ui.column().classes("w-full gap-0")

    async def draw() -> None:
        table_id = context["lens"]
        entries = await run.io_bound(library.media_for, game_id, table_id or None)
        # Only from the game's lens. Looking at one table, the badge on a slot already
        # says whose file it is, and marking the others would be noise about tables
        # that are not the subject.
        overrides = ({} if table_id else
                     await run.io_bound(library.media_overrides, game_id))
        holder.clear()
        with holder:
            mediamap.build(entries, _prefix(game_id, table_id),
                           on_pick=lambda kind: _pick_slot(context, kind, draw),
                           selected=context["slot"]["kind"],
                           overrides=overrides)
        dock = context.get("dock")
        if dock is not None:
            dock.clear()
            # Kept for the sources dialog, which says whether a file it is offering
            # is already serving one of this game's slots.
            context["media"] = entries
            kind = context["slot"]["kind"]
            detail = None
            if kind and kind in entries:
                try:
                    detail = await run.io_bound(library.media_detail, game_id,
                                                table_id or None, kind)
                except Exception:
                    logger.debug("No detail for %s", kind, exc_info=True)
            with dock:
                if kind and kind in entries:
                    _slot(context, kind, entries[kind], detail, draw,
                          (overrides or {}).get(kind) or [])
                else:
                    # The region is reserved either way, so it says what it is for
                    # rather than sitting there as an empty box. Named for what the
                    # user is looking at - the user sees - rather than for the slot
                    # they fill, which is our word and not theirs. No "above" or
                    # "beside" either: this region moves depending on the width.
                    with ui.column().classes("hub-dock-empty items-center gap-1"):
                        ui.label("No media chosen").classes("hub-dock-empty-title")
                        ui.label("Select any media item to manage it") \
                            .classes("hub-help")

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
    deeplink.sync(context["state"])
    asyncio.create_task(draw())


# An empty slot still shows what shape of thing belongs in it. Not the map's glyph
# rule, which returns nothing for a kind that normally has a frame to show - here
# there is no frame, which is the point.
_BLANK_ICON = {"image": "image", "video": "movie",
               "audio": "graphic_eq", "doc": "description"}


def _spec(detail: dict[str, Any]) -> str:
    """Size, shape and date on one line - what tells two files of a kind apart when
    both look right in a thumbnail."""
    parts = []
    if detail.get("width") and detail.get("height"):
        parts.append(f"{detail['width']} \u00d7 {detail['height']}")
    name = str(detail.get("file") or "")
    if "." in name:
        parts.append(name.rsplit(".", 1)[1].upper())
    size = mediasource._size(detail.get("size_bytes"))
    if size:
        parts.append(size)
    stamp = str(detail.get("modified") or "")
    if stamp:
        try:
            parts.append(datetime.fromisoformat(stamp).astimezone().strftime("%d %b %Y"))
        except ValueError:
            pass
    return " \u00b7 ".join(parts)


def _slot(context: dict[str, Any], kind: str, entry: dict[str, Any],
          detail: dict[str, Any] | None, draw,
          differing: list[dict[str, Any]] | None = None) -> None:
    """One slot: the art at the size of the room, and what there is to know about it.

    The picture is the subject. Everything else is one line each underneath, because
    the questions this panel answers - what is this, why this one, what else is here -
    are each a sentence, and a table of fields makes the reader do the joining.
    """
    library, game_id = context["library"], context["game_id"]
    table_id = context["lens"]
    label = mediamap.LABELS.get(kind, kind)
    # The map already knows the slot; detail only adds to it. A failed read should
    # cost the spec line, never the panel.
    detail = detail or {}
    present = bool(entry.get("present"))
    file_name = detail.get("file") or entry.get("file") or ""
    also_here = list(detail.get("tiers") or [])

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

    # Widening only, and only from the table you are looking at. The other direction -
    # a shared file becoming one table's - reads as a move but takes the file away from
    # every other table in the folder, and in the shared lens there is no table in view
    # to say which one would get it. That one needs a decision, not a default.
    can_share = present and table_id and str(entry.get("via") or "") == "table"

    async def share() -> None:
        """The table's own file takes the folder's name, so every table resolves it."""
        try:
            await run.io_bound(library.retier_media, game_id, kind, table_id, "")
        except Exception as exc:
            ui.notify(f"Could not move it: {exc}", type="negative")
            return
        ui.notify("Now used by all tables in this game", type="positive")
        for redraw in context["redraws"]:
            await redraw()

    with ui.column().classes("w-full gap-1 hub-slot p-2"):
        ui.label(label).classes("hub-card-title")

        with ui.element("div").classes("hub-slot-art"):
            if present:
                src = f"{_prefix(game_id, table_id)}/{kind}"
                _preview(src, kind, label)
                # On the picture, where the map puts it. Images only: a video keeps its
                # native controls here, and those carry a full-screen button already.
                if media_family(kind) == "image":
                    ui.button(icon="open_in_full",
                              on_click=lambda s=src, k=kind, la=label:
                                  mediaview.open_viewer(s, k, la)) \
                        .props("flat dense round size=sm") \
                        .classes("hub-slot-zoom").tooltip("Enlarge")
            else:
                with ui.column().classes("hub-slot-blank items-center gap-1"):
                    ui.icon(_BLANK_ICON.get(media_family(kind), "help_outline")) \
                        .classes("hub-slot-blank-icon")

        with ui.column().classes("w-full gap-0 hub-slot-facts"):
            if present:
                with ui.row().classes("items-start gap-2 w-full no-wrap"):
                    ui.label(file_name).classes("hub-slot-file grow min-w-0")
                    tiers.badge(detail.get("via") or entry.get("via"))
                spec = _spec(detail)
                if spec:
                    ui.label(spec).classes("hub-help")
                ui.label(tiers.sentence(detail.get("via") or entry.get("via"),
                                        viewing_a_table=bool(table_id))) \
                    .classes("hub-help")
                origin = str(detail.get("origin") or entry.get("origin") or "")
                # "unknown" is the ledger's honest answer and a useless line to read:
                # most files predate the ledger, so it would be on nearly every slot.
                if origin and origin not in ("unknown", "user"):
                    ui.label(f"Came from {origin}").classes("hub-help")
            else:
                ui.label(f"No {label.lower()} for this "
                         f"{'table' if table_id else 'game'}").classes("hub-help")

        # Only when there is more than one, because with one the sentence above has
        # already said where it is. Two is the case worth a list: the second file is
        # why an edit appeared to do nothing.
        if len(also_here) > 1:
            with ui.column().classes("w-full gap-0 hub-slot-others"):
                ui.label("Also in this folder").classes("hub-slot-others-title")
                for item in also_here:
                    if item.get("wins"):
                        continue
                    with ui.row().classes("items-center gap-2 w-full no-wrap"):
                        ui.label(item.get("file") or "").classes("hub-slot-other-file")
                        tiers.badge(item.get("tier"))

        # Only from the game's lens, and only when somebody differs. This is the whole
        # of Model B in the panel: the shared file above, and who is not using it.
        for other in (differing or []):
            with ui.row().classes("items-center gap-2 w-full no-wrap hub-slot-differs"):
                tiers.badge("table")
                ui.label(_table_line(other) or other.get("filename") or "") \
                    .classes("hub-slot-other-file").tooltip(other.get("file") or "")
                ui.button(icon="arrow_forward", on_click=lambda o=other: _go_to_table(
                    context, o.get("table") or "")) \
                    .props("flat dense round size=sm").classes("shrink-0") \
                    .tooltip("Open this table")

        with ui.row().classes("items-center gap-2 w-full hub-slot-actions") \
                .style("flex-wrap:wrap"):
            ui.button("Replace" if present else "Add",
                      icon="add_photo_alternate",
                      on_click=lambda: mediasource.open_sources(context, kind, label,
                                                                draw)) \
                .props("flat dense no-caps size=sm").classes("hub-action")
            if present:
                ui.button("Remove", on_click=remove) \
                    .props("flat dense no-caps size=sm") \
                    .classes("hub-action hub-action--danger")
            if can_share:
                ui.button("Give to all tables", on_click=share) \
                    .props("flat dense no-caps size=sm").classes("hub-action")


async def _identity_block(context: dict[str, Any]) -> None:
    """Who this is - which is a different set of facts depending on what is selected.

    The first view where the two subjects genuinely diverge. A game is a machine: the
    VPS match, the theme, the year. A table is a file somebody built: its version, who
    built it, which rom it drives. Showing the game's four rows while a table is
    selected would answer a question nobody asked.
    """
    game = context["game"]
    chosen = next((t for t in context["tables"] if t.get("id") == context["lens"]),
                  None)
    with ui.column().classes("gap-0 hub-form"):
        if chosen is not None:
            _table_rows(chosen)
        else:
            _identity_rows(game)


def _identity_rows(game: dict[str, Any]) -> None:
    _rows(ui, {
        "VPS id": game.get("vps_id") or "-",
        "ROM": game.get("rom") or "-",
        "Type": game.get("type") or "-",
        "Themes": ", ".join(game.get("themes") or []) or "-",
    })


def _table_rows(table: dict[str, Any]) -> None:
    """One table's own facts.

    The rom is the one it resolves to with any alias followed, which is the one that
    has to exist - the declared name is shown beside it only when they differ, because
    that is the case somebody has to reason about.
    """
    pinmame = (table.get("dependencies") or {}).get("pinmame") or {}
    declared = str(pinmame.get("declared") or "")
    effective = str(pinmame.get("effective") or "")
    rom = effective or declared or "-"
    if declared and effective and declared != effective:
        rom = f"{effective}  (declared {declared})"

    state = []
    if table.get("default"):
        state.append("the game's default")
    if table.get("hidden"):
        state.append("hidden from the frontend")
    if not table.get("available"):
        state.append("file not on disk")

    _rows(ui, {
        "File": table.get("filename") or "-",
        "Version": table.get("version") or "-",
        "Built by": ", ".join(table.get("authors") or []) or "-",
        "ROM": rom,
        "Runs with": table.get("app") or "-",
        "Status": ", ".join(state) or "in play",
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
    Section("details", "Details", "badge", lambda _: "Details", _identity_block),
    Section("media", "Media", "perm_media", _media_label, _media_block),
    # Layers, because what this section holds is the builds of one game stacked on each
    # other - the same icon the app nav gives Media, for the section that is media.
    Section("tables", "Tables", "layers", _tables_label, _tables_block),
)
