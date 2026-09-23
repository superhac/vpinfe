"""Getting games into a collection: the one add every surface offers, and its Undo."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable, Iterable, Sequence
from dataclasses import dataclass, field
from typing import Any

from nicegui import run, ui

from common.games.collection_store import MANUAL_ORDER
from common.i18n import t
from console import offload, undo, verbs

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
