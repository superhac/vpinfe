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
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import quote

from nicegui import run, ui

from common.games import apps, asset_registry
from common.games.asset_registry import ALWAYS_KEPT as _ALWAYS_KEPT
from common.games.collection_filters import UNCONSTRAINED
from common.games.collection_store import (
    DEFAULT_ORDER_BY,
    DIRECTION_LABELS,
    MANUAL_ORDER,
    SORT_LABELS,
)
from common.labels import field_label, humanize
from common.media_specs import media_family, media_label_map
from common.online import vps_kinds
from hubui import (
    candidates,
    confirm,
    deeplink,
    game_tables,
    media_ownership,
    mediamap,
    mediasource,
    mediaview,
    stars,
)
from hubui import features as table_features
from hubui.api import HubError
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

# Dragging one member to a new place. Pointer events, not HTML5 drag-and-drop, for the
# reason the dock grip uses them: HTML5 drag fires no move events over its own source
# and is inert on touch.
# The dock is rebuilt on every write, so its scroll position has to be carried across
# by hand. Remembered on the window rather than in the panel's state: the value changes
# on every scroll frame and none of those are worth a round trip to Python.
_KEEP_SCROLL = """
(() => {
  const dock = document.querySelector('.hub-dock');
  if (!dock) return;
  const held = window.__hubDockTop || (window.__hubDockTop = {});
  const key = '%s';
  if (held[key]) dock.scrollTop = held[key];
  if (dock.dataset.scrollWired) return;
  dock.dataset.scrollWired = '1';
  dock.addEventListener('scroll', () => { held[key] = dock.scrollTop; },
                        {passive: true});
})()
"""

_ARRANGE = """
(() => {
  const list = document.querySelector('.hub-member-list');
  if (!list || list.dataset.wired) return;
  list.dataset.wired = '1';

  // The dock scrolls, not the window, so the edges that mean "keep going" are its.
  const scroller = (() => {
    let el = list.parentElement;
    while (el && el !== document.body) {
      const flow = getComputedStyle(el).overflowY;
      if ((flow === 'auto' || flow === 'scroll') && el.scrollHeight > el.clientHeight) {
        return el;
      }
      el = el.parentElement;
    }
    return document.scrollingElement;
  })();

  const all = () => [...list.querySelectorAll('.hub-member-row')];
  const settled = () => all().filter((row) => !row.classList.contains('hub-dragging'));
  const positionOf = (row) => all().indexOf(row);

  // A dead middle and a ramp into the last sixth: a fixed rate is unusable at five
  // rows and too slow at forty, so speed follows how far into the edge you are.
  const EDGE = 0.16, FASTEST = 20;
  let drag = null, grab = null, press = null;

  function lift(row, y) {
    const box = row.getBoundingClientRect();
    const slot = document.createElement('div');
    slot.className = 'hub-drop-slot';
    slot.style.height = box.height + 'px';
    row.parentNode.insertBefore(slot, row);
    drag = {row: row, slot: slot, from: positionOf(row), anchor: row.nextSibling,
            hold: y - box.top, left: box.left, width: box.width, y: y};
    row.classList.add('hub-dragging');
    row.style.width = box.width + 'px';
    place(y);
    drag.frame = requestAnimationFrame(tick);
  }

  // The lifted row follows the pointer and nothing else moves; the slot is the only
  // thing that shifts, so the list you are aiming at holds still while you aim.
  function place(y) {
    if (!drag) return;
    drag.y = y;
    drag.row.style.top = (y - drag.hold) + 'px';
    drag.row.style.left = drag.left + 'px';
    for (const row of settled()) {
      const box = row.getBoundingClientRect();
      if (y < box.top || y > box.bottom) continue;
      const past = y > box.top + box.height / 2;
      list.insertBefore(drag.slot, past ? row.nextSibling : row);
      break;
    }
  }

  function tick() {
    if (!drag) return;
    const box = scroller.getBoundingClientRect();
    const zone = Math.max(24, box.height * EDGE);
    let speed = 0;
    if (drag.y < box.top + zone) {
      speed = -FASTEST * Math.min(1, (box.top + zone - drag.y) / zone);
    } else if (drag.y > box.bottom - zone) {
      speed = FASTEST * Math.min(1, (drag.y - (box.bottom - zone)) / zone);
    }
    if (speed) { scroller.scrollTop += speed; place(drag.y); }
    drag.frame = requestAnimationFrame(tick);
  }

  function drop(keep) {
    if (!drag) return;
    cancelAnimationFrame(drag.frame);
    const row = drag.row, slot = drag.slot, from = drag.from;
    row.classList.remove('hub-dragging');
    row.style.width = row.style.top = row.style.left = '';
    if (keep) { slot.parentNode.insertBefore(row, slot); }
    else { list.insertBefore(row, drag.anchor); }
    slot.remove();
    const to = positionOf(row);
    drag = null;
    // Only when it moved: a click on the handle would otherwise write the list back
    // unchanged and rebuild the panel under the cursor.
    if (keep && to >= 0 && to !== from) emitEvent('hub_member_moved', {from: from, to: to});
  }

  list.addEventListener('pointerdown', (e) => {
    const row = e.target.closest('.hub-member-row');
    if (!row) return;
    if (e.target.closest('.hub-drag-handle')) {
      e.preventDefault();
      try { e.target.setPointerCapture(e.pointerId); } catch (err) {}
      lift(row, e.clientY);
      return;
    }
    // Touch has no hover and no second button, so the row itself is the grab target
    // after a hold. Cancelled by any real movement, which is a scroll.
    if (e.pointerType === 'touch') {
      press = {row: row, y: e.clientY,
               timer: setTimeout(() => { press = null; lift(row, e.clientY); }, 420)};
    }
  });
  document.addEventListener('pointermove', (e) => {
    if (press && Math.abs(e.clientY - press.y) > 6) {
      clearTimeout(press.timer); press = null;
    }
    if (drag) { e.preventDefault(); place(e.clientY); }
  }, {passive: false});
  document.addEventListener('pointerup', () => {
    if (press) { clearTimeout(press.timer); press = null; }
    drop(true);
  });
  document.addEventListener('pointercancel', () => drop(false));

  // The same move without a pointer. Grab, step, drop - so arranging is reachable from
  // the keyboard, which a drag on its own never is.
  list.addEventListener('keydown', (e) => {
    const handle = e.target.closest('.hub-drag-handle');
    if (!handle) return;
    const row = handle.closest('.hub-member-row');
    if (e.key === ' ' || e.key === 'Enter') {
      e.preventDefault();
      if (grab && grab.row === row) {
        row.classList.remove('hub-grabbed');
        const to = positionOf(row), from = grab.from;
        grab = null;
        if (to >= 0 && to !== from) emitEvent('hub_member_moved', {from: from, to: to});
      } else {
        grab = {row: row, from: positionOf(row), anchor: row.nextSibling};
        row.classList.add('hub-grabbed');
      }
    } else if (grab && grab.row === row && (e.key === 'ArrowUp' || e.key === 'ArrowDown')) {
      e.preventDefault();
      const rows = all(), at = rows.indexOf(row);
      const next = e.key === 'ArrowUp' ? at - 1 : at + 1;
      if (next < 0 || next >= rows.length) return;
      list.insertBefore(row, e.key === 'ArrowUp' ? rows[next] : rows[next].nextSibling);
      row.scrollIntoView({block: 'nearest'});
      handle.focus();
    } else if (e.key === 'Escape' && grab && grab.row === row) {
      e.preventDefault();
      list.insertBefore(row, grab.anchor);
      row.classList.remove('hub-grabbed');
      grab = null;
    }
  });
})()
"""

# Where a fresh client lands, per rail. Identity, because selecting a row is usually
# navigation rather than curation: the first question a selection asks is what this is,
# and the answer is also where the things you can do to it live.
#
# Per rail rather than one value, because a rail declares its own landing place - and a
# table selected on purpose should not open on the machine that contains it.
DEFAULT_SECTION = {"game": "game_details", "table": "table_details",
                   # Contents, not Details: a collection is opened to see
                   # what is in it far more often than to rename it.
                   "collection": "collection_contents"}
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
    if game_id is None:
        _blank(container, title, "Game Details", "Select a game")
        return
    game = next((entry for entry in library.games if entry["id"] == game_id), None)
    if game is None:
        _blank(container, title, "Game Details", "Not in this library")
        return
    # Off the loop, always. This is an HTTP call to our own process: made on the
    # event loop it blocks the server from answering it, the request times out
    # after 15s, and the browser reports the socket as lost rather than slow.
    #
    # And read *before* clearing. Clearing first left the panel empty for the whole
    # round trip, which after a write reads as the panel flashing black - the write,
    # the reread and the redraw are one act to the person who asked for it.
    tables = await run.io_bound(library.tables_for, game_id)

    container.clear()
    title.clear()
    with container:
        made = f"{game.get('manufacturer') or '?'} {game.get('year') or ''}"
        _title(title, game.get("name") or "", made)
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


def _blank(container: ui.column, title: ui.column, heading: str, said: str) -> None:
    """The panel with nothing to show. Its own helper so the drawing paths can read
    their subject before clearing, and still say this when there is none."""
    container.clear()
    title.clear()
    with container:
        _title(title, heading, said)


async def _draw_collection(container: ui.column, title: ui.column, library: Library,
                           name: str | None, state: dict[str, Any]) -> None:
    if not name:
        _blank(container, title, "Collection", "Select a collection")
        return
    # Read fresh rather than from the grid's copy: every control in here writes,
    # and a rebuild that redrew the values it just changed from a stale row would
    # show the edit undoing itself.
    #
    # All of it before the container is cleared. Clearing first held the panel empty
    # across three round trips, which is the black flash after changing a member's
    # table: the old panel stays up now until the new one is ready to replace it.
    rows = await run.io_bound(library.load_collections)
    row = next((entry for entry in rows if entry.get("name") == name), None)
    if row is None:
        _blank(container, title, "Collection", "No longer in this hub")
        return
    # Independent of each other, so one wait rather than two.
    membership, axes = await asyncio.gather(
        run.io_bound(library.collection_members, name),
        run.io_bound(library.filter_axes))

    container.clear()
    title.clear()
    with container:
        kind = ("Dynamic collection" if (row.get("type") or "") == "filter"
                else "Manual collection")
        _title(title, row.get("name") or "", kind)
        # The rule being edited, which is not always the rule that is stored. Held on
        # the client rather than in this build of the panel, so a section change or a
        # redraw does not discard an edit in progress.
        drafts = state.setdefault("collection_drafts", {})
        context: dict[str, Any] = {"library": library, "collection": row,
                                   "membership": membership, "axes": axes,
                                   "state": state, "draft": drafts.setdefault(name, {}),
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
    # The Tables grid is a place now, so going to one file is going there - section 16.1.
    state["view"] = "tables"
    state["table"] = table_id
    deeplink.sync(state)
    asyncio.create_task(context["rebuild"]())


def _table_line(table: dict[str, Any]) -> str:
    """Which of a game's tables this is. One form, owned by `subject`.

    The header is the one place a long filename cannot ellipse gracefully, so the
    fallback is trimmed from the end - where the part that separates two tables of a
    game sits.
    """
    said = game_tables.table_name(table)
    return said if said != str(table.get("filename") or "") \
        else _tail(said, 40)


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
        offered = await run.io_bound(_offered_media, context)
        kept = await run.io_bound(_kept_kinds, context, "media")
        holder.clear()
        with holder:
            mediamap.build(entries, _prefix(game_id, table_id),
                           on_pick=lambda kind: _pick_slot(context, kind, draw),
                           selected=context["slot"]["kind"],
                           overrides=overrides, offered=offered, kept=kept)
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


def _kept_kinds(context: dict[str, Any], family: str) -> set[str] | None:
    """The kinds this library collects, or None where the answer cannot be had.

    None rather than an empty set, and the difference matters: filtering to an empty
    set blanks the surface, which is what a config the hub could not read would
    otherwise do. Empty is folded into None for the same reason - a library keeping no
    kinds at all is not a state anybody can be in, and every way of reaching it here is
    a failure to read rather than an answer.

    Narrow on purpose. A blanket except here swallowed a missing attribute and the
    filter silently did nothing, which looks exactly like a library that keeps
    everything - the one failure this cannot afford to be quiet about.
    """
    try:
        return set(context["library"].kept_kinds()[family]) or None
    except (HubError, OSError):
        return None


def _offered_media(context: dict[str, Any]) -> dict[str, int]:
    """What the catalog lists for this game's empty slots.

    Swallowed on failure rather than taken as zero being reported: the map is about the
    library, and a catalog that cannot be reached should mark nothing rather than say
    the catalog has nothing.
    """
    try:
        return context["library"].offered_media(context["game_id"])
    except Exception:
        return {}


def _pick_slot(context: dict[str, Any], kind: str, draw) -> None:
    """Pick a slot to see the detail of. Clicking the picked one again does nothing.

    It used to put the panel away, which made one control mean two things and cost the
    selection to a mis-click. The detail sits beside the map rather than over it, so
    there is nothing to dismiss - a slot stays picked until another is.
    """
    slot = context["slot"]
    if slot["kind"] == kind:
        return
    slot["kind"] = kind
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
    label = media_label_map().get(kind, kind)
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
                    media_ownership.badge(detail.get("via") or entry.get("via"))
                spec = _spec(detail)
                if spec:
                    ui.label(spec).classes("hub-help")
                ui.label(media_ownership.sentence(detail.get("via") or entry.get("via"),
                                        viewing_a_table=bool(table_id))) \
                    .classes("hub-help")
                origin = str(detail.get("origin") or entry.get("origin") or "")
                # "unknown" is the ledger's honest answer and a useless line to read:
                # most files predate the ledger, so it would be on nearly every slot.
                if origin and origin not in ("unknown", "user"):
                    ui.label(f"Came from {origin}").classes("hub-help")
                # Only when somebody has said - "not matched" is true of nearly every
                # file, and the button below is where the unanswered case belongs.
                named = _match_line(context, kind,
                                    detail.get("matched_to") or entry.get("matched_to"))
                if named:
                    ui.label(named).classes("hub-help")
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
                        media_ownership.badge(item.get("tier"))

        # Only from the game's lens, and only when somebody differs. This is the whole
        # of Model B in the panel: the shared file above, and who is not using it.
        for other in (differing or []):
            with ui.row().classes("items-center gap-2 w-full no-wrap hub-slot-differs"):
                media_ownership.badge("table")
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
                # Beside the acts on the bytes: a slot holding nothing has no identity.
                _match_button(context, kind, label,
                              detail if detail.get("path") else entry, draw)
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
        _tables_block(context)


async def _table_block(context: dict[str, Any]) -> None:
    """What this table is - the file somebody built, and what it needs to run."""
    chosen = next((t for t in context["tables"] if t.get("id") == context["lens"]),
                  None)
    with ui.column().classes("gap-0 hub-form"):
        if chosen is None:
            ui.label("No table selected").classes("hub-help")
            return
        _table_rows(chosen, context)


async def _write(context: dict[str, Any], call: Callable[..., Any],
                 *args: Any) -> None:
    """One write, off the loop, then redraw. Off the loop because this is an HTTP call
    to our own process: made on the event loop it blocks the server from answering it,
    and the browser reports the socket as lost rather than slow."""
    try:
        await run.io_bound(call, *args)
    except Exception as exc:
        ui.notify(f"Could not save: {exc}", type="negative")
        return
    await context["rebuild"]()


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

    entries: list[tuple[Any, Any]] = [
        (HEADING, game_tables.MACHINE),
        ("Name", _override(game.get("name") or "", found.get("name") or "",
                           "VPS", save("alt_title"))),
        ("Made by", f"{game.get('manufacturer') or '?'} "
                    f"{game.get('year') or ''}".strip()),
        ("Type", game.get("type") or "-"),
        ("Themes", ", ".join(game.get("themes") or []) or "-"),
        ("Folder", PurePosixPath(folder).name or folder or "-"),
    ]

    record = game.get("user") or {}

    async def rate(value: int) -> None:
        await _write(context, context["library"].set_game_rating,
                     context["game_id"], value)

    async def favorite(event: Any) -> None:
        await _write(context, context["library"].set_game_favorite,
                     context["game_id"], bool(event.value))

    async def reset() -> None:
        if not await confirm.ask(
                "Reset this game's play record?",
                detail="Its rating, favorite and tags are kept. The counters cannot "
                       "be recovered.",
                confirm="Reset"):
            return
        await _write(context, context["library"].reset_play_record,
                     context["game_id"])

    entries += [(HEADING, game_tables.PLAY)]
    async def retag(chosen: list[str]) -> None:
        await _write(context, context["library"].set_game_tags,
                     context["game_id"], chosen)

    entries += _play_rows(context, record, rating=int(game.get("rating") or 0),
                          on_rate=rate, on_reset=reset,
                          favorite=lambda: _switch(bool(record.get("favorite")),
                                                   favorite,
                                                   hint="Yours, and the frontend can "
                                                        "filter on it"),
                          tags=_tag_picker(list(record.get("tags") or []),
                                           context["library"].tags(), retag))

    entries += [
        (HEADING, game_tables.FRONTEND),
        # Nothing supplies this but the user, so there is nothing to revert to - empty
        # means the frontend's own default, which is what clearing it says.
        ("DOF event", _override(overrides.get("frontend_dof_event") or "", None,
                                "", save("frontend_dof_event"),
                                hint="Empty uses the default effect")),
    ]
    _rows(ui, entries)


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

    # Grouped by what a fact is about, one vocabulary shared with the views and the
    # grid. HUBUI section 14. Each group carries the actions that work on it.
    features = table.get("features") or {}
    overrides = (table.get("overrides") or {}) if context else {}

    entries: list[tuple[Any, Any]] = []
    if context is not None:
        entries += _attention(table)

    # What this file is. "Filename" rather than the group's own word, which named the
    # filename here and the on-disk state under Status - one word, two facts, both on
    # screen at once.
    entries += [
        (HEADING, game_tables.FILE),
        ("Filename", table.get("filename") or "-"),
        ("Version", table.get("version") or "-"),
        ("Author", ", ".join(table.get("authors") or []) or "-"),
        ("Hash", table.get("file_hash") or "-"),
    ]

    # Its own group. These say what the table implements, which is not the same
    # question as what plays it - the group they shared could not be named honestly.
    if features:
        # The chips span the row: the heading already says Features, and a row
        # labelled for its own group is the File/Filename collision again.
        entries += [(HEADING, game_tables.FEATURES),
                    (FULL, lambda: _feature_chips(features))]

    # Can it run, and how. The dependencies are shown as evidence, never managed
    # here: a finding jumps to where it is fixed. HUBUI section 14.3.
    entries += [(HEADING, game_tables.LAUNCH)]
    present = bool(table.get("available"))
    entries += [
        ("Will run", _launch_state(table.get("launchable"))),
        (game_tables.FILE,
         _state(game_tables.word_for(game_tables.FILE_WORDS, not present),
                "on" if present else "bad")),
        ("Application", apps.app_name(table.get("app"))),
        ("ROM", _rom_state(pinmame, rom, context=context)),
    ]
    if context is not None:
        entries += _table_override_rows(context, table, overrides)
        entries += [(FULL, _play_action(context, table))]

    # What somebody thinks of this file, and what they have done with it. The game's
    # record is the headline; a table that has been played while its sibling has not
    # is the thing the game's total cannot say.
    if context is not None:
        record = table.get("user") or {}
        table_id = str(table.get("id") or "")

        async def rate(value: int) -> None:
            await _write(context, context["library"].set_table_rating,
                         context["game_id"], table_id, value)

        async def reset() -> None:
            if not await confirm.ask(
                    "Reset this table's play record?",
                    detail="Its rating is kept, and the game's own record is not "
                           "touched. The counters cannot be recovered.",
                    confirm="Reset"):
                return
            await _write(context, context["library"].reset_play_record,
                         context["game_id"], table_id)

        entries += [(HEADING, game_tables.PLAY)]
        entries += _play_rows(context, record, rating=int(table.get("rating") or 0),
                              on_rate=rate, on_reset=reset)

    # What the frontend does with it. Settings, where Launch above is findings.
    entries += [(HEADING, game_tables.FRONTEND)]
    if context is not None:
        entries += _library_rows(context, table)
    else:
        said = game_tables.default_state(table.get("default_kind") or "")
        entries += [
            (game_tables.DEFAULT_LABEL,
             said[0] if table.get("default") and said else "No"),
            ("Hidden", game_tables.word_for(game_tables.HIDDEN_WORDS,
                                            bool(table.get("hidden")))),
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


def _assets_label(context: dict[str, Any]) -> str:
    """Counts what is here, not what could be: a denominator over sixteen registry
    kinds would call every ordinary game mostly empty."""
    game = context["game"]
    chosen = next((item for item in context["tables"]
                   if item.get("id") == context["lens"]), None)
    resolved = (chosen or {}).get("assets") or {}
    have = sum(1 for state in resolved.values()
               if state.get("resolution") != "none")
    # Skipping what the table already answered, exactly as the body does. The folder
    # reports a backglass this table resolves too, so counting both said four where
    # two rows were drawn - a header disagreeing with the list under it.
    have += sum(1 for kind, state in (game.get("assets") or {}).items()
                if kind not in resolved and state.get("present"))
    return f"Assets ({have})" if have else "Assets"


async def _assets_block(context: dict[str, Any]) -> None:
    """Every asset this game holds, and whose each one is.

    Two levels in one list, because somebody asking what a table has does not care
    which of them the filesystem answers at. The five VPX resolves by naming rule are
    the table's and carry a tier; the rest belong to the folder and carry presence.
    The tiers are `media_ownership`'s - the question is the same one, which file wins.

    Kinds the library does not collect are left out entirely. A row saying an EM table
    has no ROM is not a fact about that table, it is the list answering a question this
    library never asked.
    """
    game = context["game"]
    chosen = next((item for item in context["tables"]
                   if item.get("id") == context["lens"]), None)
    kept = await run.io_bound(_kept_kinds, context, "asset")
    resolved = _only_kept((chosen or {}).get("assets") or {}, kept)
    folder = _only_kept(game.get("assets") or {}, kept)

    entries: list[tuple[Any, Any]] = []
    if chosen is not None:
        entries += [(HEADING, "This table")]
        for kind, state in sorted(resolved.items()):
            entries.append((_asset_name(kind),
                            _resolved_row(context, chosen, kind, state)))
            if kind == "script" and state.get("resolution") != "none":
                digest = str(chosen.get("vbs_hash") or "")
                # The hash travels with the asset rather than sitting in a group of
                # identifiers. Only where there is a sidecar to have one.
                if digest:
                    entries.append(("Script hash", digest))
        pinmame = (chosen.get("dependencies") or {}).get("pinmame") or {}
        if pinmame.get("effective") or pinmame.get("declared"):
            entries.append((_asset_name("rom"), _rom_state(
                pinmame, str(pinmame.get("effective")
                             or pinmame.get("declared") or "-"))))

    entries += [(HEADING, "The game folder")]
    for kind, state in sorted(folder.items()):
        # Already answered above, and more precisely: the table's own lookup says
        # which file wins, where the folder can only say one is somewhere in it.
        if kind in resolved:
            continue
        entries.append((_asset_name(kind), _present_row(bool(state.get("present")))))

    with ui.column().classes("gap-0 hub-form"):
        _rows(ui, entries)


def _only_kept(states: dict[str, Any], kept: set[str] | None) -> dict[str, Any]:
    """Drop what the library does not collect. `table` is never in the toggles and so
    is never dropped - the .vpx is the library rather than an accessory to it."""
    if kept is None:
        return states
    return {kind: state for kind, state in states.items()
            if kind in kept or kind in _ALWAYS_KEPT}


def _asset_name(kind: str) -> str:
    """A kind's own word for itself. `asset_registry` cases the acronyms once."""
    try:
        return asset_registry.spec_for(kind).label
    except KeyError:
        return humanize(kind)


def _resolved_row(context: dict[str, Any], table: dict[str, Any], kind: str,
                  state: dict[str, Any]) -> Any:
    """Whose file this is, the file itself, and the one act that changes it."""
    external = state.get("resolution") != "none"
    name = str(state.get("file") or "")

    def draw() -> None:
        with ui.element("div").classes("hub-fact-edit"):
            # The script takes no tier. Its absence is not a gap - a table running the
            # script inside its own .vpx is the ordinary table - and "Missing" here
            # would call every one of them broken. `SCRIPT_WORDS` asks the question
            # that has no wrong answer: which script runs.
            if kind == "script":
                word = game_tables.word_for(game_tables.SCRIPT_WORDS, external)
                why = ("A .vbs beside the table, and VPX runs it instead of the one "
                       "inside" if external
                       else "The table runs the script inside its own .vpx")
                ui.label(word).classes("hub-tier hub-tier--off").tooltip(why)
            else:
                tier = media_ownership.for_resolution(state.get("resolution"))
                ui.label(tier.noun).classes(f"hub-tier {tier.css}").tooltip(tier.why)
            if name:
                ui.label(name).classes("hub-slot-file truncate").tooltip(name)
            if kind == "script":
                _script_actions(context, table, external)

    return draw


def _present_row(present: bool) -> Any:
    """A folder-level kind, which is either there or not. No tier: nothing resolves it
    per table, and a tier would imply it could."""
    return _state("Present" if present else "Missing", "on" if present else "off")


def _script_actions(context: dict[str, Any], table: dict[str, Any],
                    external: bool) -> None:
    """Extract a sidecar, or drop one. Section 14.4: the script is managed here and
    Launch only reports it."""
    if external:
        ui.button("Delete", on_click=lambda: _drop_script(context, table)) \
            .props("flat dense no-caps size=sm") \
            .classes("hub-action hub-action--inline hub-action--danger")
    else:
        ui.button("Extract", on_click=lambda: _extract_script(context, table)) \
            .props("flat dense no-caps size=sm") \
            .classes("hub-action hub-action--inline")


def _launch_state(launchable: bool | None) -> Any:
    """The rollup, above the dependencies it is built from.

    Its inputs stay on screen underneath: a bare "Blocked" with no reason is a state
    somebody has to go hunting behind, and the row that explains it is the next one.
    """
    if launchable is None:
        return _state(game_tables.LAUNCH_UNKNOWN, "unknown")
    return _state(game_tables.word_for(game_tables.LAUNCH_WORDS, not launchable),
                  "on" if launchable else "bad")


def _played_when(stamp: str | None) -> str:
    """A date, not a timestamp. Nobody reads a play record to the second."""
    if not stamp:
        return "Never"
    try:
        return datetime.fromisoformat(stamp).astimezone().strftime("%d %b %Y")
    except ValueError:
        return "Never"


def _played_for(seconds: int) -> str:
    """Play time in the largest unit that is still true, because the number is read at
    a glance and 41,400 seconds is not a length anybody pictures."""
    if seconds < 60:
        return "None" if not seconds else f"{seconds} sec"
    minutes = seconds // 60
    if minutes < 90:
        return f"{minutes} min"
    hours, rest = divmod(minutes, 60)
    return f"{hours} hr {rest} min" if rest else f"{hours} hr"


def _play_rows(context: dict[str, Any], record: dict[str, Any], *,
               rating: int, on_rate: Callable[[int], Any],
               on_reset: Callable[[], Any],
               favorite: Callable[[], None] | None = None,
               tags: Callable[[], None] | None = None) -> list[tuple[Any, Any]]:
    """What somebody thinks of this, and what they have done with it.

    Two kinds in one group and the controls say which: rating and favorite are opinions
    somebody sets, the counters are a record of what happened. Only the record can be
    reset, and the act sits under it rather than beside a row it does not belong to.
    """
    rows: list[tuple[Any, Any]] = [("Rating", stars.draw(rating, on_rate))]
    if favorite is not None:
        rows.append(("Favorite", favorite))
    if tags is not None:
        rows.append(("Tags", tags))
    rows += [
        ("Last played", _played_when(record.get("last_played"))),
        ("Times played", str(int(record.get("play_count") or 0) or "Never")),
        ("Play time", _played_for(int(record.get("play_time_seconds") or 0))),
    ]
    if context is not None and any(record.get(key) for key in
                                   ("last_played", "play_count", "play_time_seconds")):
        rows.append((FULL, _reset_action(on_reset)))
    return rows


def _tag_picker(held: list[str], known: list[str],
                on_change: Callable[[list[str]], Any]) -> Callable[[], None]:
    """The tags on this game, and the ones the library already knows.

    The same control a multi-valued filter axis uses - chips for what is set, and the
    text input once the list outgrows a glance, which is section 5's rule about a list
    longer than a screen being typed into rather than scrolled. Typing filters the known
    ones, so a tag somebody already used is the easy thing to pick; a new one is added
    on Enter, and `add-unique` is what makes a repeat impossible.

    Case is not folded. Two spellings are two tags until somebody merges them, and
    folding here would hide the duplicate instead of letting it be found.
    """
    def draw() -> None:
        control = ui.select(known, multiple=True, value=list(held),
                            with_input=True, new_value_mode="add-unique") \
            .props('dense outlined use-chips hide-dropdown-icon '
                   'popup-content-class="hub-picker-popup"') \
            .classes("w-full min-w-0")
        control.on_value_change(lambda: on_change(list(control.value or [])))

    return draw


def _reset_action(on_reset: Callable[[], Any]) -> Callable[[], None]:
    """Only where there is something to clear. An act offered on a record of nothing
    is a button that cannot do anything."""
    def draw() -> None:
        with ui.element("div").classes("hub-slot-actions"):
            ui.button("Reset play record", icon="restart_alt",
                      on_click=on_reset).props("flat dense no-caps size=sm") \
                .classes("hub-action")

    return draw


def _vps_label(context: dict[str, Any]) -> str:
    game = context["game"]
    return "VPS" if game.get("vps_id") else "VPS - not matched"


async def _vps_block(context: dict[str, Any]) -> None:
    """What this game is matched to in the catalog, and the way to change it.

    The match drives metadata, media lookup and update tracking, and until now the only
    way to set it was typing an eight-character id into a text field. Section 15.

    It does not judge the match. A ranker was measured and retired for being confidently
    wrong more than half the time, so nothing here says a match looks wrong or offers a
    better one - it shows what is bound and lets somebody go looking when they choose.
    """
    game = context["game"]
    library = context["library"]
    vps_id = str(game.get("vps_id") or "")
    chosen = bool((game.get("overrides") or {}).get("alt_vps_id"))

    entries: list[tuple[Any, Any]] = []
    parked = game.get("parked_vps_id") or {}
    if parked.get("value"):
        entries.append((FULL, _parked_match(context, parked)))

    if not vps_id:
        entries += [("Entry", _state("Not matched", "warn"))]
    else:
        found = await run.io_bound(library.vps_entry, vps_id)
        entries += [
            # The entry as a person reads it. The id is how the wire addresses it and
            # is the one thing a reader cannot check a match against.
            ("Entry", _vps_entry_row(found, vps_id)),
            ("Match", _state("Set by you" if chosen else "Discovered",
                             "on" if chosen else "off")),
        ]
        if found.get("releases"):
            entries.append(("Releases", str(found["releases"])))
        differs = await run.io_bound(library.vps_details, context["game_id"])
        if differs:
            entries.append((FULL, _details_differ(context, differs)))
    entries.append((FULL, _change_match(context)))

    with ui.column().classes("gap-0 hub-form"):
        _rows(ui, entries)


# What the catalog calls these against what a person does. Only where the two differ:
# `Manufacturer` needs no translating and a map that repeats it is a map nobody trusts.
DETAIL_WORDS = {"Title": "Name", "IPDBId": "IPDB", "PinballPrimerTut": "Tutorial",
                "Themes": "Theme"}


def _details_differ(context: dict[str, Any],
                    differs: list[dict[str, Any]]) -> Callable[[], None]:
    """The game's details against the entry's, where they have come apart.

    Absent the whole time until somebody corrects a match, which is the only thing that
    parts them: the details were written from the entry, so they agree with it until
    the entry changes underneath them. Measured on a real library - across 71 matched
    games, not one field disagreed.

    Adopting is one act over all of them rather than a choice per field. They are one
    machine's facts, and taking this one's year beside that one's maker would describe
    no machine at all.
    """
    async def adopt() -> None:
        await _write(context, context["library"].adopt_vps_details,
                     context["game_id"])

    def draw() -> None:
        # The block lays its children out in a row, so the stack goes in a column of
        # its own - the same shape the fault list beside an icon uses.
        with ui.element("div").classes("hub-attention w-full"), \
                ui.column().classes("gap-1 min-w-0 grow"):
            ui.label("This game still describes the machine it was matched to before") \
                .classes("hub-attention-line")
            for item in differs:
                said = str(item.get("field") or "")
                with ui.row().classes("items-baseline gap-2 w-full no-wrap"):
                    ui.label(DETAIL_WORDS.get(said, said)).classes("hub-diff-field")
                    ui.label(str(item.get("ours") or "-")).classes("hub-diff-was")
                    ui.icon("arrow_forward").classes("hub-diff-arrow")
                    ui.label(str(item.get("theirs") or "-")).classes("hub-help truncate")
            ui.button("Use the entry's details", on_click=adopt) \
                .props("flat dense no-caps size=sm").classes("hub-action")

    return draw


def _vps_entry_row(found: dict[str, Any], vps_id: str) -> Callable[[], None]:
    """The matched machine, named the way somebody can check it - and a way out to the
    catalog, so a reader is not asked to search for what is already identified."""
    def draw() -> None:
        with ui.element("div").classes("hub-fact-edit"):
            said = str(found.get("name") or "")
            made = " ".join(str(found.get(k) or "") for k in ("manufacturer", "year"))
            ui.label(f"{said} - {made.strip()}" if said else vps_id) \
                .classes("hub-fact-value truncate min-w-0").tooltip(vps_id)
            if found.get("url"):
                ui.link(target=str(found["url"]), new_tab=True) \
                    .classes("hub-action hub-action--inline").tooltip("Open on VPS") \
                    .props("no-caps") \
                    .set_text("View")

    return draw


def _change_match(context: dict[str, Any]) -> Callable[[], None]:
    """One verb on this section, which is the only act it offers."""
    def draw() -> None:
        with ui.element("div").classes("hub-slot-actions"):
            ui.button("Change match...", icon="search",
                      on_click=lambda: _pick_a_match(context)) \
                .props("flat dense no-caps size=sm").classes("hub-action")

    return draw


async def _pick_a_match(context: dict[str, Any]) -> None:
    """Search the catalog and bind one entry, or clear the binding.

    Presented in the order the catalog answers in - by name, then year - and with no
    mark of quality on any row. Section 15.2: sorting by "best match" is a claim, and
    the measurement that would have to support it says the opposite.

    The query starts as the game's name because that is where somebody would start
    typing, and it is visible and editable rather than a filter applied behind them.
    """
    game = context["game"]
    library = context["library"]

    with ui.dialog().props("persistent") as dialog, \
            ui.card().classes("hub-confirm hub-picker-dialog"):
        ui.label("Match this game to VPS").classes("hub-confirm-title")
        ui.label("Nothing here ranks the results - pick the machine you have.") \
            .classes("hub-help")
        field = ui.input(value=str(game.get("name") or "")) \
            .props("dense autofocus clearable").classes("hub-edit-field w-full")
        found = ui.column().classes("w-full gap-0 hub-source-list")

        async def look() -> None:
            said = str(field.value or "").strip()
            rows = await run.io_bound(library.vps_search, said, 40) if said else []
            found.clear()
            with found:
                if not said:
                    ui.label("Type a name, a maker or a year").classes("hub-help")
                    return
                if not rows:
                    ui.label(f"Nothing in the catalog matches “{said}”") \
                        .classes("hub-help")
                    return
                for row in rows:
                    _match_row(row, dialog)

        field.on("keydown.enter", look)
        ui.button("Search", on_click=look).props("flat dense no-caps size=sm") \
            .classes("hub-action")
        with ui.row().classes("justify-end gap-2 w-full"):
            ui.button("Clear match", on_click=lambda: dialog.submit("")) \
                .props("flat no-caps")
            ui.button("Cancel", on_click=lambda: dialog.submit(None)).props("flat no-caps")
        await look()

    picked = await dialog
    if picked is None:
        return
    await _write(context, library.set_game_overrides, context["game_id"],
                 {"alt_vps_id": str(picked)})


def _match_row(row: dict[str, Any], dialog: Any) -> None:
    """One candidate, with the machine's photograph where the catalog has one.

    Named twice over - by the maker and year that tell two machines of one name apart,
    and by the picture, which settles it faster than either. The release count rides in
    the same line: it says which entry the world actually builds for, and it is not a
    judgement of the match, which nothing here makes.
    """
    said = [" ".join(str(row.get(k) or "") for k in ("manufacturer", "year")).strip()]
    count = int(row.get("releases") or 0)
    if count:
        said.append(f"{count} release{'' if count == 1 else 's'}")
    candidates.choice(str(row.get("img_url") or ""), str(row.get("name") or ""),
                      " \u00b7 ".join(part for part in said if part),
                      lambda: dialog.submit(str(row.get("vps_id") or "")),
                      glyph="videogame_asset")


def _parked_match(context: dict[str, Any], parked: dict[str, Any]) -> Callable[[], None]:
    """A match the user made, set aside when the table it was claimed against changed.

    Not a suggestion and not a warning - it is their own statement handed back, which is
    why it can sit here at all while nothing else on this section judges a match.
    """
    async def restore() -> None:
        await _write(context, context["library"].set_game_overrides,
                     context["game_id"], {"alt_vps_id": str(parked.get("value") or "")})

    async def discard() -> None:
        if not await confirm.ask(
                "Discard the match you made earlier?",
                detail="It is not in use either way. Discarding means looking it up "
                       "again if you want it back.",
                confirm="Discard"):
            return
        await _write(context, context["library"].set_game_overrides,
                     context["game_id"], {"alt_vps_id_previous": ""})

    def draw() -> None:
        with ui.element("div").classes("hub-attention w-full"):
            said = str(parked.get("table") or "")
            ui.label("You matched this by hand before "
                     + (f"“{said}” was replaced" if said else "the table changed")) \
                .classes("hub-attention-line")
            with ui.row().classes("items-center gap-2"):
                ui.button("Restore", on_click=restore) \
                    .props("flat dense no-caps size=sm").classes("hub-action")
                ui.button("Discard", on_click=discard) \
                    .props("flat dense no-caps size=sm") \
                    .classes("hub-action hub-action--danger")

    return draw


def _rom_state(pinmame: dict[str, Any], rom: str,
               context: dict[str, Any] | None = None) -> Any:
    """The rom, and whether it is actually there.

    The chain resolves aliases and audits the install, so the name alone is half an
    answer: what anybody wants of a rom is whether it will run.

    A missing one carries the way *to* the fix rather than the fix. Section 14.3:
    Launch reports and Assets manages, so a finding jumps to where the act lives.
    """
    installed = pinmame.get("installed")
    if not pinmame.get("effective") or installed is None:
        return rom
    chip = _state("Installed" if installed else "Not installed",
                  "on" if installed else "warn", beside=rom)
    if installed or context is None:
        return chip

    def draw() -> None:
        chip()
        ui.button("Assets", icon="chevron_right",
                  on_click=lambda: _choose(context, "assets")) \
            .props("flat dense no-caps size=sm") \
            .classes("hub-action hub-action--inline") \
            .tooltip("Where a rom is managed")

    return draw


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
        """The state, and the one act that changes it.

        A switch stood here and could not tell the truth: the fact has three states -
        the default because somebody chose it, the default because nothing did, and not
        the default - so a two-state control had to say something else, and said
        "Default table for game" while the grid said "User". The chip is the finding and
        the button is the act, which is the panel's own convention.
        """
        said = game_tables.default_state(table.get("default_kind") or "")
        with ui.element("div").classes("hub-fact-edit"):
            if is_default and said:
                # No colour: green in this panel means installed, present, extracted -
                # facts whose absence costs you a working table. A game has a default
                # either way, so the word carries it and the palette keeps its meaning.
                ui.label(said[0]).classes("hub-tier hub-tier--off").tooltip(said[1])
            if not is_default:
                ui.button("Make default",
                          on_click=lambda: act(library.set_default_table, game_id,
                                               table_id,
                                               done="Now the game's default")) \
                    .props("flat dense no-caps size=sm") \
                    .classes("hub-action hub-action--inline")
            elif (table.get("default_kind") or "") == game_tables.DERIVED:
                # The way to stop it moving. Nothing else in the UI could pin the table
                # a game had already landed on, so an automatic default stayed at the
                # mercy of the next table installed.
                ui.button("Choose",
                          on_click=lambda: act(library.set_default_table, game_id,
                                               table_id, done="Chosen")) \
                    .props("flat dense no-caps size=sm") \
                    .classes("hub-action hub-action--inline")
            else:
                ui.button("Clear choice",
                          on_click=lambda: act(library.set_default_table, game_id, "",
                                               done="Back to an automatic default")) \
                    .props("flat dense no-caps size=sm") \
                    .classes("hub-action hub-action--inline")

    def hidden_row() -> None:
        # On is hidden, the same direction the column and the funnel read it. It used to
        # be "Frontend visible" and inverted the value on its way to the API, so the two
        # surfaces asked opposite questions about one flag.
        _switch(hidden,
                lambda event: act(library.set_table_hidden, game_id, table_id,
                                  bool(event.value)),
                hint="Keep this table out of the frontend")

    return [(game_tables.DEFAULT_LABEL, default_row), ("Hidden", hidden_row)]


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
def _feature_chips(features: dict[str, Any]) -> None:
    """What the table's script was seen to use, named where there is room for names -
    the grid draws the same three states as marks."""
    with ui.element("div").classes("hub-chips"):
        for key, label in table_features.LABELS.items():
            state = table_features.state_of(features.get(key))
            ui.label(label).classes(f"hub-tier {state.chip}").tooltip(state.noun)


async def _script_act(context: dict[str, Any], call: Any, table_id: str,
                      done: str, failed: str) -> None:
    """Run one script act and redraw. The panel is showing which script runs, so it is
    exactly what the act changes."""
    try:
        await run.io_bound(call, context["game_id"], table_id)
    except Exception as exc:
        ui.notify(f"{failed}: {exc}", type="negative")
        return
    ui.notify(done, type="positive")
    await context["rebuild"]()


async def _extract_script(context: dict[str, Any], table: dict[str, Any]) -> None:
    """Not confirmed: it writes a new file and takes nothing away, and the way back is
    the Delete beside it."""
    await _script_act(context, context["library"].extract_script,
                      table.get("id") or "", "Extracted - the table now runs the .vbs",
                      "Could not extract the script")


async def _drop_script(context: dict[str, Any], table: dict[str, Any]) -> None:
    """Confirmed: whatever the sidecar held goes with it, and a patched table quietly
    becomes an unpatched one."""
    if not await confirm.ask(
            "Delete the script beside this table?",
            detail="The table goes back to the script inside its .vpx. Anything the "
                   "sidecar held - a patch, an edit - goes with it.",
            lines=[f"{Path(table.get('filename') or '').stem}.vbs"]):
        return
    await _script_act(context, context["library"].delete_script,
                      table.get("id") or "", "Deleted - the table runs its own script",
                      "Could not delete the script")


async def _forget_table(context: dict[str, Any], table: dict[str, Any]) -> None:
    """Drop a gone table's record, once the user says it is not coming back.

    Confirmed because it is the only destructive thing on this surface, and the dialog
    names the file rather than the id - the id is ours, the filename is what the user
    recognizes. The hub refuses the request outright if the .vpx is back, so a stale
    panel cannot delete a table that returned while it was open.
    """
    if not await confirm.ask(
            "Forget this table?",
            detail="Its record goes; no file is deleted, because there is none. Put the "
                   ".vpx back and refresh and it returns as a new table.",
            lines=[table.get("filename") or "this table"], confirm="Forget"):
        return
    try:
        await run.io_bound(context["library"].forget_table,
                           context["game_id"], table.get("id") or "")
    except Exception as exc:
        ui.notify(f"Could not forget it: {exc}", type="negative")
        return
    ui.notify("Table forgotten", type="positive")
    await context["rebuild"]()


def _tables_block(context: dict[str, Any]) -> None:
    """This game's tables, and which one it offers first.

    A block inside Game Details rather than a rail entry of its own: most games hold one
    table, so "Tables (1)" was a place you went to read a single row, and the rail holds
    places. Section 7 already names this shape - a sub-table, a related collection with
    its own columns.

    Version and author, never the filename - this is the block whose whole job is
    telling them apart, and filenames cannot. HUBUI section 13.
    """
    tables = context["tables"]
    if not tables:
        return
    showing = str(context.get("lens") or "")
    # Only where there is a choice to describe. A count beside one row says nothing.
    said = f"Tables ({len(tables)})" if len(tables) > 1 else "Table"
    ui.label(said).classes("hub-card-title hub-fact-heading")
    for table in tables:
        since = str(table.get("absent_since") or "")
        here = str(table.get("id") or "") == showing
        with ui.column().classes("gap-0 w-full hub-member-row"):
            with ui.row().classes("items-center gap-2 w-full no-wrap"):
                # On every row, and leading. `docs/conventions.md`: show varying state
                # on every row rather than let a reader take meaning from absence -
                # which is what a chip on the default alone asked them to do. A game
                # has exactly one default, so the control that says so is a radio.
                _default_mark(context, table, since=since)
                name = ui.label(game_tables.table_name(table)) \
                    .classes("hub-member-name grow min-w-0 truncate") \
                    .tooltip(str(table.get("filename") or ""))
                # Which of them the panel beside this is about. Without it the block
                # repeats the grid you are already looking at; with it, it is where
                # you are - this game has two, you are on one, that one is default.
                if here:
                    name.classes(add="hub-member-name--here")
                if since:
                    # Stated, not judged: how long it has been gone is what tells a
                    # deletion from a share that was late mounting, and that call is
                    # the user's.
                    name.classes(add="opacity-60")
                    ui.label(game_tables.word_for(game_tables.FILE_WORDS, True)) \
                        .classes("hub-member-chip hub-tier hub-tier--warn") \
                        .tooltip(f"Not on disk since {since[:10]}")
                elif table.get("default"):
                    # Qualifies *the default*, so it belongs only where there is one -
                    # the mark has already said which row that is, and "how was it
                    # decided" is not a question a non-default table answers.
                    say = game_tables.default_state(table.get("default_kind") or "")
                    if say:
                        ui.label(say[0]).classes("hub-member-chip hub-chip-quiet") \
                            .tooltip(say[1])
                # On every row that has one, because which program plays a file is
                # exactly what separates a VPX build from a Future Pinball one - it
                # used to appear only where the game had a single table, which is when
                # it distinguishes nothing.
                app = apps.app_name(table.get("app"))
                if app:
                    ui.label(app).classes("hub-member-chip hub-tier hub-tier--off")
                with ui.element("div").classes("hub-row-action"):
                    if since:
                        ui.button(icon="delete_outline",
                                  on_click=lambda _, t=table: _forget_table(context, t)) \
                            .props("flat dense round size=sm color=warning") \
                            .tooltip("Forget this table")
                    else:
                        _release_button(context, table)
                        _launch_button(context, table)
            _release_line(table)


def _release_line(table: dict[str, Any]) -> None:
    """Which build of the machine this file is, once somebody has said.

    Nothing at all until then, which is the honest reading of an absent record: no
    matcher has examined this and none exists, so a row that read "not matched" would
    be reporting a search that never happened.

    Drawn from what the row already carries. Reaching for the release list here put a
    blocking hub call inside a synchronous draw, and the rows after it never appeared.
    """
    source = table.get("source") or {}
    if not source.get("vps_file_id"):
        return
    version = str(source.get("version") or "")
    made_by = ", ".join(str(name) for name in (source.get("authors") or [])[:3])
    told = " \u00b7 ".join(part for part in (version, made_by) if part)
    with ui.row().classes("items-center gap-2 w-full no-wrap hub-member-table-line"):
        ui.label(told or "A build the catalog no longer lists").classes("hub-help truncate")


def _release_button(context: dict[str, Any], table: dict[str, Any]) -> None:
    """The way to say which build this file is.

    Shown whether or not one is recorded, because with nothing recorded there is
    otherwise no way in: the row says nothing about its release until somebody has
    answered, so the affordance cannot be the answer.
    """
    entry = str(context["game"].get("vps_id") or "")
    button = ui.button(icon="link",
                       on_click=lambda: _pick_a_release(context, table)) \
        .props("flat dense round size=sm")
    if entry:
        button.tooltip("Which release this is")
        return
    # A release belongs to an entry, so there is nothing to choose among until the
    # game is matched. Said on the control rather than in a dialog that opens empty.
    button.disable()
    button.tooltip("Match the game to VPS first, then its releases can be named")


def _listed_as(kind: str, inventory: str) -> Any:
    """What VPSdb calls this kind, when it is asking about the right inventory.

    `backglass` is a picture among media and a `.directb2s` among assets, and VPS
    lists the second. Matching by name alone offered a media slot the assets that
    view is explicitly not about.
    """
    listed = vps_kinds.BY_OURS.get(kind)
    return listed if listed is not None and listed.held_in == inventory else None


def _match_line(context: dict[str, Any], kind: str, matched_to: Any) -> str:
    """What the bound record is called. Resolved here because the catalog is already
    open on this side and an id is not something to put on screen."""
    said = str(matched_to or "")
    listed = _listed_as(kind, vps_kinds.MEDIA)
    if not said or listed is None:
        return ""
    vps_id = str(context["game"].get("vps_id") or "")
    for record in _records_of(context, vps_id, listed.listed_as):
        if str(record.get("vps_file_id") or "") == said:
            told = " · ".join(part for part in (
                str(record.get("version") or ""),
                ", ".join(str(name) for name in (record.get("authors") or [])[:2]),
            ) if part)
            return f"Matched to {told}" if told else "Matched to a published file"
    # Worth saying: it is why no update will ever be reported for this file.
    return "Matched to a file the catalog no longer lists"


def _match_button(context: dict[str, Any], kind: str, label: str,
                  entry: dict[str, Any], redraw: Callable[[], None]) -> None:
    """The way to say which VPS record one file is. Only for media kinds VPSdb lists -
    a picker over a kind nothing publishes opens empty every time."""
    listed = _listed_as(kind, vps_kinds.MEDIA)
    if listed is None:
        return
    path = str(entry.get("path") or "")
    if not path:
        return
    bound = str(entry.get("matched_to") or "")
    button = ui.button("Change match" if bound else "Match",
                       on_click=lambda: _pick_a_record(context, listed.listed_as,
                                                       label, path, bound, redraw)) \
        .props("flat dense no-caps size=sm").classes("hub-action")
    if context["game"].get("vps_id"):
        button.tooltip("Which published file this is")
        return
    # The records belong to an entry, so there is nothing to choose among until the
    # game is matched. Said on the control rather than in a dialog that opens empty.
    button.disable()
    button.tooltip("Match the game to VPS first, then its files can be named")


async def _pick_a_record(context: dict[str, Any], listed_as: str, label: str,
                         path: str, bound: str,
                         redraw: Callable[[], None]) -> None:
    """Bind one file to a record VPSdb publishes, or take the binding back.

    The assets ledger's twin of `_pick_a_release`, unordered for the same reason: the
    scorer that would rank these was measured at chance.
    """
    library = context["library"]
    vps_id = str(context["game"].get("vps_id") or "")
    records = await run.io_bound(_records_of, context, vps_id, listed_as)

    with ui.dialog().props("persistent") as dialog, \
            ui.card().classes("hub-confirm hub-picker-dialog"):
        ui.label(f"Which published {label.lower()} is this?") \
            .classes("hub-confirm-title")
        ui.label(path).classes("hub-help")
        with ui.column().classes("w-full gap-0 hub-source-list"):
            if not records:
                ui.label(f"VPS lists no {label.lower()} for this machine") \
                    .classes("hub-help")
            for item in records:
                _record_row(item, dialog, bound)
        with ui.row().classes("justify-end gap-2 w-full"):
            if bound:
                ui.button("Clear", on_click=lambda: dialog.submit("")) \
                    .props("flat no-caps")
            ui.button("Cancel", on_click=lambda: dialog.submit(None)) \
                .props("flat no-caps")

    picked = await dialog
    if picked is None:
        return
    await _write(context, library.set_asset_source, context["game_id"], path,
                 str(picked))
    redraw()


def _record_row(record: dict[str, Any], dialog: Any, bound: str) -> None:
    """One published file, by the two things a person can compare against their own."""
    said = str(record.get("vps_file_id") or "")
    meta = []
    made_by = ", ".join(str(name) for name in (record.get("authors") or [])[:3])
    if made_by:
        meta.append(made_by)
    stamp = str(record.get("updated_at") or "")[:10]
    if stamp:
        meta.append(stamp)
    name = str(record.get("version") or "") or "No version given"
    if said == bound:
        name = f"{name}  ✓"
    candidates.choice(str(record.get("img_url") or ""), name,
                      " · ".join(meta), lambda: dialog.submit(said),
                      glyph="inventory_2")


def _records_of(context: dict[str, Any], vps_id: str,
                listed_as: str) -> list[dict[str, Any]]:
    """One kind's records for an entry. Blocks, so it belongs on a worker thread."""
    if not vps_id:
        return []
    try:
        return list(context["library"].vps_releases(vps_id, listed_as))
    except Exception:
        logger.warning("hub ui: could not read %s for %s", listed_as, vps_id,
                       exc_info=True)
        return []


async def _pick_a_release(context: dict[str, Any], table: dict[str, Any]) -> None:
    """Bind this table to one of the entry's builds, or take the binding back.

    Ordered as VPSdb holds them and marked with nothing: a scorer over this exact
    question was measured at chance. What the panel does offer is the file's own
    version and authors, which is not a ranking - it is the user's own data, put where
    they can compare it against the list rather than remembering it.
    """
    library = context["library"]
    entry = str(context["game"].get("vps_id") or "")
    bound = str((table.get("source") or {}).get("vps_file_id") or "")
    releases = await run.io_bound(_releases_of, context, entry)

    with ui.dialog().props("persistent") as dialog, \
            ui.card().classes("hub-confirm hub-picker-dialog"):
        ui.label("Which release is this table?").classes("hub-confirm-title")
        _yours(table)
        found = ui.column().classes("w-full gap-0 hub-source-list")
        with found:
            if not releases:
                ui.label("VPS lists no builds for this machine").classes("hub-help")
            for item in releases:
                _release_row(item, dialog, bound)
        with ui.row().classes("justify-end gap-2 w-full"):
            if bound:
                ui.button("Clear", on_click=lambda: dialog.submit("")) \
                    .props("flat no-caps")
            ui.button("Cancel", on_click=lambda: dialog.submit(None)) \
                .props("flat no-caps")

    picked = await dialog
    if picked is None:
        return
    await _write(context, library.set_table_source, context["game_id"],
                 str(table.get("id") or ""), str(picked))


def _yours(table: dict[str, Any]) -> None:
    """What this file says about itself, so the list is compared against something.

    A `.vpx` carries a version and its authors and VPS names releases by the same two,
    which is the only honest handle here - VPS records a filename on 3% of them.
    """
    said = str(table.get("version") or "")
    made_by = ", ".join(str(name) for name in (table.get("authors") or [])[:4])
    told = " \u00b7 ".join(part for part in (said, made_by) if part)
    ui.label(f"This file says {told}" if told
             else "This file records no version or author to compare") \
        .classes("hub-help")


def _release_row(release: dict[str, Any], dialog: Any, bound: str) -> None:
    """One build, with its picture - VPS has one for 95% of them, against 39% of the
    machines they belong to, so here the art is the ordinary case and not the exception."""
    said = str(release.get("vps_file_id") or "")
    meta = [str(release.get("format") or "")]
    made_by = ", ".join(str(name) for name in (release.get("authors") or [])[:3])
    if made_by:
        meta.append(made_by)
    stamp = str(release.get("updated_at") or "")[:10]
    if stamp:
        meta.append(stamp)
    name = str(release.get("version") or "") or "No version given"
    if said == bound:
        name = f"{name}  \u2713"
    candidates.choice(str(release.get("img_url") or ""), name,
                      " \u00b7 ".join(part for part in meta if part),
                      lambda: dialog.submit(said), glyph="casino")


def _releases_of(context: dict[str, Any], vps_id: str) -> list[dict[str, Any]]:
    """The entry's builds, for the picker only - this blocks, so it belongs on a worker
    thread and never in a draw."""
    if not vps_id:
        return []
    try:
        return list(context["library"].vps_releases(vps_id))
    except Exception:
        return []


def _launch_button(context: dict[str, Any], table: dict[str, Any]) -> None:
    """Play this one. The row names the table, so the act on it is unambiguous - which
    is what lets Game Details offer a launch without inventing a game-level one whose
    target would be implicit."""
    filename = str(table.get("filename") or "")

    async def go() -> None:
        try:
            await run.io_bound(context["library"].launch, context["game_id"], filename)
        except Exception as exc:
            ui.notify(f"Could not launch: {exc}", type="negative")

    button = ui.button(icon="play_arrow", on_click=go) \
        .props("flat dense round size=sm").tooltip("Play this table")
    if not table.get("available"):
        button.disable()


def _default_mark(context: dict[str, Any], table: dict[str, Any], *,
                  since: str) -> None:
    """Which table the game offers, and the way to change it.

    Chris asked for this in section 13 - *"tables to be able to raise their hand and
    say 'I am a default'"* - and the panel could only report it. A gone table is shown
    unset and is not offerable: the game cannot default to a file that is not there.
    """
    chosen = bool(table.get("default"))
    mark = ui.icon("radio_button_checked" if chosen else "radio_button_unchecked") \
        .classes("hub-default-mark")
    if chosen:
        mark.classes(add="hub-default-mark--on")
        mark.tooltip("The table this game offers")
        return
    if since:
        mark.classes(add="opacity-30")
        mark.tooltip("Not on disk, so it cannot be the default")
        return
    mark.classes(add="cursor-pointer")
    mark.tooltip("Make this the default")
    mark.on("click", lambda t=table: _make_default(context, t))


async def _make_default(context: dict[str, Any], table: dict[str, Any]) -> None:
    """Hand the game a different default. Everything downstream that follows the game
    rather than one table moves with it, which is the point of following."""
    try:
        await run.io_bound(context["library"].set_default_table,
                           context["game_id"], str(table.get("id") or ""))
    except Exception as exc:
        ui.notify(f"Could not change it: {exc}", type="negative")
        return
    ui.notify("Default changed", type="positive")
    await context["rebuild"]()


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
            target.label(field_label(str(label))).classes("hub-fact-label")
            if callable(value):
                value()
                continue
            target.label(str(value)).classes("hub-fact-value truncate min-w-0") \
                .tooltip(str(value))


# --- collections ------------------------------------------------------------------
# A collection's rail. Nothing here is shared with a game's: the two subjects have no
# section in common, which is what section 11 means by the rail being a function of
# (nav node, subject) rather than one list everything appears in.
#
# Two sections, not three. A rule and what it matches are one thing to look at - the
# whole point of building a rule beside its result - so they share a section, with the
# rule in the browse region and the result in the dock.


def _collection(context: dict[str, Any]) -> dict[str, Any]:
    return context["collection"]


def _is_dynamic(row: dict[str, Any]) -> bool:
    """Whether this collection changes under its owner.

    Derived, never stored: it carries criteria or it does not. Named for what it does
    to the user rather than for how it was built, which is what makes the arrangement
    question answerable - only a static list has a membership stable enough to arrange.
    """
    return (row.get("type") or "") == "filter"


async def _collection_details(context: dict[str, Any]) -> None:
    """What the collection is, rather than what is in it."""
    row = _collection(context)
    entries: list[tuple[Any, Any]] = [
        (HEADING, "This list"),
        ("Name", _text_control(context, row, "name")),
        ("Description", _text_control(context, row, "description", lines=3)),
        # Kind is not repeated here. It is a control in Contents, beside the rule and
        # the games it decides between, and a read-only copy of it here would be a
        # second home for one fact.
    ]
    with ui.column().classes("gap-0 hub-form"):
        _rows(ui, entries)
        _image_slot(context, row)


def _text_control(context: dict[str, Any], row: dict[str, Any], field: str,
                  lines: int = 0) -> Callable[[], None]:
    """One editable field of a collection, and when it is written.

    Two rhythms, because the two fields cost different amounts to change. Free text
    settles as you stop typing. A name is this collection's identity - every route is
    keyed by it - so it is written when you leave the field, and `debounce=0` is what
    makes that safe: nicegui's model is only current if every keystroke reaches it, and
    reading it on blur without that gets whatever the last sync happened to hold.
    """
    async def save(value: str) -> None:
        if value == (row.get(field) or ""):
            return
        if field == "name" and not value.strip():
            ui.notify("A collection needs a name", type="warning")
            return
        await _patch(context, {field: value})

    def draw() -> None:
        if lines:
            control = ui.textarea()
            control.value = row.get(field) or ""
            control.props(f"dense outlined rows={lines} debounce=800") \
                .classes("w-full min-w-0")
            control.on_value_change(lambda: save(control.value or ""))
            return
        control = ui.input()
        control.value = row.get(field) or ""
        control.props("dense outlined debounce=0").classes("w-full min-w-0")
        control.on("blur", lambda: save(control.value or ""))

    return draw


def _image_slot(context: dict[str, Any], row: dict[str, Any]) -> None:
    """The collection's icon, in the shape a media slot takes.

    Same card, same art region, same blank state, same row of actions - a picture in
    this app is presented one way, and a bespoke drop target here was a second.
    """
    name = row.get("name") or ""
    library = context["library"]
    present = bool(row.get("image"))

    async def upload(event) -> None:
        import tempfile
        content = event.content.read()
        if not content:
            return
        with tempfile.NamedTemporaryFile(suffix=Path(event.name).suffix,
                                         delete=False) as staged:
            staged.write(content)
        try:
            await run.io_bound(library.set_collection_image, name, staged.name)
        except Exception as exc:
            ui.notify(f"Could not use that image: {exc}", type="negative")
            return
        await context["rebuild"]()

    async def clear() -> None:
        await run.io_bound(library.clear_collection_image, name)
        await context["rebuild"]()

    with ui.column().classes("w-full gap-1 hub-slot p-2 mt-3"):
        ui.label("Image").classes("hub-card-title")
        with ui.element("div").classes("hub-slot-art"):
            if present:
                ui.image(f"/api/v1/collections/{quote(name, safe='')}/image") \
                    .classes("hub-slot-image")
            else:
                with ui.column().classes("hub-slot-blank items-center gap-1"):
                    ui.icon("image").classes("hub-slot-blank-icon")
        with ui.row().classes("items-center gap-2 w-full hub-slot-actions"):
            # The picker sits behind the button, as the media slot's own actions do.
            # A drop target the size of the panel was reading as the content.
            upload_control = ui.upload(on_upload=upload, auto_upload=True, max_files=1) \
                .props('accept="image/*"').classes("hidden")
            ui.button("Replace" if present else "Add an image", icon="upload",
                      on_click=lambda: upload_control.run_method("pickFiles")) \
                .props("flat dense no-caps size=sm").classes("hub-action")
            if present:
                ui.button("Remove", on_click=clear) \
                    .props("flat dense no-caps size=sm")


def _contents_label(context: dict[str, Any]) -> str:
    got = (context.get("membership") or {}).get("playable")
    return "Contents" if got is None else f"Contents ({got})"


async def _collection_contents(context: dict[str, Any]) -> None:
    """The rule on the left, what it holds on the right.

    Section 4's own principle - a rule shows its result - applied to the one place a
    rule is written. The dock is where a picked thing goes for a game's media; here the
    thing being looked at is the whole result, which is what the rule is *for*.
    """
    row = _collection(context)
    with ui.column().classes("gap-0 hub-form w-full"):
        _rule_region(context, row)
    dock = context.get("dock")
    if dock is not None:
        dock.clear()
        with dock:
            await _result_region(context, row)


def _rule_region(context: dict[str, Any], row: dict[str, Any]) -> None:
    """What kind of collection this is, what fills it, and how it is presented.

    Three regions, always in this order and always present. Rules used to be behind an
    "Add a rule" button, which charged a click to reveal something permanent and hid
    from a reader that a rule was possible at all.
    """
    dynamic = _is_dynamic(row) or _drafting(context)
    _kind_control(context, row, dynamic)
    ui.label("Rules").classes("hub-group mt-3")
    if dynamic:
        ui.label(_rule_sentence(context, row)).classes("hub-help hub-rule-sentence mb-2")
        _axis_rows(context, row)
        _rule_actions(context, row)
    else:
        # One word. The toggle above already says what a manual collection is, and
        # repeating it here is the filler this section was rebuilt to remove.
        ui.label("None").classes("hub-help")
    _ordering_rows(context, row, arrangeable=not dynamic)


def _kind_control(context: dict[str, Any], row: dict[str, Any],
                  dynamic: bool) -> None:
    """Dynamic or Manual, and switching converts.

    Here rather than at creation: which one a collection is follows from what it holds,
    so it is changed while looking at the contents rather than picked as a mode before
    there are any. Going Manual keeps what the rule found; going Dynamic opens a rule
    over the games already named.
    """
    with ui.row().classes("items-center gap-3 w-full no-wrap"):
        choice = ui.toggle({"manual": "Manual", "dynamic": "Dynamic"},
                           value="dynamic" if dynamic else "manual") \
            .props("dense no-caps unelevated").classes("hub-kind-toggle")

        async def changed() -> None:
            wanted = choice.value
            if wanted == ("dynamic" if dynamic else "manual"):
                return
            if wanted == "dynamic":
                _start_rule(context)
                return
            await _keep_result(context)

        choice.on_value_change(changed)
        ui.label("Fills itself from the library" if dynamic
                 else "Holds what you put in it").classes("hub-help min-w-0")


def _start_rule(context: dict[str, Any]) -> None:
    """Begin a rule without writing one. An empty criteria block matches everything,
    which is the honest starting point and is only stored once it is saved."""
    context["draft"]["filters"] = dict(_stored_filters(_collection(context)))
    asyncio.create_task(context["rebuild"]())


def _stored_filters(row: dict[str, Any]) -> dict[str, Any]:
    return dict(row.get("filters") or {})


def _draft_filters(context: dict[str, Any], row: dict[str, Any]) -> dict[str, Any]:
    """The rule being edited, which is the stored one until somebody touches it.

    Keyed on the draft *having* a filters block, never on that block being truthy: a
    rule somebody has just started is empty, and empty is falsy, so a truth test cannot
    tell "no rule" from "a rule with nothing set yet". The store draws the same
    distinction the same way.
    """
    if "filters" in context["draft"]:
        return dict(context["draft"]["filters"])
    return _stored_filters(row)


def _drafting(context: dict[str, Any]) -> bool:
    return "filters" in context["draft"]


def _is_dirty(context: dict[str, Any], row: dict[str, Any]) -> bool:
    """Whether what is on screen differs from what is stored.

    Starting a rule on a list that had none counts, even before anything is set: saving
    it would turn a list into something that fills itself, which is the change.
    """
    if _drafting(context) and not _is_dynamic(row):
        return True
    return _draft_filters(context, row) != _stored_filters(row)


def _axis_rows(context: dict[str, Any], row: dict[str, Any]) -> None:
    """One control per axis, from the registry rather than a list written here.

    Section 2.15 makes the registry the only place an axis is named, so a new one
    appears the moment core declares it - including how many values it takes.
    """
    current = _draft_filters(context, row)
    entries: list[tuple[Any, Any]] = []
    for axis in context.get("axes") or []:
        name = str(axis.get("name") or "")
        # The pair to `rating`, not an axis anybody sets on its own.
        if name == "rating_or_higher":
            continue
        entries.append((_axis_label(axis), _axis_control(context, axis, current)))
    _rows(ui, entries)


def _axis_label(axis: dict[str, Any]) -> str:
    """What to call an axis in a label column.

    The registry's label, not its `summary`: the summaries are sentences written to
    explain an axis ("First letter of the title, as sorted"), and a column of sentences
    is not a column of labels. The sentence becomes the tooltip.
    """
    return str(axis.get("label") or "") or humanize(axis.get("name") or "")


def _axis_control(context: dict[str, Any], axis: dict[str, Any],
                  current: dict[str, Any]) -> Callable[[], None]:
    """One control per axis kind, sized by how many values the axis takes."""
    name = str(axis.get("name") or "")
    kind = str(axis.get("kind") or "")
    many = bool(axis.get("many"))
    values = list(axis.get("values") or [])
    summary = str(axis.get("summary") or "")

    def changed(value) -> None:
        filters = _draft_filters(context, _collection(context))
        filters[name] = value
        context["draft"]["filters"] = filters
        asyncio.create_task(context["rebuild"]())

    def draw() -> None:
        if kind == "flag":
            # Three states, not two: absent says nothing about play, while true and
            # false are both criteria. A switch could only ever say two of the three.
            control = ui.select({"": "Any", "yes": "Yes", "no": "No"},
                                value={True: "yes", False: "no"}.get(
                                    current.get(name), "")) \
                .props("dense outlined").classes("w-full min-w-0")
            control.on_value_change(
                lambda: changed({"": None, "yes": True, "no": False}[control.value]))
        elif many:
            control = ui.select(values, multiple=True,
                                value=_selected(current.get(name)),
                                with_input=len(values) > 12) \
                .props('dense outlined use-chips '
                       'popup-content-class="hub-picker-popup"') \
                .classes("w-full min-w-0")
            control.on_value_change(lambda: changed(list(control.value or [])))
        else:
            chosen = _selected(current.get(name))
            control = ui.select([UNCONSTRAINED, *values],
                                value=chosen[0] if chosen else UNCONSTRAINED) \
                .props("dense outlined").classes("w-full min-w-0")
            control.on_value_change(lambda: changed(control.value))
        if summary:
            control.tooltip(summary)

    return draw


def _selected(value) -> list[str]:
    """A criterion as the list a multi-select shows. "All" is how a criterion says it
    constrains nothing, so it is an empty selection rather than a chip reading "All"."""
    if isinstance(value, list):
        chosen = [str(v) for v in value]
    else:
        chosen = [part.strip() for part in str(value or "").split(",") if part.strip()]
    return [v for v in chosen if v != UNCONSTRAINED]


def _rule_sentence(context: dict[str, Any], row: dict[str, Any]) -> str:
    """The rule, in words, with its connectives showing.

    People ask for AND/OR controls when they cannot tell what they are getting: two
    manufacturers selected is an OR, and a reader who assumes AND sees rows they cannot
    explain. Saying "or" costs a line and removes the question.
    """
    current = _draft_filters(context, row)
    said = []
    for axis in context.get("axes") or []:
        name = str(axis.get("name") or "")
        if name == "rating_or_higher":
            continue
        if name == "played":
            if current.get(name) is not None:
                said.append("it has been played" if current[name]
                            else "it has never been played")
            continue
        chosen = _selected(current.get(name))
        if chosen:
            said.append(f"{_axis_label(axis)} is "
                        + " or ".join(f"\u201c{v}\u201d" for v in chosen))
    if not said:
        return "Everything in the library, so far."
    return "Every game where " + ", and ".join(said) + "."


def _ordering_rows(context: dict[str, Any], row: dict[str, Any],
                   *, arrangeable: bool) -> None:
    """How the collection is presented: its order, its paging, and how much of it.

    `manual` order only where the membership is stable enough to arrange. A rule
    contributes rows that are not in the array, so an arrangement could not say where
    they go - section 4 leaves that undefined and the API refuses it.
    """
    ordered = _order_control(context, row, arrangeable=arrangeable)
    entries: list[tuple[Any, Any]] = [(HEADING, "Presentation")]
    entries.append(("Ordered by", ordered["by"]))
    if (row.get("order_by") or DEFAULT_ORDER_BY) != MANUAL_ORDER:
        # Not a setting that happens to be off: a direction on a hand-arranged list is
        # not a question, so the row is absent rather than disabled.
        entries.append(("Direction", ordered["direction"]))
    entries.append(("Paging", _paging_control(context, row)))
    entries.append(("Limit", _limit_control(context, row)))
    _rows(ui, entries)


def _paging_control(context: dict[str, Any],
                    row: dict[str, Any]) -> Callable[[], None]:
    """Which boundary the frontend pages between.

    Empty is a value - it says follow the player's own setting - so it is an option
    rather than the absence of one.
    """
    current = row.get("paging_group") or ""

    def draw() -> None:
        field = ui.select({"": "Follow the player", "sort": "By sort group",
                           "count": "By a fixed number"}, value=current) \
            .props("dense outlined").classes("w-full min-w-0")

        async def changed() -> None:
            await _patch(context, {"paging_group": field.value})

        field.on_value_change(changed)

    return draw


def _rule_actions(context: dict[str, Any], row: dict[str, Any]) -> None:
    """Save the rule, put it back, or keep what it found instead.

    Three, because a rule being edited has three honest ends: store it, abandon it, or
    take its result and stop being a rule at all - which is what makes criteria a way
    of building a list as well as a rule to keep.
    """
    dirty = _is_dirty(context, row)
    with ui.row().classes("items-center gap-2 w-full no-wrap mt-3"):
        if dirty:
            ui.button("Save the rule", icon="check",
                      on_click=lambda: _save_rule(context)) \
                .props("dense no-caps unelevated size=sm")
            ui.button("Discard", on_click=lambda: _discard_rule(context)) \
                .props("flat dense no-caps size=sm")
        elif _is_dynamic(row):
            ui.button("Keep what it found", icon="push_pin",
                      on_click=lambda: _keep_result(context)) \
                .props("flat dense no-caps size=sm").classes("hub-action") \
                .tooltip("Store these games and drop the rule")
    if dirty:
        ui.label("Not saved yet. The frontend still shows what is stored.") \
            .classes("hub-help mt-1 text-warning")


async def _save_rule(context: dict[str, Any]) -> None:
    """Write the rule, then stop drafting - in that order, and not through `_patch`.

    `_patch` rebuilds the panel as its last act, so dropping the draft after calling it
    drops it after the rebuild has already read it: the rule saves and the panel still
    says "not saved yet". The draft is only discarded once the write has come back, so
    a failed save leaves the edit where it was.
    """
    row = _collection(context)
    filters = {key: value for key, value in _draft_filters(context, row).items()
               if key not in ("order_by", "direction")}
    try:
        await run.io_bound(context["library"].patch_collection, row["name"],
                           {"filters": filters})
    except Exception as exc:
        ui.notify(f"Could not save: {exc}", type="negative")
        return
    context["draft"].pop("filters", None)
    await context["rebuild"]()


async def _discard_rule(context: dict[str, Any]) -> None:
    context["draft"].pop("filters", None)
    await context["rebuild"]()


async def _keep_result(context: dict[str, Any]) -> None:
    """Materialise: what the rule matches becomes the membership and the rule goes."""
    library = context["library"]
    try:
        await run.io_bound(library.keep_collection_result, _collection(context)["name"])
    except Exception as exc:
        ui.notify(f"Could not do that: {exc}", type="negative")
        return
    ui.notify("Kept the games; the rule is gone", type="positive")
    await context["rebuild"]()


def _order_control(context: dict[str, Any], row: dict[str, Any],
                   *, arrangeable: bool) -> dict[str, Callable[[], None]]:
    choices = {MANUAL_ORDER: "Manual", **SORT_LABELS} if arrangeable \
        else dict(SORT_LABELS)
    current = row.get("order_by") or DEFAULT_ORDER_BY
    held: dict[str, Any] = {"by": current if current in choices else DEFAULT_ORDER_BY,
                            "direction": row.get("direction") or "asc"}

    async def save() -> None:
        await _patch(context, {"order_by": held["by"], "direction": held["direction"]})

    # Each handler is a coroutine handed over whole. A lambda returning a *tuple* that
    # happens to contain one is not awaitable, so nicegui drops it and the control
    # changes on screen while nothing is written.
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
    """How many games the frontend is handed. Empty means all of them.

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
            ui.notify("A limit is a whole number of games", type="warning")

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


# --- what the collection holds ----------------------------------------------------


async def _result_region(context: dict[str, Any], row: dict[str, Any]) -> None:
    """What is in it, beside the rule that decides.

    Two things can be on screen here and they are not the same, so they are not mixed:
    the *stored* membership, which knows why each row is there and can be acted on, and
    a *preview* of a rule that has not been saved, which is a question rather than a
    fact. Offering "exclude this" on a row of an unsaved rule would be acting on
    something that does not exist yet.
    """
    dirty = _is_dirty(context, row)
    if dirty:
        await _preview_rows(context, row)
        return
    _stored_rows(context, row)


async def _preview_rows(context: dict[str, Any], row: dict[str, Any]) -> None:
    """What the rule being edited would match. Nothing is stored to ask this."""
    library = context["library"]
    filters = {key: value for key, value in _draft_filters(context, row).items()
               if key not in ("order_by", "direction")}
    try:
        answer = await run.io_bound(library.preview_filters, filters, row.get("limit"))
    except Exception as exc:
        ui.label(f"Could not work that out: {exc}").classes("hub-help text-warning")
        return
    entries = answer.get("entries") or []
    ui.label(f"{answer.get('count', len(entries))} games, if you save this") \
        .classes("hub-card-title")
    ui.label("A preview. Nothing here is stored yet.").classes("hub-help mb-2")
    if not entries:
        ui.label("Nothing matches this rule.").classes("hub-help")
    for entry in entries[:200]:
        game = entry.get("game") or {}
        with ui.row().classes("items-center gap-2 w-full no-wrap py-1 hub-index-item"):
            ui.label(str(game.get("name") or "")) \
                .classes("text-xs grow min-w-0 truncate")
    if len(entries) > 200:
        ui.label(f"...and {len(entries) - 200} more").classes("text-xs opacity-50")


# What a member points at, read off the *table* entry rather than the member.
# `member.origin` is provenance - who put this here, a person or the rule - and
# `tables[0].origin` is the axis this vocabulary is about: `named` means the member
# holds to that table, `default` means it resolves through whatever the game offers.
# Reading the wrong one made every stored member report as specific.
_TABLE_STATE = {
    "named": game_tables.FIXED,
    "default": game_tables.FOLLOWS,
    "missing": game_tables.GONE,
}


def _member_state(member: dict[str, Any]) -> str:
    tables = member.get("tables") or []
    if not tables:
        return game_tables.GONE
    return _TABLE_STATE.get(str(tables[0].get("origin") or ""), game_tables.FOLLOWS)
# Not a thing a reference points at, so it keeps its own word.
_EXCLUDED = ("Excluded", "Kept out of this collection")


def _stored_rows(context: dict[str, Any], row: dict[str, Any]) -> None:
    """The stored membership, each row saying why it is there and what undoes it."""
    membership = context.get("membership") or {}
    members = membership.get("members") or []
    find = (context["state"].setdefault("member_find", {})
            .get(_collection(context)["name"], "")).strip().lower()
    if find:
        members = [m for m in members
                   if find in str(m.get("name") or "").lower()]
    # Counted after the filter, not before: the count describes what is on screen, and
    # reporting the whole collection's tally over a filtered list read "42 of 16".
    playable = sum(1 for m in members if m.get("included"))
    with ui.row().classes("items-center gap-2 w-full no-wrap"):
        # Tables, not games: a collection resolves to entries and an entry is a table
        # (COLLECTIONS 2.5), so a game that named two of its tables contributes two.
        # Calling them games is wrong in exactly the case the count is needed for.
        total = len(members)
        word = "table" if total == 1 else "tables"
        ui.label(f"{playable} of {total} {word}" if playable != total
                 else f"{total} {word}").classes("hub-card-title")
        ui.space()
        # The key, beside the count rather than above the rows: a legend the reader
        # scrolls away from stops being one, and this sits in the header that stays.
        if members or find:
            with ui.row().classes("items-center gap-2 no-wrap hub-member-key") \
                    .tooltip(game_tables.KEY_DETAIL):
                for shown, word in game_tables.KEY_WORDS:
                    ui.element("span").classes(game_tables.mark(shown))
                    ui.label(word)
    if len(context.get("membership", {}).get("members") or []) > 8:
        name = _collection(context)["name"]
        box = ui.input(placeholder="Find in this collection") \
            .props("dense outlined clearable debounce=250") \
            .classes("w-full mb-2 mt-1")
        box.value = find

        async def look() -> None:
            context["state"]["member_find"][name] = box.value or ""
            await context["rebuild"]()

        box.on_value_change(look)
    # Arranging is only offered where the order *is* the arrangement, and only a static
    # list has one: a rule contributes rows that are not in the array, so there would
    # be nowhere for them to sit.
    kept = [m for m in members if (m.get("origin") or "") != "excluded"]
    # Not while a find is on: what is drawn is a subset, and an order has to be the
    # whole membership - dragging inside a filtered list can only send a partial one.
    arrange = (not _is_dynamic(row) and not find
               and (row.get("order_by") or "") == MANUAL_ORDER
               and len([m for m in members if m.get("origin") == "named"]) > 1)
    excluded = [m for m in members if (m.get("origin") or "") == "excluded"]
    with ui.column().classes("gap-0 w-full hub-member-list"):
        for member in kept:
            _member_line(context, member, arrange=arrange)
    # Grouped, not inline: a handful of rows somebody took out do not belong scattered
    # through forty they left in, and they are the ones most likely to be wanted back.
    if excluded:
        ui.label(f"Taken out ({len(excluded)})").classes("hub-group mt-3")
        with ui.column().classes("gap-0 w-full"):
            for member in excluded:
                _member_line(context, member)
    # `kept`, not `members`: the excluded rows are drawn in their own group below, so
    # the indices the browser reports are into this list. Sending `members` sent the
    # excluded ones too - a game both named and excluded appeared twice, and the route
    # refused the whole move.
    #
    # Handed to the listener through state rather than closed over, because the
    # listener is registered **once**. Registering inside the draw added one on every
    # rebuild, and NiceGUI answers a changed listener set by re-rendering the page -
    # which is why a reorder flashed the grid and the logo in the nav, neither of which
    # this panel touches.
    held = context["state"]
    held["member_move"] = (context, kept) if arrange else None
    if arrange:
        if not held.get("member_move_bound"):
            held["member_move_bound"] = True
            ui.on("hub_member_moved", lambda event: _moved(held, event.args))
        ui.run_javascript(_ARRANGE)
    _add_control(context, members)
    # A write rebuilds the panel, so the dock is a new element starting at the top -
    # and changing a member's table sent a forty-row list back to the beginning. The
    # position is remembered per collection, because arriving at a different one
    # should start at the top rather than wherever the last one was left.
    ui.run_javascript(_KEEP_SCROLL % _collection(context)["name"].replace("'", "\\'"))


async def _moved(state: dict[str, Any], moved: Any) -> None:
    """The list as it stands, read at the moment of the drop rather than captured when
    the listener was made - one listener now serves every redraw of the panel."""
    held = state.get("member_move")
    if held:
        await _reorder(held[0], held[1], moved)


async def _reorder(context: dict[str, Any], members: list[dict], moved: Any) -> None:
    """Put one game where it was dropped.

    Sent as the whole ordered list, which is what the route takes - atomic, and no
    index arithmetic on either side of the wire.
    """
    try:
        source, target = int(moved["from"]), int(moved["to"])
    except (KeyError, TypeError, ValueError):
        return
    order = [m["game"] for m in members]
    if not (0 <= source < len(order) and 0 <= target < len(order)) or source == target:
        return
    order.insert(target, order.pop(source))
    library = context["library"]
    try:
        await run.io_bound(library.set_collection_order,
                           _collection(context)["name"], order)
    except Exception as exc:
        ui.notify(f"Could not move it: {exc}", type="negative")
        return
    await context["rebuild"]()


def _member_line(context: dict[str, Any], member: dict[str, Any],
                 *, arrange: bool = False) -> None:
    origin = member.get("origin") or ""
    tables = member.get("tables") or []
    table = tables[0] if tables else {}
    # The chip slot is for what has happened to this row in this collection. Which
    # table it uses is a qualifier on the table line and is said there.
    state = _member_state(member)
    chip = _EXCLUDED if origin == "excluded" else (
        game_tables.reference_state(state) if state == game_tables.GONE else None)
    # The handle and the action sit outside the two text lines so they centre against
    # the row rather than against its first line, which read as pinned to the name.
    with ui.row().classes("items-center gap-2 w-full no-wrap hub-member-row") \
            .props(f'data-origin="{origin}"'):
        if arrange:
            # Focusable, because the keyboard path grabs from here: without a tab stop
            # the arrangement is mouse-only, which is the same trap the hover-revealed
            # row action had.
            ui.icon("drag_indicator").classes("hub-drag-handle") \
                .props('tabindex=0 role=button') \
                .tooltip("Drag to move, or press Space and use the arrow keys")
        with ui.column().classes("gap-0 grow min-w-0"):
            with ui.row().classes("items-center gap-2 w-full no-wrap"):
                ui.label(member.get("name") or member.get("game") or "") \
                    .classes("hub-member-name grow min-w-0 truncate")
                if chip:
                    ui.label(chip[0]).tooltip(chip[1]) \
                        .classes("hub-member-chip hub-chip-warn")
            # The table sits under its game and close to it, because the two are one
            # answer - which of this game's tables this collection holds.
            said = game_tables.table_name(table) if table else ""
            if said:
                # The line already answers "which table does this use?", so it is also
                # where that is changed - no new place to learn, and the glyph doubles
                # as the affordance. Excluded rows are not in the collection and have
                # nothing to point anywhere.
                _table_choice(context, member, state, table, said,
                              editable=origin != "excluded")
            elif table.get("origin") == "missing":
                ui.label("Names a table this library does not have") \
                    .classes("hub-member-table text-warning")
        with ui.element("div").classes("hub-row-action"):
            _member_action(context, member, origin)


def _table_choice(context: dict[str, Any], member: dict[str, Any], state: str,
                  table: dict[str, Any], said: str, *, editable: bool) -> None:
    """The table line, and the menu that changes which table this member names.

    COLLECTIONS 2.12 makes naming a table a tool of its own - *exactly these, frozen* -
    and the API has carried it since the member routes took a `table`. Nothing in the
    UI reached it, so every row read `Game Default` whatever the collection stored.
    """
    with ui.row().classes("items-center gap-2 no-wrap w-full min-w-0 "
                          "hub-member-table-line") as line:
        # Leading the *table* line, because that is what it qualifies - which table
        # this entry uses. On the name line it would read as a mark about the game.
        # The word the key uses, not a second phrasing of it: hovering a mark and
        # reading the legend should not teach two different names for one state. What
        # the difference *costs* stays on the key's own tooltip.
        ui.element("span").classes(game_tables.mark(state)) \
            .tooltip(game_tables.reference_state(state)[0])
        # The same line, and the same tooltip, as a game's Tables section: version and
        # author on screen, the filename a hover away. One formatter, so the two
        # surfaces cannot drift apart.
        ui.label(said).classes("hub-member-table truncate grow min-w-0") \
            .tooltip(str(table.get("filename") or ""))
        if not editable:
            return
        ui.icon("expand_more").classes("hub-member-table-caret")
        line.classes(add="cursor-pointer")
        # Anchored inside the element it belongs to. Built as a sibling it lands
        # wherever the parent row happens to start, which put an earlier menu 726px
        # from the control that opened it.
        with line, ui.menu().props('anchor="bottom left" self="top left"'):
            holder = ui.column().classes("gap-0 w-full items-stretch")
        # Filling only. The menu is a child of this line, so Quasar already opens and
        # closes it on a click here - calling `open()` as well reopened it in the same
        # gesture that closed it, which read as the menu refusing to shut.
        line.on("click", lambda: _fill_table_menu(context, member, table, holder))


async def _fill_table_menu(context: dict[str, Any], member: dict[str, Any],
                           table: dict[str, Any], holder: Any) -> None:
    """This game's tables, read when asked for rather than with every row.

    One read per game and it is cached, but doing it while drawing forty rows would be
    forty requests on the loop - which `api.py` refuses outright.
    """
    game = str(member.get("game") or "")
    named = str(table.get("id") or "") if table.get("origin") == "named" else ""
    try:
        choices = await run.io_bound(context["library"].tables_for, game)
    except Exception as exc:
        ui.notify(f"Could not read this game's tables: {exc}", type="negative")
        return
    # Every table this collection already holds for this game - what its refs *resolve
    # to*, not just what they name. Asking only about named tables offered the file a
    # following ref already resolves to, so a one-table game was told it could add the
    # table it has: "Add another" and "Uses" read as the same entry (Chris, 2026-08-30).
    # An excluded ref counts too: offering a table that is being kept out would add a
    # member the collection immediately drops again.
    spoken = {str(t.get("id") or "")
              for other in (context.get("membership") or {}).get("members") or []
              if str(other.get("game") or "") == game
              for t in other.get("tables") or []}
    # Tables another of this game's rows already names. A pairing appears once (2.10),
    # so pointing this row at one of them cannot be stored - it is shown and refused
    # rather than hidden, because an entry that vanishes without a reason is the same
    # puzzle as a row that vanishes without one.
    taken: set[str] = set()
    default_taken = False
    for other in (context.get("membership") or {}).get("members") or []:
        if other is member or str(other.get("game") or "") != game:
            continue
        if _member_state(other) == game_tables.FOLLOWS:
            # Another row already follows this game, and a second bare ref is the same
            # pairing twice. Offering it was an error the user could only find by
            # picking it.
            default_taken = True
        else:
            taken.update(str(t.get("id") or "") for t in other.get("tables") or [])
    # What following this game gets you today. Shown on every game, including one with
    # a single table where it can only be that table: the rule stays the rule, and an
    # exception is one more thing for a reader to know.
    offers = next((one for one in choices if one.get("default")), None)
    holder.clear()
    with holder:
        # The question this group answers, not the verb on its own: "Uses" was the
        # verb without its object, and a reader had to infer the subject.
        ui.item_label("Which table").props("header").classes("hub-menu-header")
        _table_menu_item(context, member, "", named,
                         game_tables.FOLLOWS,
                         game_tables.REFERENCE_WORDS[game_tables.FOLLOWS][0],
                         chosen=not named,
                         blocked="Already in this collection" if default_taken else "",
                         under=game_tables.table_name(offers) if offers else "")
        for one in choices:
            table_id = str(one.get("id") or "")
            _table_menu_item(context, member, table_id, named,
                             game_tables.FIXED,
                             game_tables.table_name(one), chosen=table_id == named,
                             blocked="Already in this collection"
                             if table_id in taken else "")
        # The tournament case: a collection holding two versions of one game, each
        # named (COLLECTIONS 2.10 and 2.12). Switching this row cannot express it -
        # that is one ref pointing somewhere else - so adding is its own verb.
        spare = [one for one in choices if str(one.get("id") or "") not in spoken]
        if spare:
            ui.separator()
            # "Insert", because it lands beside the row it was asked from rather than
            # at the end - and naming the game because this is the confusing half of
            # the menu, where being explicit beats being short (Chris, 2026-08-31).
            # Not "another user defined": every item here wears the mark for that and
            # the key says what it means, so the state would restate what is on screen.
            ui.item_label("Insert another table from this game").props("header") \
                .classes("hub-menu-header")
            for one in spare:
                _add_table_item(context, game, one, after=named)


def _table_menu_item(context: dict[str, Any], member: dict[str, Any], table_id: str,
                     was: str, state: str, label: str, *, chosen: bool,
                     blocked: str = "", under: str = "") -> None:
    """One choice. The current one is marked and inert - a menu that lets you pick what
    is already true reports a change that did not happen - and so is one the collection
    cannot hold, which says why instead of disappearing.

    `under` names what this entry resolves to today, which only Game Default needs: from
    a row pinned to some other table, choosing it was a blind pick, and the two entries
    read as different destinations when what actually differs is what happens when a new
    table arrives.
    """
    async def pick() -> None:
        if chosen or blocked:
            return
        try:
            await run.io_bound(context["library"].set_member_table,
                               _collection(context)["name"],
                               str(member.get("game") or ""), table_id, was)
        except Exception as exc:
            ui.notify(f"Could not change it: {exc}", type="negative")
            return
        await context["rebuild"]()

    marked = "hub-menu-item"
    if chosen:
        marked += " hub-menu-on"
    elif blocked:
        marked += " hub-menu-blocked"
    item = ui.menu_item(on_click=pick).classes(marked)
    if blocked:
        # It stays open on a click it will not act on: closing would look like the
        # choice was taken.
        item.props("auto-close=false").tooltip(blocked)
    with item, ui.row().classes("items-center gap-2 no-wrap w-full"):
        ui.element("span").classes(f"hub-menu-mark {game_tables.mark(state)}")
        with ui.column().classes("gap-0 grow min-w-0"):
            ui.label(label).classes("hub-menu-table-name")
            if under:
                ui.label(under).classes("hub-menu-sub")
        if chosen:
            ui.icon("check").classes("hub-menu-check")
        elif blocked:
            ui.icon("block").classes("hub-menu-check hub-menu-blocked-mark")


def _add_table_item(context: dict[str, Any], game: str, table: dict[str, Any],
                    *, after: str) -> None:
    """A second ref for this game, naming another of its tables.

    Landed next to the row it was asked from, not at the end: in a forty-row collection
    the end is off screen, and a new row you cannot see is indistinguishable from a
    click that did nothing.
    """
    async def add() -> None:
        try:
            await run.io_bound(context["library"].add_to_collection,
                               _collection(context)["name"], game,
                               str(table.get("id") or ""), after)
        except Exception as exc:
            ui.notify(f"Could not add it: {exc}", type="negative")
            return
        await context["rebuild"]()

    with ui.menu_item(on_click=add).classes("hub-menu-item"), \
            ui.row().classes("items-center gap-2 no-wrap w-full"):
        # A plus, not the ● the entries above wear. Both groups named the same table
        # with the same mark, so the pair read as one thing listed twice and the
        # heading was the only thing telling them apart - which a heading loses at a
        # glance (Chris, 2026-08-30). The mark carries the verb now.
        ui.icon("add").classes("hub-menu-add")
        ui.label(game_tables.table_name(table)).classes("hub-menu-table-name grow min-w-0")


def _member_action(context: dict[str, Any], member: dict[str, Any],
                   origin: str) -> None:
    """The one thing this row's state makes sense to do.

    Removing says the same word whichever way the row got here, because that is the
    one intent a reader has. Underneath it differs - a matched row has to be recorded
    as an exclusion or the rule finds it again - but the list says so by moving it
    into "Taken out", which is better than a tooltip explaining it in advance.
    """
    library = context["library"]
    name = _collection(context)["name"]
    game = member.get("game") or ""
    tables = member.get("tables") or []
    table = str(tables[0].get("id", "")) if tables else ""

    async def act(what, *args, said: str) -> None:
        try:
            await run.io_bound(what, *args)
        except Exception as exc:
            ui.notify(f"Could not do that: {exc}", type="negative")
            return
        ui.notify(said, type="positive")
        await context["rebuild"]()

    # The ref this row *is*, not the table it resolves to. An exclusion naming no
    # table resolves to one all the same, and sending that back matched nothing.
    ref_table = str(member.get("ref_table") or "")
    if origin == "excluded":
        ui.button(icon="undo",
                  on_click=lambda: act(library.unexclude_from_collection, name, game,
                                       ref_table, said="Back in the list")) \
            .props("flat dense round size=sm").tooltip("Put this back")
    elif origin == "filter":
        ui.button(icon="close",
                  on_click=lambda: act(library.exclude_from_collection, name, game,
                                       table, said="Taken out")) \
            .props("flat dense round size=sm").tooltip("Remove from this collection")
    else:
        # The ref this row *is*, not the table it resolves to: a row that follows the
        # game names no table, so its identity is "". Passing "" used to mean every
        # ref for the game, which is how deleting one row deleted three.
        ui.button(icon="close",
                  on_click=lambda: act(library.remove_from_collection, name, game,
                                       ref_table, said="Removed")) \
            .props("flat dense round size=sm").tooltip("Remove from this collection")


def _add_control(context: dict[str, Any], members: list[dict]) -> None:
    """Add a game the rule did not find, or that there is no rule to find.

    A game, not a table: a member with no table named follows whichever table is the
    game's default, which is what somebody adding a game to a list almost always
    means. Holding it to one table is the unusual intent and is a second act.
    """
    here = {m.get("game") for m in members}
    choices = {game["id"]: game.get("name") or game["id"]
               for game in context["library"].games if game["id"] not in here}
    if not choices:
        return
    # Typed into, not scrolled: this is a picker over the whole library, and a list
    # that long is searched. `use-input` with no debounce filters from the first
    # character; `new-value-mode` is left off so only a real game can be chosen.
    picker = ui.select(choices, with_input=True, label="Add a game") \
        .props('dense outlined options-dense use-input input-debounce=0 '
               'hide-selected fill-input clearable '
               'popup-content-class="hub-picker-popup"') \
        .classes("w-full mt-3")

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


SECTIONS: tuple[Section, ...] = (
    # The game first, then the file: a table belongs to a game, and reading down is
    # reading from the thing that contains to the thing contained.
    Section("game_details", lambda _: "Game Details", _game_block),
    Section("table_details", lambda _: "Table Details", _table_block,
            subjects=frozenset({"table"})),
    # Beside the game's own facts: the match is how this game is identified, and the
    # section exists so that is something a person can see and change rather than an
    # opaque id in a text field.
    Section("vps", _vps_label, _vps_block, subjects=frozenset({"game", "table"})),
    Section("media", _media_label, _media_block, dock=True),
    # Beside Media, not under Details: both answer "what does this game hold", one
    # for what a screen shows and one for what a launch needs.
    Section("assets", _assets_label, _assets_block),
    # Two, not three. A rule and what it matches are one thing to look at, so the rule
    # sits in the browse region and the result in the dock beside it.
    Section("collection_details", lambda _: "Details", _collection_details,
            subjects=frozenset({"collection"})),
    Section("collection_contents", _contents_label, _collection_contents,
            subjects=frozenset({"collection"}), dock=True),
)
