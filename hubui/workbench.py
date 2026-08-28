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
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import PurePosixPath
from typing import Any

from nicegui import run, ui

from common.games import apps
from common.games.collection_store import (
    DEFAULT_ORDER_BY,
    DIRECTION_LABELS,
    MANUAL_ORDER,
    SORT_LABELS,
)
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
    const main = grip.closest('.hub-section-work');
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

# Where a fresh client lands, per rail. Identity, because selecting a row is usually
# navigation rather than curation: the first question a selection asks is what this is,
# and the answer is also where the things you can do to it live.
#
# Per rail rather than one value, because a rail declares its own landing place - and a
# table selected on purpose should not open on the machine that contains it.
DEFAULT_SECTION = {"game": "game_details", "table": "table_details",
                   "collection": "collection_details"}
# Every section closed. Named, because it travels in the state and the address, and
# "" appearing in either wants to be findable as a decision rather than as a blank.
COLLAPSED = ""

# Below this the outline costs more than it gives: 132px of it against a 320px
# workbench leaves the map too narrow to read, and the section headers are already
# a list of what is here. It earns its place once there is room for both.
#
# Enforced in CSS by a container query, not here. Quasar resizes the pane live while
# you drag and only tells the server on release, so a server-side threshold changed
# the layout a beat after you let go - which is exactly when you can no longer see
# what you were aiming at.
OUTLINE_FROM_PX = 520

# Rows that are not a fact. A group's title and a group's actions both span the whole
# grid, so every group keeps the one shared label column - the alignment a second grid
# would break.
HEADING = object()
FULL = object()



@dataclass(frozen=True)
class Section:
    """One block in the panel: what it is called and how to draw it.

    One name, on the row that opens it. There is no second heading over the content,
    because the row is the heading.

    `label` takes the context, since a name that counts something has to count this
    game's. `build` is async because a section may need a fetch.
    """

    key: str
    label: Callable[[dict[str, Any]], str]
    build: Callable[[dict[str, Any]], Any]
    # What this section is about. The rail is what the selected subject can be asked,
    # so a section that only makes sense for one of them says so and is simply absent
    # for the other - rather than being present and answering a question nobody asked.
    # Keys stay unique across every rail, so `section=` in an address means one thing.
    subjects: frozenset[str] = frozenset({"game", "table"})
    # Whether this section works on a picked thing beside its browse region. Only the
    # one that has something to pick declares it: reserving the room everywhere left
    # a section like Game details as four lines of text over an empty half-panel,
    # with the sections under it pushed to the bottom edge.
    dock: bool = False


def sections_for(subject: str) -> tuple[Section, ...]:
    """The rail for this subject, in order."""
    return tuple(item for item in SECTIONS if subject in item.subjects)


def chosen_section(state: dict[str, Any], subject: str = "game") -> str:
    """The section this client is on, seeded once and kept across games.

    "" when every section is closed, which is a place like any other.

    Held across games so stepping down a list does not re-pick a section at every stop,
    which is what looking at one kind across a library needs. Held across subjects too
    where it can be - but a section the new subject has no answer for is not one of
    those, and then the rail's own default is where you land rather than wherever the
    list happens to start.
    """
    rail = sections_for(subject)
    known = {item.key for item in rail}
    if state.get("section") == COLLAPSED:
        # Asked for, so it is kept - including across a change of subject. Seeding a
        # default here would reopen a section the user just shut.
        return COLLAPSED
    if state.get("section") not in known:
        wanted = DEFAULT_SECTION.get(subject, "")
        state["section"] = wanted if wanted in known else rail[0].key
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
            # The subject has to survive a rebuild. Left off, every rail click fell
            # back to the game and the table's own sections vanished under the cursor.
            await build(container, title, library, game_id, state, table_id)

        context["rebuild"] = rebuild
        await _rail(context, "table" if table_id else "game", state)


async def build_collection(container: ui.column, title: ui.column, library: Library,
                           name: str | None, state: dict[str, Any] | None = None) -> None:
    """The panel, for a collection rather than a game.

    Its own entry point rather than a branch inside `build`: a collection has no game,
    no tables and no media lens, so everything that build assembles for those would be
    a chain of empty values threaded through to sections that never read them.
    """
    state = state if state is not None else {}
    lock: asyncio.Lock = state.setdefault("build_lock", asyncio.Lock())
    state["build_seq"] = mine = state.get("build_seq", 0) + 1
    async with lock:
        if state["build_seq"] != mine:
            return
        await _draw_collection(container, title, library, name, state)


async def _draw_collection(container: ui.column, title: ui.column, library: Library,
                           name: str | None, state: dict[str, Any]) -> None:
    container.clear()
    title.clear()
    with container:
        if not name:
            _title(title, "Collection", "Select a collection")
            return
        # Read fresh rather than from the grid's copy: every control in here writes,
        # and a rebuild that redrew the values it just changed from a stale row would
        # show the edit undoing itself.
        rows = await run.io_bound(library.load_collections)
        row = next((entry for entry in rows if entry.get("name") == name), None)
        if row is None:
            _title(title, "Collection", "No longer in this hub")
            return
        kind = "Rule" if (row.get("type") or "") == "filter" else "Hand-picked"
        _title(title, row.get("name") or "", kind)

        members = await run.io_bound(library.collection_games, name)
        axes = await run.io_bound(library.filter_axes)
        context: dict[str, Any] = {"library": library, "collection": row,
                                   "members": members, "axes": axes, "state": state,
                                   "redraws": [], "dock": None}

        async def rebuild() -> None:
            await build_collection(container, title, library, name, state)

        context["rebuild"] = rebuild
        await _rail(context, "collection", state)


async def _rail(context: dict[str, Any], subject: str,
                state: dict[str, Any]) -> None:
    """The rail and the open section, for whatever subject the panel is about.

    Three regions, in reading order: which mode you are in, what that mode gives you to
    browse, and what you are working on. The outline must not scroll with what it
    points at, so this row is the fixed frame and only the body scrolls.

    One structure, presented two ways. Wide, the rows are a rail down the left and the
    work fills the column beside them. Narrow, they stack in order and the work falls
    under the row that opened it - an accordion, which is what a rail already is when
    everything is closed. The stylesheet decides which; nothing about the markup
    changes, so nothing has to be rebuilt on a drag.
    """
    section = chosen_section(state, subject)
    rows = sections_for(subject)
    body = None
    # The row count goes to the stylesheet because the wide layout needs a track
    # per row and then one that takes the rest - CSS cannot count its own children.
    with ui.element("div").classes("w-full grow min-h-0 hub-sections") \
            .style(f"--rows: {len(rows)}"):
        for item in rows:
            _section_row(context, item, item.key == section)
            if item.key != section:
                continue
            # The work sits immediately after the row it belongs to, which is what
            # makes the narrow case an accordion without a second layout.
            work = ui.element("div").classes("min-w-0 hub-section-work")
            if item.dock:
                work.classes(add="hub-has-dock")
                work.style(f"--dock-h: {state.get('dock_px', DOCK_PX)}px")
            with work:
                body = ui.column().classes("min-w-0 overflow-auto gap-0 "
                                           "hub-workbench-body")
                if item.dock:
                    ui.element("div").classes("hub-dock-grip") \
                        .tooltip("Drag to resize")
                    context["dock"] = ui.column().classes("min-w-0 gap-0 hub-dock")
                else:
                    context["dock"] = None
    if body is not None:
        with body:
            await _one_section(context, section)
        if context.get("dock") is not None:
            ui.run_javascript(_GRIP)


async def _one_section(context: dict[str, Any], key: str) -> None:
    """The chosen section's content. No heading - the row that opened it is the
    heading, and a second copy of the same words under it is furniture."""
    await next(item for item in SECTIONS if item.key == key).build(context)


def _section_row(context: dict[str, Any], section: Section, open_now: bool) -> None:
    """One section's name, which is both the rail entry and the accordion header.

    The name is text: a badge said nothing about a game's identity, and the sections
    still to come would each need a picture that means only itself. Words already do.

    The chevron is the exception, and it is not the same thing - it says the row opens,
    which is a fact about the control rather than a label for the section. Without it
    the stacked rows are four words with no sign that any of them do anything.
    """
    row = ui.row().classes("items-stretch gap-0 no-wrap hub-section-row")
    if open_now:
        row.classes(add="hub-section-on")
    with row:
        name = ui.row().classes("items-center grow min-w-0 hub-section-hit")
        with name:
            text = ui.label(section.label(context)).classes("hub-section-text truncate")
        # Shown only where the rows stack, because only there does one open under
        # another. Beside its content it would be pointing at nothing.
        with ui.row().classes("items-center hub-section-caret"):
            ui.icon("expand_more", size="18px")
    # The whole band, name and chevron alike - a header that opens on the word but
    # only closes on the arrow is a control with two rules to learn.
    row.on("click", lambda key=section.key: _toggle(context, key))

    async def relabel() -> None:
        # A count in the name has to follow the thing it counts.
        text.text = section.label(context)

    context["redraws"].append(relabel)


def _toggle(context: dict[str, Any], key: str) -> None:
    """Open this section, or close it if it is the one already open."""
    _choose(context, COLLAPSED if context["state"].get("section") == key else key)


def _choose(context: dict[str, Any], key: str) -> None:
    """Make it the section on screen. "" closes every one of them."""
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


async def _game_block(context: dict[str, Any]) -> None:
    """What the game is - the machine, not the file.

    Shown whichever subject is selected. A table belongs to a game, and the VPS match,
    the manufacturer and the theme are as true while you are looking at one of its files
    as they are otherwise. Substituting one for the other, which this used to do, threw
    away half of what somebody was looking at.
    """
    with ui.column().classes("gap-0 hub-form"):
        _identity_rows(context)


async def _table_block(context: dict[str, Any]) -> None:
    """What this table is - the file somebody built, and what it needs to run."""
    chosen = next((t for t in context["tables"] if t.get("id") == context["lens"]),
                  None)
    with ui.column().classes("gap-0 hub-form"):
        if chosen is None:
            ui.label("No table selected").classes("hub-help")
            return
        _table_rows(chosen, context)


async def _save_overrides(context: dict[str, Any], changes: dict[str, Any], *,
                          table: bool) -> None:
    """Write one field and rebuild. Off the loop: this is an HTTP call to our own
    process, and made on the event loop it blocks the server from answering it."""
    library = context["library"]
    try:
        if table:
            await run.io_bound(library.set_table_overrides, context["game_id"],
                               context["lens"], changes)
        else:
            await run.io_bound(library.set_game_overrides, context["game_id"], changes)
    except Exception as exc:
        ui.notify(f"Could not save: {exc}", type="negative")
        return
    await context["rebuild"]()


def _override(effective: str, found: str | None, source: str,
              save: Callable[[str], Any], *, shown: str | None = None,
              hint: str = "") -> Callable[[], None]:
    """One field the user may override, drawn into a fact row.

    A field the whole time. The read state and the edit state are one element, so there
    is nothing for the alignment to drift against and nothing moves on the first click.

    `found` is what the field would say with no override, or None where nothing but the
    user ever supplies one. Where there is a `found`, an amber revert appears exactly
    when the value differs from it, and typing that value back clears the override -
    so the mark's presence always means "this differs from the default".
    """
    current = effective if shown is None else shown

    def draw() -> None:
        with ui.element("div").classes("hub-fact-edit"):
            field = ui.input(value=current).props("dense borderless") \
                .classes("hub-edit-field")
            if hint:
                field.tooltip(hint)
            icon = ui.icon("undo").classes("hub-revert")
            if found is not None:
                target = f'"{found}"' if found else "empty"
                icon.tooltip(f"Revert to {target} - from {source}")
            icon.visible = found is not None and current != found
            held = {"value": current}

            async def commit() -> None:
                value = str(field.value or "").strip()
                if value == held["value"]:
                    return
                held["value"] = value
                # Sending the discovered value is how an override is cleared, so the
                # two cases are one request rather than a delete and a write.
                await save("" if found is not None and value == found else value)

            def cancel() -> None:
                field.value = held["value"]
                field.run_method("blur")

            async def revert() -> None:
                held["value"] = found or ""
                await save("")

            field.on("blur", commit)
            field.on("keydown.enter", lambda: field.run_method("blur"))
            field.on("keydown.escape", cancel)
            icon.on("click", revert)

    return draw


def _identity_rows(context: dict[str, Any]) -> None:
    game = context["game"]
    # The folder is the tail, not the whole path: the library root is the same for
    # every game and repeating it costs the only column that has to hold a name.
    folder = str(game.get("folder") or "")
    found = game.get("discovered") or {}
    overrides = game.get("overrides") or {}

    def save(key: str):
        async def write(value: str) -> None:
            await _save_overrides(context, {key: value}, table=False)
        return write

    _rows(ui, [
        (HEADING, "The machine"),
        ("Name", _override(game.get("name") or "", found.get("name") or "",
                           "VPS", save("alt_title"))),
        ("Made by", f"{game.get('manufacturer') or '?'} "
                    f"{game.get('year') or ''}".strip()),
        ("Type", game.get("type") or "-"),
        ("Themes", ", ".join(game.get("themes") or []) or "-"),
        ("ROM", game.get("rom") or "-"),
        (HEADING, "Matched against"),
        ("VPS id", _override(game.get("vps_id") or "", found.get("vps_id") or "",
                             "VPS", save("alt_vps_id"),
                             shown=overrides.get("alt_vps_id") or game.get("vps_id"))),
        (HEADING, "On this cabinet"),
        # Nothing supplies this but the user, so there is nothing to revert to - empty
        # means the frontend's own default, which is what clearing it says.
        ("DOF event", _override(overrides.get("frontend_dof_event") or "", None,
                                "", save("frontend_dof_event"),
                                hint="Empty uses the default effect")),
        ("Folder", PurePosixPath(folder).name or folder or "-"),
    ])


def _table_rows(table: dict[str, Any],
                context: dict[str, Any] | None = None) -> None:
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

    # Grouped, and each group carries the actions that work on it. The groups are the
    # ranking: a version is read constantly and a hash almost never.
    script = ((table.get("assets") or {}).get("script") or {})
    features = table.get("features") or {}
    overrides = (table.get("overrides") or {}) if context else {}

    entries: list[tuple[Any, Any]] = []
    if context is not None:
        entries += _attention(table)

    entries += [
        (HEADING, "Identity"),
        ("File", table.get("filename") or "-"),
        ("Version", table.get("version") or "-"),
        ("Author", ", ".join(table.get("authors") or []) or "-"),
    ]
    if context is not None:
        entries += [(FULL, _play_action(context, table))]
    entries += [
        (HEADING, "Plays with"),
        ("Application", apps.app_name(table.get("app"))),
        ("ROM", _rom_state(pinmame, rom)),
    ]
    if features:
        # Under "Plays with", not a group of its own: nFozzy, SSF and FlexDMD are all
        # answers to how this table plays, and the row label already says it.
        entries += [("Features", lambda: _feature_chips(features))]
    if context is not None:
        entries += _table_override_rows(context, table, overrides)

    entries += [(HEADING, "Status")]
    if context is not None:
        entries += _library_rows(context, table)
    else:
        entries += [
            ("Default", "Yes" if table.get("default") else "No"),
            ("In frontend", "Hidden" if table.get("hidden") else "Shown"),
        ]
    entries += [("File on disk",
                 _state("Present", "on") if table.get("available")
                 else _state("Missing", "bad"))]

    # Last and quiet: identifiers are looked up, not read. They earn a place on the
    # panel and not a place near the top of it.
    entries += [
        (HEADING, "Reference"),
        ("VBScript", _state("Extracted", "on") if script.get("resolution") != "none"
                     else _state("Not extracted", "off")),
        ("File hash", table.get("file_hash") or "-"),
        ("VBScript hash", table.get("vbs_hash") or "-"),
    ]
    _rows(ui, entries)


def _state(text: str, level: str, beside: str = "") -> Callable[[], None]:
    """A state the panel found and the user cannot set, as a chip.

    The counterpart of the switch: a switch is a setting, a chip is a finding, and the
    shape is what says which. The level is what the absence *costs* - `on` for the
    affirmative, `off` where absence is the ordinary case, `warn` where it is worth
    fixing, `bad` where it stops the table working. Each fact keeps its own words,
    because a rom is installed, a script is extracted and a file is merely present.
    """
    def draw() -> None:
        with ui.element("div").classes("hub-fact-edit"):
            if beside:
                ui.label(beside).classes("hub-fact-value truncate min-w-0") \
                    .tooltip(beside)
            ui.label(text).classes(f"hub-tier hub-tier--{level}")

    return draw


def _rom_state(pinmame: dict[str, Any], rom: str) -> Any:
    """The rom, and whether it is actually there.

    The chain resolves aliases and audits the install, so the name alone is half an
    answer: what anybody wants of a rom is whether it will run.
    """
    installed = pinmame.get("installed")
    if not pinmame.get("effective") or installed is None:
        return rom
    return _state("Installed" if installed else "Not installed",
                  "on" if installed else "warn", beside=rom)


def _attention(table: dict[str, Any]) -> list[tuple[Any, Any]]:
    """What is wrong with this table, before anything that is merely true about it.

    A workbench leads with the thing you would act on. Only real faults: hidden and
    not-default are choices somebody made, not problems, and listing them here would
    teach the block to be ignored.
    """
    pinmame = (table.get("dependencies") or {}).get("pinmame") or {}
    flex = (table.get("dependencies") or {}).get("flexdmd") or {}
    faults = []
    if not table.get("available"):
        faults.append("The .vpx is not on disk")
    if pinmame.get("effective") and pinmame.get("installed") is False:
        faults.append(f"ROM {pinmame['effective']} is not installed")
    if flex.get("detected") and not flex.get("installed"):
        faults.append("The script uses FlexDMD, which is not installed")
    if not faults:
        return []

    def draw() -> None:
        with ui.element("div").classes("hub-attention"):
            ui.icon("error_outline").classes("hub-attention-icon")
            with ui.column().classes("gap-0 min-w-0"):
                for fault in faults:
                    ui.label(fault).classes("hub-attention-line")

    return [(FULL, draw)]


def _library_rows(context: dict[str, Any],
                  table: dict[str, Any]) -> list[tuple[Any, Any]]:
    """Which table this game offers, and whether the frontend shows it.

    Both are the user's to change, so the verb sits beside the fact it changes.
    """
    library, game_id = context["library"], context["game_id"]
    table_id = str(table.get("id") or "")
    is_default = bool(table.get("default"))
    hidden = bool(table.get("hidden"))

    async def act(call: Callable[..., Any], *args: Any, done: str = "") -> None:
        try:
            await run.io_bound(call, *args)
        except Exception as exc:
            ui.notify(f"Could not do that: {exc}", type="negative")
            return
        if done:
            ui.notify(done, type="positive")
        await context["rebuild"]()

    def default_row() -> None:
        # On but not off: exactly one table is the game's default, so this is turned on
        # by turning another one on. Disabled rather than absent, or the row a table
        # already holds would be the one row with no control in it.
        _switch(is_default,
                lambda _: act(library.set_default_table, game_id, table_id,
                              done="Now the game's default"),
                disabled=is_default,
                hint=("This is the one the game offers" if is_default
                      else "Offer this table first"))

    def frontend_row() -> None:
        _switch(not hidden,
                lambda event: act(library.set_table_hidden, game_id, table_id,
                                  not bool(event.value)),
                hint="Offer this table in the frontend")

    return [("Default table for game", default_row),
            ("Frontend visible", frontend_row)]


def _switch(value: bool, on_change: Callable[[Any], Any], *,
            disabled: bool = False, hint: str = "") -> None:
    """Every binary value on this panel, drawn the same way.

    One control for one kind of value: a switch for a yes or no, a select where there
    is a list to pick from. Mixing a checkbox, a text state and a button across three
    booleans makes the reader work out three times what one convention would say once.
    """
    # Green, the same token a present chip takes: on means the same thing whether the
    # panel found it or the user set it, and the control's shape already says which.
    switch = ui.switch(value=value, on_change=on_change) \
        .props("dense color=positive").classes("hub-fact-switch")
    if disabled:
        switch.disable()
    if hint:
        switch.tooltip(hint)


def _play_action(context: dict[str, Any], table: dict[str, Any]) -> Callable[[], None]:
    """Play this file, not the game's default - the panel is about this one."""
    filename = str(table.get("filename") or "")

    async def go() -> None:
        try:
            await run.io_bound(context["library"].launch, context["game_id"], filename)
        except Exception as exc:
            ui.notify(f"Could not launch: {exc}", type="negative")

    def draw() -> None:
        with ui.row().classes("items-center gap-2"):
            button = ui.button("Play this table", icon="play_arrow", on_click=go) \
                .props("flat dense no-caps size=sm").classes("hub-action")
            if not table.get("available"):
                button.disable()
                button.tooltip("The .vpx is not on disk")

    return draw


def _table_override_rows(context: dict[str, Any], table: dict[str, Any],
                         overrides: dict[str, Any]) -> list[tuple[Any, Any]]:
    """What the user says about this file. None of these has a discovered value - each
    falls back to a setting that applies everywhere - so empty is the revert."""

    def save(key: str):
        async def write(value: Any) -> None:
            await _save_overrides(context, {key: value}, table=True)
        return write

    async def toggle(event: Any) -> None:
        await _save_overrides(context, {"delete_nvram_on_close": bool(event.value)},
                              table=True)

    def nvram() -> None:
        _switch(bool(overrides.get("delete_nvram_on_close")), toggle,
                hint="Remove the NVRAM file when this table exits")

    return [
        ("Launcher", _override(overrides.get("alt_launcher") or "", None, "",
                               save("alt_launcher"),
                               hint="Empty uses the configured Visual Pinball binary")),
        ("Clear NVRAM on exit", nvram),
    ]


# Named for the thing, not for the .info key. PinMAME is left out: it is not a script
# flourish like the rest, and the ROM row above already answers for it in detail.
FEATURE_LABELS = {
    "nfozzy": "nFozzy", "fleep": "Fleep", "ssf": "SSF", "lut": "LUT",
    "scorbit": "Scorbit", "fastflips": "FastFlips", "flexdmd": "FlexDMD",
}


def _feature_chips(features: dict[str, Any]) -> None:
    """What the table's script was seen to use.

    Three states, because a table nobody has parsed yet answers null for every one of
    them and that is not the same as answering no. Same forms as a media tier: filled
    for what is here, quiet for what is not, dashed for not yet known.
    """
    with ui.element("div").classes("hub-chips"):
        for key, label in FEATURE_LABELS.items():
            present = features.get(key)
            style = ("hub-tier--on" if present
                     else "hub-tier--unknown" if present is None
                     else "hub-tier--off")
            ui.label(label).classes(f"hub-tier {style}") \
                .tooltip("In the script" if present else
                         "Not parsed yet" if present is None else "Not used")


def _tables_label(context: dict[str, Any]) -> str:
    tables = context["tables"]
    gone = [table for table in tables if table.get("absent_since")]
    label = f"Tables ({len(tables)})"
    return label + (f" - {len(gone)} not on disk" if gone else "")


async def _forget_table(context: dict[str, Any], table: dict[str, Any]) -> None:
    """Drop a gone table's record, once the user says it is not coming back.

    Confirmed because it is the only destructive thing on this surface, and the dialog
    names the file rather than the id - the id is ours, the filename is what the user
    recognizes. The hub refuses the request outright if the .vpx is back, so a stale
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


def _rows(target: Any, entries: Sequence[tuple[Any, Any]]) -> None:
    """The facts of one section, as (label, value) pairs.

    One grid for all of them, not a row each, so the label column is the width of the
    longest label - a fixed one is a guess that truncates as soon as the type grows.
    A row whose value is not text passes a callable and draws its own; it has to be in
    *this* grid, or it sizes a label column of its own and its value starts somewhere
    else entirely. `HEADING` and `FULL` are the same story: a group's title and its
    actions span both columns here rather than living in a grid of their own, which is
    what keeps every group's values on one left edge.

    `min-w-0` is what lets the value shrink: a grid item refuses to go below its
    content width without it, and the row wraps instead of ellipsing.
    """
    with target.element("div").classes("hub-facts"):
        for label, value in entries:
            if label is HEADING:
                target.label(str(value)).classes("hub-fact-heading")
                continue
            if label is FULL:
                with target.element("div").classes("hub-fact-full"):
                    value()
                continue
            target.label(label).classes("hub-fact-label")
            if callable(value):
                value()
                continue
            target.label(str(value)).classes("hub-fact-value truncate min-w-0") \
                .tooltip(str(value))


# --- collections ------------------------------------------------------------------
# A collection's rail. Nothing here is shared with a game's: the two subjects have no
# section in common, which is what section 11 means by the rail being a function of
# (nav node, subject) rather than one list everything appears in.


def _collection(context: dict[str, Any]) -> dict[str, Any]:
    return context["collection"]


async def _collection_details(context: dict[str, Any]) -> None:
    """What the collection is, and how it hands its games out."""
    row = _collection(context)
    manual = (row.get("type") or "") == "manual"
    # One control per row. Two side by side overflowed the value column at the panel's
    # own width and wrapped out from under it, which is the whole reason the facts grid
    # has one label column in the first place.
    ordered = _order_control(context, row)
    entries: list[tuple[Any, Any]] = [
        (HEADING, "This list"),
        ("Kind", "An explicit list of games" if manual
         else "Built from the library by a rule"),
        ("Ordered by", ordered["by"]),
    ]
    if (row.get("order_by") or DEFAULT_ORDER_BY) != MANUAL_ORDER:
        # Not a setting that happens to be off: a direction on a hand-arranged list is
        # not a question, so the row is absent rather than disabled.
        entries.append(("Direction", ordered["direction"]))
    entries.append(("Cap", _limit_control(context, row)))
    with ui.column().classes("gap-0 hub-form"):
        _rows(ui, entries)


def _order_control(context: dict[str, Any],
                   row: dict[str, Any]) -> dict[str, Callable[[], None]]:
    """How the frontend hands this collection out, as two drawable rows.

    `manual` is only offered where there is a member array to be the order - a filter
    collection has no stored list, so "as arranged" would name something that does not
    exist.
    """
    manual = (row.get("type") or "") == "manual"
    choices = {MANUAL_ORDER: "As arranged", **SORT_LABELS} if manual else dict(SORT_LABELS)
    current = row.get("order_by") or DEFAULT_ORDER_BY
    held: dict[str, Any] = {"by": current if current in choices else DEFAULT_ORDER_BY,
                            "direction": row.get("direction") or "asc"}

    async def save() -> None:
        await _patch(context, {"order_by": held["by"], "direction": held["direction"]})

    # Each handler is a coroutine handed over whole. A lambda returning a *tuple* that
    # happens to contain one - `lambda: (held.update(...), save())` - is not awaitable,
    # so nicegui drops it and the control changes on screen while nothing is written.
    def draw_by() -> None:
        field = ui.select(choices, value=held["by"]).props("dense outlined") \
            .classes("w-full min-w-0")

        async def changed() -> None:
            held["by"] = field.value
            await save()

        field.on_value_change(changed)

    def draw_direction() -> None:
        field = ui.select(DIRECTION_LABELS, value=held["direction"]) \
            .props("dense outlined").classes("w-full min-w-0")

        async def changed() -> None:
            held["direction"] = field.value
            await save()

        field.on_value_change(changed)

    return {"by": draw_by, "direction": draw_direction}


def _limit_control(context: dict[str, Any],
                   row: dict[str, Any]) -> Callable[[], None]:
    """How many the frontend is handed. Empty means all of them.

    Cleared with its own flag rather than by sending null: absent and null are the same
    thing over JSON, so there would be no way to say "lift it".
    """
    limit = row.get("limit")

    async def save(value) -> None:
        if value in (None, ""):
            await _patch(context, {"clear_limit": True})
            return
        try:
            await _patch(context, {"limit": max(1, int(value))})
        except (TypeError, ValueError):
            ui.notify("A cap is a whole number of games", type="warning")

    def draw() -> None:
        field = ui.number(value=limit, min=1, format="%d", placeholder="All") \
            .props("dense outlined clearable").classes("w-full min-w-0")
        field.on_value_change(lambda: save(field.value))

    return draw


async def _patch(context: dict[str, Any], changes: dict[str, Any]) -> None:
    library = context["library"]
    try:
        await run.io_bound(library.patch_collection, _collection(context)["name"],
                           changes)
    except Exception as exc:
        ui.notify(f"Could not save: {exc}", type="negative")
        return
    await context["rebuild"]()


def _members_label(context: dict[str, Any]) -> str:
    got = context.get("members")
    return "Games" if got is None else f"Games ({len(got)})"


async def _collection_members(context: dict[str, Any]) -> None:
    """What is in it now.

    Resolved, never the stored array: a member naming a game this library does not have
    resolves to nothing, and reporting the stored count instead would tell somebody
    they have five games in a list that hands out none.
    """
    row = _collection(context)
    manual = (row.get("type") or "") == "manual"
    members = context.get("members") or []
    stored = row.get("game_count")
    with ui.column().classes("gap-0 hub-form w-full"):
        if manual and stored is not None and stored != len(members):
            ui.label(f"{stored} games are stored here but {len(members)} are in this "
                     "library. The rest name games it does not have.") \
                .classes("hub-help text-warning mb-2")
        if not manual:
            ui.label("These follow the rule. Edit the rule to change them.") \
                .classes("hub-help mb-2")
        if not members:
            ui.label("Nothing in it yet." if manual
                     else "The rule matches nothing right now.").classes("hub-help")
        # Only where the order is the thing being read. Arrows on a list the frontend
        # sorts by title would move something and change nothing anyone can see.
        arrange = manual and (row.get("order_by") or "") == MANUAL_ORDER
        for index, game in enumerate(members):
            with ui.row().classes("items-center gap-2 w-full no-wrap py-1 "
                                  "hub-index-item"):
                ui.label(game.get("name") or "").classes("text-xs grow min-w-0 truncate")
                if arrange:
                    ui.button(icon="keyboard_arrow_up",
                              on_click=lambda i=index: _move_member(context, members,
                                                                    i, -1)) \
                        .props("flat dense round size=sm") \
                        .set_enabled(index > 0)
                    ui.button(icon="keyboard_arrow_down",
                              on_click=lambda i=index: _move_member(context, members,
                                                                    i, 1)) \
                        .props("flat dense round size=sm") \
                        .set_enabled(index < len(members) - 1)
                if manual:
                    ui.button(icon="close",
                              on_click=lambda g=game: _drop_member(context, g)) \
                        .props("flat dense round size=sm").tooltip("Take out of this list")
        if manual:
            _add_member_control(context, members)


def _add_member_control(context: dict[str, Any], members: list[dict]) -> None:
    """Add by name, from what is not already in it.

    A select rather than a dialog: adding several in a row is the normal case, and a
    dialog per game turns that into a chore.
    """
    here = {game.get("id") for game in members}
    choices = {game["id"]: game.get("name") or game["id"]
               for game in context["library"].games if game["id"] not in here}
    if not choices:
        return
    picker = ui.select(choices, with_input=True, label="Add a game") \
        .props("dense outlined").classes("w-full mt-3")

    async def add() -> None:
        if not picker.value:
            return
        library = context["library"]
        try:
            await run.io_bound(library.add_to_collection,
                               _collection(context)["name"], picker.value)
        except Exception as exc:
            ui.notify(f"Could not add it: {exc}", type="negative")
            return
        await context["rebuild"]()

    picker.on_value_change(add)


async def _move_member(context: dict[str, Any], members: list[dict],
                       index: int, step: int) -> None:
    """Move one game within the arrangement.

    Sent as the whole ordered list, which is what the route takes - atomic, and no
    index arithmetic on either side of the wire.
    """
    order = [game["id"] for game in members]
    target = index + step
    if not 0 <= target < len(order):
        return
    order[index], order[target] = order[target], order[index]
    library = context["library"]
    try:
        await run.io_bound(library.set_collection_order,
                           _collection(context)["name"], order)
    except Exception as exc:
        ui.notify(f"Could not move it: {exc}", type="negative")
        return
    await context["rebuild"]()


async def _drop_member(context: dict[str, Any], game: dict[str, Any]) -> None:
    library = context["library"]
    try:
        await run.io_bound(library.remove_from_collection,
                           _collection(context)["name"], game["id"])
    except Exception as exc:
        ui.notify(f"Could not remove it: {exc}", type="negative")
        return
    await context["rebuild"]()


async def _collection_rule(context: dict[str, Any]) -> None:
    """The criteria, one control per axis, read from the registry rather than listed.

    A new axis appears here the moment core declares one - section 2.15 makes the
    registry the only place an axis is named, and a hand-written form here would be a
    second place that goes stale.
    """
    row = _collection(context)
    filters = dict(row.get("filters") or {})
    axes = context.get("axes") or []
    fields: dict[str, Any] = {}

    async def save() -> None:
        wanted = {name: control.value for name, control in fields.items()}
        await _patch(context, {"filters": {**filters, **wanted}})

    with ui.column().classes("gap-0 hub-form w-full"):
        if (row.get("type") or "") == "manual":
            # Offered, not done quietly: sending filters discards the hand-picked list,
            # so it is only ever something somebody asked for.
            ui.label("This list is hand-picked, so it has no rule.").classes("hub-help")
            ui.label("Giving it one replaces the games in it with whatever the rule "
                     "matches. The list itself is not kept.") \
                .classes("hub-help text-warning mt-1 mb-2")
            ui.button("Give it a rule instead",
                      on_click=lambda: _patch(context, {"filters": {}})) \
                .props("flat dense no-caps size=sm").classes("hub-action")
            return
        ui.label("A rule is applied to the library, never to another collection.") \
            .classes("hub-help mb-2")
        entries: list[tuple[Any, Any]] = []
        for axis in axes:
            name = axis.get("name") or ""
            # The pair to `rating`, not an axis anybody sets on its own.
            if name == "rating_or_higher":
                continue
            entries.append((_axis_label(axis), _axis_control(axis, filters, fields,
                                                             save)))
        _rows(ui, entries)


def _axis_label(axis: dict[str, Any]) -> str:
    """What to call an axis in a label column.

    Its name, not its `summary`: the registry's summaries are sentences written to
    explain an axis ("First letter of the title, as sorted"), and a column of sentences
    is not a column of labels. The sentence is worth having, so it becomes the tooltip.
    """
    return str(axis.get("name") or "").replace("_", " ").capitalize()


def _axis_control(axis: dict[str, Any], filters: dict[str, Any],
                  fields: dict[str, Any], save: Callable[[], Any]) -> Callable[[], None]:
    """One control per axis kind. "All" is unconstrained, which is the vocabulary the
    filter engine already uses - kept rather than translated, so what a client sends is
    what it sees."""
    name = str(axis.get("name") or "")
    kind = str(axis.get("kind") or "")
    values = list(axis.get("values") or [])
    summary = str(axis.get("summary") or "")

    def draw() -> None:
        if kind == "flag":
            # Three states, not two: absent says nothing about play, true and false are
            # both criteria. A switch could only ever say two of the three.
            current = filters.get(name)
            control = ui.select({"": "Any", "yes": "Yes", "no": "No"},
                                value={True: "yes", False: "no"}.get(current, "")) \
                .props("dense outlined").classes("w-full min-w-0")
            fields[name] = _Mapped(control, {"": None, "yes": True, "no": False})
        else:
            control = ui.select(["All", *values],
                                value=str(filters.get(name) or "All"),
                                with_input=len(values) > 12) \
                .props("dense outlined").classes("w-full min-w-0")
            fields[name] = control
        if summary:
            control.tooltip(summary)
        control.on_value_change(save)

    return draw


class _Mapped:
    """A control whose stored value is not the one on screen. `.value` reads through
    the map, so the caller collecting a filter block does not special-case a kind."""

    def __init__(self, control: Any, mapping: dict[Any, Any]) -> None:
        self._control = control
        self._mapping = mapping

    @property
    def value(self) -> Any:
        return self._mapping.get(self._control.value, self._control.value)


SECTIONS: tuple[Section, ...] = (
    # The game first, then the file: a table belongs to a game, and reading down is
    # reading from the thing that contains to the thing contained.
    Section("game_details", lambda _: "Game Details", _game_block),
    Section("table_details", lambda _: "Table Details", _table_block,
            subjects=frozenset({"table"})),
    Section("media", _media_label, _media_block, dock=True),
    Section("tables", _tables_label, _tables_block),
    Section("collection_details", lambda _: "Details", _collection_details,
            subjects=frozenset({"collection"})),
    Section("collection_members", _members_label, _collection_members,
            subjects=frozenset({"collection"})),
    Section("collection_rule", lambda _: "Rule", _collection_rule,
            subjects=frozenset({"collection"})),
)
