"""One collection, resolved to the ordered list a frontend navigates.

Five steps, and the same answer whoever asks - the wheel and the API both arrive here:

    1. membership   filters, then members overriding them, then exclusions
    2. visibility   drop hidden - library-wide, and it beats a named table
    3. selection    the table a member named, or the game's default
    4. order        the member array, or a computed sort
    5. limit        keep the first N rows, if the collection caps itself

Both callers are named above because for ten days only one of them was true. The wheel
went through a second engine that read game ids and nothing else, so it could not see a
member naming a table, an exclusion, a limit or a stored order - and it matched "Last
Played" by string literal. A collection meant one thing over REST and another on the
surface a player actually uses.

An entry is a table with its game attached. Media is resolved by whoever serializes it,
because the play lens and the management lens want different amounts of it.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from common.games import collection_filters
from common.games.game_identity import game_id
from common.games.game_metadata import (
    game_rating,
    game_title,
    game_year,
    run_time_seconds,
    section,
    vpinfe_section,
)
from common.games.tables import (
    TABLE_FILENAME_KEY,
    TABLE_ID_KEY,
    entry_filename,
    entry_for_filename,
    recorded_default,
    table_entries,
    table_filenames,
)
from common.games.tables import default_table as resolve_default_name

MEMBER_GAME_KEY = "game"
MEMBER_TABLE_KEY = "table"

DEFAULT_ORDER = "title"


class UnresolvableCollectionError(Exception):
    """A collection this build cannot answer for, naming why.

    Raised rather than resolved-around: dropping a criterion we do not understand
    answers a different question, and does it silently.
    """

    def __init__(self, name: str, axes):
        self.name = name
        self.axes = list(axes)
        super().__init__(
            f"Collection {name!r} filters on {', '.join(self.axes)}, which this build "
            f"does not know. Update VPinFE to use it.")


@dataclass(frozen=True)
class Entry:
    """One row of the resolved list: a table, with the game it belongs to."""

    game: Any
    table: dict
    siblings: int

    @property
    def table_id(self) -> str:
        return str(self.table.get(TABLE_ID_KEY, "") or "")

    @property
    def filename(self) -> str:
        return entry_filename(self.table)

    # A player's list is entries rather than games, and the frontend's sorts read these
    # two off whatever they are handed. Forwarding beats teaching every sort both shapes.
    @property
    def meta_config(self):
        return getattr(self.game, "meta_config", {})

    @property
    def creation_time(self):
        return getattr(self.game, "creation_time", None)


def _user_value(game, key, fallback=0):
    try:
        return int(section(getattr(game, "meta_config", {}), "User").get(key, fallback) or 0)
    except (TypeError, ValueError):
        return fallback


def visible_entries(game) -> list[dict]:
    """A game's offerable tables, the default first and the rest by filename.

    Default first is what makes a member naming only a game deterministic: it takes the
    head of this list, and that is the game's own choice rather than directory order.
    """
    entries = table_entries(getattr(game, "meta_config", {}))
    visible = [e for e in entries.values() if e.get("hidden") is not True]
    if not visible:
        return _unparsed_entry(game)

    meta = getattr(game, "meta_config", {})
    chosen = recorded_default(vpinfe_section(meta), entries) or resolve_default_name(
        table_filenames(entries), getattr(game, "gameDirName", "") or "")
    default_id = entry_for_filename(entries, chosen)[0]

    rest = sorted((e for e in visible if e.get(TABLE_ID_KEY) != default_id),
                  key=lambda e: entry_filename(e).lower())
    head = [e for e in visible if e.get(TABLE_ID_KEY) == default_id]
    return head + rest


def _unparsed_entry(game) -> list[dict]:
    """The .vpx the scan found, for a game nothing has parsed yet.

    Its .info has no tables section - a folder that has never been through a metadata
    build, which is the normal state of a freshly added game. It is still launchable
    and the frontend has always offered it, so it gets an entry with no id rather than
    disappearing until somebody runs a scan. The id arrives with the parse.
    """
    path = str(getattr(game, "fullPathVPXfile", "") or "").strip()
    if not path:
        return []
    return [{TABLE_ID_KEY: "", TABLE_FILENAME_KEY: os.path.basename(path)}]


def _named_table(game, table_id: str) -> dict | None:
    """The table a member named, unless it is hidden. `hidden` is library-wide and beats
    a member: it exists so a patch base can stay on disk without being playable."""
    entry = table_entries(getattr(game, "meta_config", {})).get(table_id)
    if not isinstance(entry, dict) or entry.get("hidden") is True:
        return None
    return entry


def _excluded(refs) -> tuple[set[str], set[str]]:
    """(whole games, individual tables) named by a collection's exclusions."""
    games = {r[MEMBER_GAME_KEY] for r in refs if MEMBER_TABLE_KEY not in r}
    tables = {r[MEMBER_TABLE_KEY] for r in refs if MEMBER_TABLE_KEY in r}
    return games, tables


def _sort_key(order_by: str):
    if order_by == "title":
        return lambda e: (game_title(e.game).lower(), e.table_id)
    if order_by == "year":
        return lambda e: (str(game_year(e.game)), game_title(e.game).lower(), e.table_id)
    if order_by == "rating":
        return lambda e: (-game_rating(e.game), game_title(e.game).lower(), e.table_id)
    if order_by == "added":
        return lambda e: (-(getattr(e.game, "creation_time", 0) or 0),
                          game_title(e.game).lower(), e.table_id)
    if order_by == "play_time":
        # The seconds, not User.RunTime: ordering on the minutes ties every game with
        # under a minute on it at zero, which is most of a library that gets browsed.
        return lambda e: (-run_time_seconds(getattr(e.game, "meta_config", {}) or {}),
                          game_title(e.game).lower(), e.table_id)
    if order_by in ("last_played", "play_count"):
        stored = {"last_played": "LastRun", "play_count": "StartCount"}[order_by]
        return lambda e: (-_user_value(e.game, stored), game_title(e.game).lower(),
                          e.table_id)
    return _sort_key(DEFAULT_ORDER)


def resolve_games(name: str, collections, games) -> list[Any]:
    """The games a collection contains, for the management lens.

    Not the play lens: a game whose only .vpx is hidden, or which has none at all,
    still belongs to the collection. It produces no entry - there is nothing to
    launch - but hiding it from the list you would go to in order to fix it is how a
    library grows a game nobody can find.

    Same membership, ordering and limit as `resolve`, so the two lenses cannot disagree
    about what a collection holds or what order it is in. A game the limit cuts is not
    in the collection - the cap is part of the definition, not a display setting.
    """
    unknown = collections.unknown_filter_axes(name)
    if unknown:
        raise UnresolvableCollectionError(name, unknown)

    by_id = {}
    for game in games:
        found = game_id(game)
        if found:
            by_id.setdefault(found, game)

    member_refs = collections.get_member_refs(name)
    named = {ref[MEMBER_GAME_KEY] for ref in member_refs}
    stored_filters = collections.get_filters(name) or {}
    dropped_games, _ = _excluded(collections.get_excluded_refs(name))

    picked, seen = [], set()

    def _add(game):
        # By object, for the reason `resolve._take` gives: an unscanned game has no id.
        if id(game) in seen or game_id(game) in dropped_games:
            return
        seen.add(id(game))
        picked.append(game)

    for ref in member_refs:
        game = by_id.get(ref[MEMBER_GAME_KEY])
        if game is not None:
            _add(game)

    from_filters = []
    if stored_filters:
        for game in games:
            if game_id(game) in named or game_id(game) in dropped_games:
                continue
            if collection_filters.matches(stored_filters, game):
                before = len(picked)
                _add(game)
                from_filters.extend(picked[before:])
                del picked[before:]

    order = collections.get_order(name)
    order_by = order["by"] or DEFAULT_ORDER
    key = _sort_key(order_by)
    as_entries = {id(g): Entry(game=g, table={}, siblings=0) for g in picked + from_filters}

    if order_by == "manual":
        from_filters.sort(key=lambda g: key(as_entries[id(g)]))
        result = picked + from_filters
    else:
        result = picked + from_filters
        result.sort(key=lambda g: key(as_entries[id(g)]))
        if order["direction"] == "desc" and order_by in ("title", "year"):
            result.reverse()
    limit = collections.get_limit(name)
    return result[:limit] if limit else result


def resolve(name: str, collections, games) -> list[Entry]:
    """The ordered entries a collection contains, one per game.

    `games` is the library. A game offering several tables contributes the one step 3
    selected; `Entry.siblings` says how many it has, and `/games/{id}/tables` lists them.
    """
    unknown = collections.unknown_filter_axes(name)
    if unknown:
        raise UnresolvableCollectionError(name, unknown)

    by_id = {}
    for game in games:
        found = game_id(game)
        if found:
            by_id.setdefault(found, game)

    member_refs = collections.get_member_refs(name)
    named = {ref[MEMBER_GAME_KEY] for ref in member_refs}
    stored_filters = collections.get_filters(name) or {}
    dropped_games, dropped_tables = _excluded(collections.get_excluded_refs(name))

    # 1-3. Members first, in their order. A game named here states exactly what this
    # collection holds for it, so the filter is not consulted for that game at all.
    ordered: list[Entry] = []
    seen: set[tuple[int, str]] = set()

    def _take(game, entry):
        table_id = str(entry.get(TABLE_ID_KEY, ""))
        if table_id in dropped_tables or game_id(game) in dropped_games:
            return
        # Keyed on the object, not on the game's id: a game that has never been through
        # a metadata build has no id yet, and keying on "" would collapse every one of
        # them into a single row. Members resolve through `by_id` to the object the
        # library holds, so the same pairing twice is still one row.
        key = (id(game), table_id)
        if key in seen:
            return
        seen.add(key)
        ordered.append(Entry(game=game, table=entry, siblings=len(visible_entries(game))))

    for ref in member_refs:
        game = by_id.get(ref[MEMBER_GAME_KEY])
        if game is None:
            continue    # not in the library right now; the membership stays on disk
        if MEMBER_TABLE_KEY in ref:
            named_table = _named_table(game, ref[MEMBER_TABLE_KEY])
            if named_table is not None:
                _take(game, named_table)
        else:
            # Naming a game means the game, so it contributes its default and nothing
            # else. Naming two of a game's tables is how a collection holds both, and
            # that is why nothing de-duplicates by game after this.
            offered = visible_entries(game)
            if offered:
                _take(game, offered[0])

    from_filters: list[Entry] = []
    if stored_filters and not collection_filters.unknown_axes(stored_filters):
        for game in games:
            if game_id(game) in named:
                continue
            if not collection_filters.matches(stored_filters, game):
                continue
            offered = visible_entries(game)
            if not offered:
                continue
            before = len(ordered)
            _take(game, offered[0])
            from_filters.extend(ordered[before:])
            del ordered[before:]

    # 4. Order. `manual` is the member array, and only when the collection says so:
    # a list curated before curated order existed was shown alphabetically, and
    # honouring its insertion order would reshuffle it under the user.
    order = collections.get_order(name)
    order_by = order["by"] or DEFAULT_ORDER
    descending = order["direction"] == "desc"

    if order_by == "manual":
        # Whatever a filter contributed has no position of its own, so it follows.
        from_filters.sort(key=_sort_key(DEFAULT_ORDER))
        result = ordered + from_filters
    else:
        result = ordered + from_filters
        result.sort(key=_sort_key(order_by))
        if descending and order_by in ("title", "year"):
            result.reverse()

    # 5. Limit. Last, so it caps an ordered list rather than deciding what is in it.
    # The tiebreak in _sort_key is what stops "top 20 rated" returning a different
    # twenty each time two tables are level.
    limit = collections.get_limit(name)
    return result[:limit] if limit else result
