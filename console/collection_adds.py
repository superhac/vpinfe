"""Getting games into a collection: the one add every surface offers, and its Undo."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable, Iterable, Sequence
from dataclasses import dataclass, field
from functools import partial
from typing import Any

from nicegui import run, ui

from common.games.collection_store import MANUAL_ORDER
from common.i18n import t
from console import dialog as frame
from console import offload, panel, remembered, undo, verbs

logger = logging.getLogger("vpinfe.console.collection_adds")

# What a row being added is, which is what the words count.
GAMES = "games"
TABLES = "tables"

# Member origins in a collection's stored membership. `missing` names a game this
# library no longer has - still a stored row, and still a place in the order.
_IN = ("named", "filter")
_STORED = ("named", "missing")

_ADDED = {GAMES: "console.adds.added_games", TABLES: "console.adds.added_tables"}
_ADDED_HELD = {GAMES: "console.adds.added_games_held",
               TABLES: "console.adds.added_tables_held"}
_EXCEPTION = {GAMES: "console.adds.exception_games",
              TABLES: "console.adds.exception_tables"}
_EXCEPTION_HELD = {GAMES: "console.adds.exception_games_held",
                   TABLES: "console.adds.exception_tables_held"}


@dataclass(frozen=True)
class Row:
    """A game following its default table, or one table of it held to that table."""

    game: str
    table: str = ""


@dataclass
class Wrote:
    """What one add changed, which is what its Undo takes back."""

    smart: bool = False
    held: int = 0
    written: list[Row] = field(default_factory=list)
    lifted: list[Row] = field(default_factory=list)
    put_back: int = 0
    # The order it had, where dropping at a place made it Custom Order.
    order: dict[str, str] | None = None

    @property
    def added(self) -> int:
        return len(self.written) + self.put_back


def holds(members: Sequence[dict[str, Any]]) -> tuple[set[str], set[tuple[str, str]]]:
    """The games a collection holds and each (game, table) it plays, read off its stored
    membership. A game past the limit is held; one taken out is not."""
    out = {str(one.get("game") or "") for one in members
           if one.get("origin") == "excluded" and not one.get("ref_table")}
    games: set[str] = set()
    tables: set[tuple[str, str]] = set()
    for member in members:
        game = str(member.get("game") or "")
        if member.get("origin") not in _IN or game in out:
            continue
        table = (member.get("tables") or [{}])[0]
        if table.get("origin") == "excluded":
            continue
        games.add(game)
        if table.get("id"):
            tables.add((game, str(table["id"])))
    return games, tables


def held_rows(members: Sequence[dict[str, Any]], rows: Iterable[Row]) -> list[Row]:
    games, tables = holds(members)
    return [row for row in rows
            if ((row.game, row.table) in tables if row.table else row.game in games)]


def keeping_out(members: Sequence[dict[str, Any]], row: Row) -> list[Row]:
    """The exclusions that keep `row` out: every one naming its game for a game, and the
    whole game's and that table's for one table."""
    return [Row(str(one.get("game") or ""), str(one.get("ref_table") or ""))
            for one in members
            if one.get("origin") == "excluded" and one.get("game") == row.game
            and (not row.table or str(one.get("ref_table") or "") in ("", row.table))]


def listed_order(members: Sequence[dict[str, Any]]) -> list[str]:
    """One game id per stored row, as the list shows them: what setting an order takes."""
    return [str(one.get("game") or "") for one in members
            if one.get("origin") in _STORED]


def write(library: Any, name: str, rows: Sequence[Row], at: int | None = None) -> Wrote:
    """Put `rows` in `name` and answer what changed. Blocking: run it off the loop.

    A row it holds is left alone, and one it keeps out is let back in before anything is
    written. `at` places the new rows in a collection without rules, and makes its order
    Custom Order.
    """
    collection = next((one for one in library.load_collections()
                       if one.get("name") == name), None)
    if collection is None:
        raise LookupError(t("console.page.no_longer_library"))
    wrote = Wrote(smart=(collection.get("type") or "") == "filter")
    members = library.collection_members(name).get("members") or []
    held = held_rows(members, rows)
    wrote.held = len(held)
    wanted = [row for row in rows if row not in held]
    for row in wanted:
        for ref in keeping_out(members, row):
            if ref not in wrote.lifted:
                library.unexclude_from_collection(name, ref.game, ref.table)
                wrote.lifted.append(ref)
    if wrote.lifted:
        members = library.collection_members(name).get("members") or []
        back = held_rows(members, wanted)
        wrote.put_back = len(back)
        wanted = [row for row in wanted if row not in back]
    before = listed_order(members)
    for row in wanted:
        library.add_to_collection(name, row.game, row.table)
        wrote.written.append(row)
    if at is not None and wanted and not wrote.smart:
        place = max(0, min(at, len(before)))
        if (collection.get("order_by") or "") != MANUAL_ORDER:
            wrote.order = {"order_by": str(collection.get("order_by") or ""),
                           "direction": str(collection.get("direction") or "")}
        library.set_collection_order(
            name, before[:place] + [row.game for row in wanted] + before[place:])
    return wrote


def unwrite(library: Any, name: str, wrote: Wrote) -> None:
    """Take back what `write` did. Blocking: run it off the loop.

    A row already gone is not an error: the collection has what Undo asked for.
    """
    members = library.collection_members(name).get("members") or []
    stored = {(str(one.get("game") or ""), str(one.get("ref_table") or ""))
              for one in members if one.get("origin") in _STORED}
    for row in wrote.written:
        if (row.game, row.table) in stored:
            library.remove_from_collection(name, row.game, row.table)
    for ref in wrote.lifted:
        library.exclude_from_collection(name, ref.game, ref.table)
    if wrote.order and wrote.order.get("order_by"):
        library.patch_collection(name, {key: value for key, value in wrote.order.items()
                                        if value})


def said(name: str, wrote: Wrote, what: str) -> str:
    """The message, counted in what the rows are."""
    if not wrote.added:
        return t("console.adds.all_held", count=wrote.held, name=name)
    exception = is_exception(wrote)
    if wrote.held:
        keys = _EXCEPTION_HELD if exception else _ADDED_HELD
        return t(keys[what], count=wrote.added, name=name, held=wrote.held)
    return t((_EXCEPTION if exception else _ADDED)[what], count=wrote.added, name=name)


def is_exception(wrote: Wrote) -> bool:
    """A smart collection's rules did not bring these in, so they stay on their own."""
    return wrote.smart and bool(wrote.written)


async def add(library: Any, name: str, rows: Iterable[Row], *, what: str = GAMES,
              at: int | None = None,
              then: Callable[[], Awaitable[Any]] | None = None) -> Wrote | None:
    """Add `rows` to `name`, say what happened, and offer the way back.

    `then` redraws whatever shows the collection, after the add and again after Undo.
    It may delete the element that asked, so the message is said through the page.
    """
    client = ui.context.client
    asked = list(dict.fromkeys(rows))
    try:
        wrote = await offload.io(write, library, name, asked, at)
    except Exception as exc:  # noqa: BLE001 - the reason belongs on screen
        ui.notify(t("said.could_not_add_it", exc=exc), type="negative")
        return None
    used(name)
    if then is not None:
        await then()

    async def reverse() -> None:
        await run.io_bound(unwrite, library, name, wrote)
        if then is not None:
            await then()

    with client:
        if not wrote.added:
            ui.notify(said(name, wrote, what), type="positive")
        else:
            undo.offer(said(name, wrote, what), reverse, warn=is_exception(wrote),
                       icon=verbs.SMART if is_exception(wrote) else None)
    return wrote


# --- taking games back out of the one the grid is narrowed to ------------------------


@dataclass
class Took:
    """What one removal changed, which is what its Undo puts back."""

    removed: list[Row] = field(default_factory=list)
    kept_out: list[str] = field(default_factory=list)
    # None where an order sorts the collection: only a hand arrangement is put back.
    order: list[str] | None = None

    @property
    def taken(self) -> int:
        return len({row.game for row in self.removed} | set(self.kept_out))


def take(library: Any, name: str, games: Sequence[str]) -> Took:
    """Take `games` out of `name`: every row naming one, and the rules' match kept out
    where its rules would bring it back. Blocking: run it off the loop."""
    collection = next((one for one in library.load_collections()
                       if one.get("name") == name), None)
    if collection is None:
        raise LookupError(t("console.page.no_longer_library"))
    wanted = set(games)
    members = library.collection_members(name).get("members") or []
    took = Took(order=listed_order(members)
                if collection.get("order_by") == MANUAL_ORDER else None)
    took.removed = [Row(str(one.get("game") or ""), str(one.get("ref_table") or ""))
                    for one in members
                    if one.get("origin") in _STORED and one.get("game") in wanted]
    for row in took.removed:
        library.remove_from_collection(name, row.game, row.table)
    if (collection.get("type") or "") == "filter":
        if took.removed:
            members = library.collection_members(name).get("members") or []
        games_now = holds(members)[0]
        took.kept_out = [game for game in games if game in games_now]
        for game in took.kept_out:
            library.exclude_from_collection(name, game, "")
    return took


def untake(library: Any, name: str, took: Took) -> None:
    """Put back what `take` took. Blocking: run it off the loop."""
    for game in took.kept_out:
        library.unexclude_from_collection(name, game, "")
    for row in took.removed:
        library.add_to_collection(name, row.game, row.table)
    if took.order:
        now = listed_order(library.collection_members(name).get("members") or [])
        if sorted(now) == sorted(took.order):
            library.set_collection_order(name, took.order)


async def remove(library: Any, name: str, games: Sequence[str], *,
                 then: Callable[[], Awaitable[Any]] | None = None) -> None:
    """Take `games` out of `name`, say so, and offer the way back."""
    client = ui.context.client
    try:
        took = await offload.io(take, library, name, list(games))
    except Exception as exc:  # noqa: BLE001 - the reason belongs on screen
        ui.notify(t("said.could_not_do_that", exc=exc), type="negative")
        return
    if then is not None:
        await then()

    async def reverse() -> None:
        await run.io_bound(untake, library, name, took)
        if then is not None:
            await then()

    key = "console.adds.taken_out_games" if took.kept_out and not took.removed \
        else "console.adds.removed_games"
    with client:
        undo.offer(t(key, count=took.taken, name=name), reverse)


# --- the collections added to last ---------------------------------------------

_RECENT = "recent_collections"
RECENT_HELD = 5


def recent(known: Iterable[str]) -> list[str]:
    """The collections added to most recently that still exist, newest first, for this
    Console user."""
    here = set(known)
    return [name for name in remembered.get(_RECENT) or [] if name in here][:RECENT_HELD]


def used(name: str) -> None:
    kept = [one for one in remembered.get(_RECENT) or [] if one != name]
    remembered.put(_RECENT, [name, *kept][:RECENT_HELD])


def renamed(old: str, new: str) -> None:
    held = remembered.get(_RECENT) or []
    if old in held:
        remembered.put(_RECENT, [new if one == old else one for one in held])


# --- what a grid's menus offer ----------------------------------------------------

_ADD_TO = {GAMES: "console.adds.add_games_to", TABLES: "console.adds.add_tables_to"}
_ADD_TO_COLLECTION = {GAMES: "console.adds.add_games_to_collection",
                      TABLES: "console.adds.add_tables_to_collection"}
_PICK_TITLE = {GAMES: "console.adds.pick_games", TABLES: "console.adds.pick_tables"}


@dataclass
class Offer:
    """Rows a menu offers to add, and what redraws the grid behind them."""

    library: Any
    rows: list[Row]
    what: str
    # Names the one row, for a title; empty in a bulk menu.
    subject: str
    then: Callable[[], Awaitable[Any]]
    # The collection the grid is narrowed to, whose Remove joins the menu.
    narrowed: str = ""


@dataclass
class Read:
    """What a menu needs to know before it is drawn."""

    kinds: dict[str, bool]
    recent: list[str]
    held: dict[str, list[dict[str, Any]]]


async def read(library: Any, narrowed: str = "") -> Read:
    """The collections, which were added to last, and what those hold. Off the loop."""
    collections = await offload.io(library.load_collections)
    kinds = {str(one.get("name") or ""): (one.get("type") or "") == "filter"
             for one in collections}
    last = recent(kinds)
    wanted = list(dict.fromkeys(last + ([narrowed] if narrowed in kinds else [])))
    held = await offload.io(library.held_members, wanted) if wanted else {}
    return Read(kinds=kinds, recent=last, held=held)


def holds_all(held: dict[str, list[dict[str, Any]]], name: str, rows: list[Row]) -> bool:
    members = held.get(name)
    return members is not None and len(held_rows(members, rows)) == len(rows)


def draw(offer: Offer, known: Read, close: Callable[[], Any]) -> None:
    """The adds for a grid's row or selection, drawn into the menu being built: the
    collection added to last, the recent ones under Add to Collection with the rest a
    dialog away, and Remove where the grid is narrowed to one."""
    bulk = not offer.subject
    count = len(offer.rows)

    def go(name: str) -> Callable[[], Any]:
        async def run_it() -> None:
            close()
            await add(offer.library, name, offer.rows, what=offer.what, then=offer.then)
        return run_it

    if known.recent:
        top = known.recent[0]
        _item(t(_ADD_TO[offer.what], count=count, name=top) if bulk
              else t("console.adds.add_to", name=top), go(top),
              smart=known.kinds.get(top, False),
              held=holds_all(known.held, top, offer.rows))
    parent = _item(t(_ADD_TO_COLLECTION[offer.what], count=count) if bulk
                   else t("console.adds.add_to_collection"), None, opens=True)
    with parent, ui.menu().props('anchor="top end" self="top start"') as sub:
        if known.recent:
            ui.item_label(t("console.adds.recent")).props("header") \
                .classes("console-menu-header")
            for name in known.recent:
                _item(name, go(name), smart=known.kinds.get(name, False),
                      held=holds_all(known.held, name, offer.rows))
            ui.separator()

        async def more() -> None:
            sub.close()
            close()
            await pick(offer)

        async def new() -> None:
            sub.close()
            close()
            await new_with(offer)

        _item(t("console.adds.more_collections"), more)
        _item(t("console.adds.new_collection"), new)
    if offer.narrowed and offer.narrowed in known.kinds and offer.what == GAMES:
        async def take_out() -> None:
            close()
            await remove(offer.library, offer.narrowed, [row.game for row in offer.rows],
                         then=offer.then)

        _item(t("console.adds.remove_games_from", count=count, name=offer.narrowed)
              if bulk else t("console.adds.remove_from", name=offer.narrowed), take_out)


def _item(label: str, act: Callable[[], Any] | None, *, smart: bool = False,
          held: bool = False, opens: bool = False) -> Any:
    """One entry: the Smart mark in the leading slot, In It in the trailing one. An entry
    already true is inert, and stays open on a click it will not act on."""
    def mark() -> None:
        with ui.icon(verbs.SMART).classes("console-menu-mark"):
            ui.tooltip(t("console.collections.smart.help")).classes("console-menu-tip")

    def trail() -> None:
        if held:
            ui.label(t("console.adds.in_it")).classes("console-menu-trail")
        else:
            ui.icon(verbs.DRILL).classes("console-menu-trail")

    return panel.menu_entry(label, None if held else act, mark=mark if smart else None,
                            trail=trail if held or opens else None,
                            classes="console-menu-blocked" if held else "",
                            auto_close=False)


# --- More Collections... and New Collection... ------------------------------------

_NEW = "\x00new"


async def pick(offer: Offer) -> None:
    """Every collection, typed into, with what each is and holds: the rest of the menu."""
    library = offer.library
    try:
        collections = await offload.io(library.load_collections)
        names = [str(one.get("name") or "") for one in collections]
        held = await offload.io(library.held_members, names) if names else {}
    except Exception as exc:  # noqa: BLE001 - the reason belongs on screen
        ui.notify(t("said.could_not_do_that", exc=exc), type="negative")
        return
    title = (t("console.adds.pick_one", name=offer.subject) if offer.subject
             else t(_PICK_TITLE[offer.what], count=len(offer.rows)))
    chosen = await _pick_one(title, collections, held, offer.rows)
    if chosen == _NEW:
        await new_with(offer)
    elif chosen:
        await add(library, chosen, offer.rows, what=offer.what, then=offer.then)


async def _pick_one(title: str, collections: list[dict[str, Any]],
                    held: dict[str, list[dict[str, Any]]], rows: list[Row]) -> str | None:
    chosen: dict[str, str] = {"name": ""}
    ordered = sorted(collections, key=lambda one: str(one.get("name") or "").casefold())
    with frame.opened(title) as box:
        with ui.element("div").classes("w-full px-3"):
            find = frame.field(placeholder=t("console.adds.find_collection"))
        with ui.element("div").classes("w-full px-3 mt-2 console-source-list "
                                       "console-collection-pick") as held_at:
            listing = ui.column().classes("w-full gap-1 console-pick-list")
        with ui.element("div").classes("px-3 mt-1"):
            panel.action(t("console.adds.new_collection"), lambda: box.submit(_NEW),
                         icon=verbs.CREATE)()
        with frame.footer():
            frame.cancel(lambda: box.submit(None))
            go = frame.answer(t("word.add"), lambda: box.submit(chosen["name"] or None),
                              icon=verbs.ADD)
        go.disable()

        def shown() -> list[dict[str, Any]]:
            typed = str(find.value or "").strip().casefold()
            return [one for one in ordered
                    if typed in str(one.get("name") or "").casefold()]

        def choose(name: str) -> None:
            chosen["name"] = name
            go.enable()
            draw_rows()

        def draw_rows() -> None:
            listing.clear()
            found = shown()
            with listing:
                if not found:
                    ui.label(t("console.adds.none_match")).classes("console-help")
                for one in found:
                    name = str(one.get("name") or "")
                    _collection_row(one, holds_all(held, name, rows),
                                    name == chosen["name"], partial(choose, name))

        def typed() -> None:
            pickable = [str(one.get("name") or "") for one in shown()
                        if not holds_all(held, str(one.get("name") or ""), rows)]
            if len(pickable) == 1:
                chosen["name"] = pickable[0]
                go.enable()
            elif chosen["name"] not in pickable:
                chosen["name"] = ""
                go.disable()
            draw_rows()

        find.on_value_change(typed)
        find.on("keydown.enter", lambda: box.submit(chosen["name"]) if chosen["name"]
                else None)
        draw_rows()
    frame.focus(box, find)
    # On the list's frame, which the server never redraws: a height set on the list
    # itself is wiped by the next redraw of its rows.
    box.on("show", lambda: ui.run_javascript(
        f"(() => {{ const el = document.getElementById('c{held_at.id}');"
        " if (el) el.style.height = el.offsetHeight + 'px'; })()"))
    box.open()
    return await box


def _collection_row(one: dict[str, Any], held: bool, chosen: bool,
                    take: Callable[[], None]) -> None:
    """One collection to pick: its name, what kind it is and how many games it has, and
    In It where it holds every row already."""
    smart = (one.get("type") or "") == "filter"
    count = int(one.get("count") or 0)
    classes = "items-center gap-3 w-full no-wrap console-source-row console-source-row--entry"
    classes += " console-source-row--held" if held else " console-source-row--pick"
    if chosen:
        classes += " console-source-row--chosen"
    row = ui.row().classes(classes)
    with row:
        if smart:
            ui.icon(verbs.SMART).classes("console-menu-mark") \
                .tooltip(t("console.collections.smart.help"))
        else:
            ui.element("span").classes("console-menu-mark")
        with ui.column().classes("gap-0 grow min-w-0"):
            ui.label(str(one.get("name") or "")).classes("console-source-name")
            ui.label(t("console.workbench.smart_games" if smart
                       else "console.workbench.hand_picked_games", count=count)) \
                .classes("console-help")
        if held:
            ui.label(t("console.adds.in_it")).classes("console-help shrink-0")
    if not held:
        row.on("click", take)


async def new_with(offer: Offer) -> None:
    """A new collection holding `offer`'s rows, made in one step."""
    async def made(name: str) -> None:
        await add(offer.library, name, offer.rows, what=offer.what, then=offer.then)

    ask_new(offer.library, made, announce=False)


def ask_new(library: Any, made: Callable[[str], Awaitable[Any]], *,
            announce: bool = True) -> None:
    """A name. Nothing else.

    The kind is not a question at creation: it is decided by what the collection ends up
    holding, and changed in the panel where the games and the rule both are. Asking up
    front would make it a mode. `announce` says Created, for a caller that says nothing
    else about it.
    """
    held: dict[str, Any] = {}

    async def keep() -> None:
        name = held["name"]
        wanted = (name.value or "").strip()
        if not wanted:
            name.props["error"] = True
            name.props["error-message"] = t("said.give_it_a_name")
            return
        dialog.close()
        try:
            created = await offload.io(library.create_collection, wanted, None)
        except Exception as exc:  # noqa: BLE001 - the reason belongs on screen
            ui.notify(t("said.could_not_do_that", exc=exc), type="negative")
            return
        if announce:
            ui.notify(t("console.collections.created", strip=wanted), type="positive")
        await made(str(created.get("name") or wanted))

    with frame.opened(t("console.collections.new_collection")) as dialog:
        panel.facts(ui, [(t("word.name"), lambda: held.update(name=frame.field()))])
        with frame.footer():
            frame.cancel(dialog.close)
            go = frame.answer(t("console.collections.create"), keep, icon=verbs.CREATE)
    frame.focus(dialog, held["name"])
    frame.enter_presses(go)
    dialog.open()
