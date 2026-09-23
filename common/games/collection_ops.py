"""Collections: what one is, what is in it, and every way of changing it.

Two kinds behind one shape. A **manual** collection stores an explicit list of game ids.
A **filter** collection stores criteria and resolves to whatever matches when you ask - so
it has no member list to add to. The two are combinable: a collection may hold criteria,
hand-picked members and exclusions together, and the kind is derived from what is stored
rather than chosen up front.

Membership is the game's own id, not its VPS id: a game with no VPSdb match still belongs
to collections. The key on disk is still `vpsids` for files written before that migration.

Criteria arrive already in the shape the store reads. Turning a caller's filters into that
shape is the caller's business, because the filters are its own vocabulary.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from pathlib import Path
from typing import Any
from urllib.parse import quote

from common import service_errors
from common.games import entry_lens, game_identity, game_lens, game_repository, table_lens
from common.games.collection_filters import UNCONSTRAINED, group_key, group_kind
from common.games.collection_resolver import (
    Entry,
    Holding,
    UnresolvableCollectionError,
    holding,
    resolve,
    resolve_games,
)
from common.games.collection_store import (
    DEFAULT_DIRECTION,
    MANUAL_ORDER,
    PAGING_GROUPS,
    SORT_LABELS,
    CollectionStore,
    DuplicateMemberError,
    normalize_paging_group,
)
from common.games.collections_service import (
    collection_icon_path,
    follow_rename_in_settings,
    forget_in_settings,
    get_collections_manager,
    get_collections_metadata,
    save_collection_icon,
)
from common.games.game_repository import collections_by_game_id, game_to_row
from common.i18n import t
from common.values import is_truthy

logger = logging.getLogger("vpinfe.common.games.collection_ops")


def _many_out(value: object) -> list[str]:
    """A stored criterion as the list a reader wants.

    Storage joins several values with a comma and the matcher splits them again, so this
    is the same set said in the shape the schema declares. "All" is one value like any
    other - it is the vocabulary for unconstrained, not an empty list.
    """
    if isinstance(value, list):
        return [str(part).strip() for part in value if str(part).strip()]
    parts = [part.strip() for part in str(value or "").split(",") if part.strip()]
    return parts or [UNCONSTRAINED]


def _links(name: str) -> dict:
    encoded = quote(name, safe="")
    return {"self": f"/api/v1/collections/{encoded}",
            "games": f"/api/v1/collections/{encoded}/games"}


def _resolved_count(name: str) -> int:
    """How many entries this collection hands out. Resolved, because that is what its size
    means - a rule's matches are stored nowhere and a stored member that names a game this
    library lost resolves to nothing."""
    try:
        return len(resolve(name, get_collections_manager(),
                           list(game_repository.catalog().values())))
    except Exception:
        # A collection this build cannot resolve still has to list. Its own reads say why;
        # a number in a table is not the place to raise it.
        logger.warning("could not size collection %r", name, exc_info=True)
        return 0


def _held(name: str) -> Holding | None:
    try:
        return holding(name, get_collections_manager(),
                       list(game_repository.catalog().values()))
    except Exception:
        # A collection this build cannot resolve still has to list; its own reads say why.
        logger.warning("could not resolve collection %r", name, exc_info=True)
        return None


def _resource_for(row: dict) -> dict:
    name = row["name"]
    held = _held(name)
    filters = None
    # From the `order` block, which is where the resolver reads it. The criteria carry a
    # default for keys the collection never set, so reading the sort there reports "Alpha"
    # for a collection that is ordered by anything else.
    order = get_collections_manager().get_order(name)
    if row["is_filter"]:
        raw = get_collections_manager().get_filters(name) or {}
        filters = {
            "letter": _many_out(raw.get("letter", "All")),
            "theme": _many_out(raw.get("theme", "All")),
            "game_type": _many_out(raw.get("table_type", "All")),
            "manufacturer": _many_out(raw.get("manufacturer", "All")),
            "year": _many_out(raw.get("year", "All")),
            "rating": raw.get("rating", "All"),
            "rating_or_higher": str(raw.get("rating_or_higher", "false")).lower()
            in ("1", "true", "yes", "on"),
            "played": None if raw.get("played") is None else is_truthy(raw["played"]),
            "favorite": None if raw.get("favorite") is None
            else is_truthy(raw["favorite"]),
            "tags": _many_out(raw.get("tags", "All")),
            "order_by": order["by"],
            "direction": order["direction"],
        }
    return {
        "name": name,
        # On the wire this is "manual"; on disk it is still "vpsid", from before
        # membership moved onto game ids. The honest name belongs in the contract.
        "type": "filter" if row["is_filter"] else "manual",
        "description": get_collections_manager().get_description(name),
        "image": row.get("image") or None,
        "count": _resolved_count(name),
        "game_count": row.get("game_count"),
        "added": len(held.added) if held else 0,
        "matched": len(held.matched) if held else 0,
        "excluded": held.excluded if held else 0,
        "filters": filters,
        # Read for every collection, not only a filter one: a manual collection is capped
        # and ordered the same way, and reporting it only sometimes is how a caller learns
        # to ask twice.
        "limit": get_collections_manager().get_limit(name),
        "order_by": order["by"],
        "direction": order["direction"],
        "paging_group": order.get("paging_group") or "",
        "links": _links(name),
    }


def _row_or_refuse(name: str) -> dict:
    for row in get_collections_metadata():
        if row["name"] == name:
            return row
    raise service_errors.NotFoundError(
        t("error.collections.no_collection_named", name=(name)))


def _named_or_refuse(manager: CollectionStore, name: str) -> None:
    if name not in manager.get_collections_name():
        raise service_errors.NotFoundError(
            t("error.collections.no_collection_named", name=(name)))


def _game_or_refuse(game_id: str) -> None:
    if game_id not in game_repository.catalog():
        raise service_errors.NotFoundError(
            t("error.collections.no_game_id", game_id=(game_id)))


def _one_table_of(game_id: str, table_id: str) -> None:
    """Refuse a table that is not this game's. A ref naming a table of some other game
    resolves to nothing and reads as a missing table forever after."""
    if not table_id:
        return
    game = game_repository.game_by_id(game_id)
    known = ({str(row.get("id")) for row in table_lens.table_rows(game, game_to_row(game))}
             if game else set())
    if table_id not in known:
        raise service_errors.NotFoundError(
            t("error.collections.no_table", game_id=(game_id), table_id=(table_id)))


def _resolved(name: str) -> list[Entry]:
    """The collection's entries, or a refusal naming what this build could not read.

    Refusing beats resolving what is left: dropping a criterion answers a different
    question and does it silently. Every other collection still answers.
    """
    try:
        return resolve(name, get_collections_manager(),
                       list(game_repository.catalog().values()))
    except UnresolvableCollectionError as exc:
        raise service_errors.BlockedError(
            str(exc), details={"unknown_filters": exc.axes}) from exc


def _resolved_games(name: str, manager: CollectionStore | None = None) -> list[Any]:
    try:
        return resolve_games(name, manager or get_collections_manager(),
                             list(game_repository.catalog().values()))
    except UnresolvableCollectionError as exc:
        raise service_errors.BlockedError(
            str(exc), details={"unknown_filters": exc.axes}) from exc


# -- reads ------------------------------------------------------------------------


def listing() -> dict:
    return {"collections": [_resource_for(row) for row in get_collections_metadata()]}


def resource(name: str) -> dict:
    return _resource_for(_row_or_refuse(name))


def games_in(name: str) -> dict:
    """Resolved membership, so a filter collection answers the same question a manual one
    does. Ordering is the collection's own.

    The management lens: same membership and order as the play lens, but a game with
    nothing launchable still belongs here. Sharing the resolver is what stops this
    answering in one order while the frontend answers in another.
    """
    _row_or_refuse(name)
    by_collection = collections_by_game_id()
    resources = [game_lens.game_resource(game_to_row(game, by_collection),
                                         game_identity.game_id(game))
                 for game in _resolved_games(name)]
    return {"total": len(resources), "offset": 0, "count": len(resources),
            "games": resources}


def collections_of(game_id: str) -> dict:
    """Every collection holding this game, and whether it was added or matched."""
    _game_or_refuse(game_id)
    found = []
    for row in get_collections_metadata():
        held = _held(row["name"])
        if held is None:
            continue
        kept = {game_identity.game_id(game) for game in held.games}
        if game_id not in kept:
            continue
        added = any(game_identity.game_id(game) == game_id for game in held.added)
        found.append({"name": row["name"],
                      "type": "filter" if row["is_filter"] else "manual",
                      "how": "added" if added else "matched",
                      "links": _links(row["name"])})
    return {"game": game_id, "collections": found}


def members_of(name: str) -> dict:
    """What is written down, not what resolved - the difference an editor needs and every
    other lens hides.

    `games` and `entries` both report what came *out* of the resolver, so a member naming
    something this library no longer has simply is not in them. It stays in the file, keeps
    being counted, and nothing can say so. Here it is a row with `origin: "missing"`.

    Nothing is pruned on the strength of this. A library on a share that was not mounted at
    scan time reports every game missing, and a cleanup that ran on that signal would empty
    every collection. Absence is not deletion.
    """
    _row_or_refuse(name)
    manager = get_collections_manager()
    catalog = game_repository.catalog()
    excluded = manager.get_excluded_refs(name)
    out = ({r["game"] for r in excluded if not r.get("table")},
           {r["table"] for r in excluded if r.get("table")})

    members: list[dict] = []
    named_games = set()
    for ref in manager.get_member_refs(name):
        named_games.add(ref["game"])
        members.append(_member_row(ref["game"], "named", ref.get("table", ""),
                                   catalog, out))
    # Whatever the criteria matched and nobody named. Members come first because that is
    # the order the resolver walks and the order the collection is handed out in.
    for game in _resolved_games(name, manager):
        found = game_identity.game_id(game)
        if found and found not in named_games:
            members.append(_member_row(found, "filter", "", catalog, out))
    # Exclusions last, and listed rather than silent: a row somebody took out is the one
    # row they may want back, and nothing else reports it.
    for ref in excluded:
        members.append({**_member_row(ref["game"], "excluded", ref.get("table", ""),
                                      catalog, out),
                        "origin": "excluded", "included": False})
    return {"collection": name, "count": len(members),
            "playable": sum(1 for one in members if one["included"]),
            "members": members}


def _member_row(game_id: str, origin: str, named_table: str,
                catalog: dict, excluded: tuple[set, set]) -> dict:
    """One stored member, and what became of it."""
    excluded_games, excluded_tables = excluded
    game = catalog.get(game_id)
    if game is None:
        return {"game": game_id, "name": "", "origin": "missing",
                "included": False, "ref_table": named_table, "tables": []}
    known = table_lens.table_rows(game, game_to_row(game))
    by_id = {str(row.get("id")): row for row in known}
    chosen = named_table or (str(known[0].get("id")) if known else "")
    tables = []
    if named_table and named_table not in by_id:
        # The game is here; the table it names is not. Reported rather than resolved to
        # the default, which would quietly change what the collection holds.
        tables.append({"id": named_table, "included": False, "origin": "missing"})
    elif chosen:
        table = by_id[chosen]
        kept_out = ("excluded" if chosen in excluded_tables or game_id in excluded_games
                    else "hidden" if table.get("hidden") else "")
        tables.append({"id": chosen,
                       "version": str(table.get("version") or ""),
                       "authors": [str(one) for one in (table.get("authors") or [])],
                       "filename": str(table.get("filename") or ""),
                       "included": not kept_out,
                       "origin": kept_out or ("named" if named_table else "default")})
    return {"game": game_id, "name": str(game_to_row(game).get("name") or ""),
            "origin": origin, "included": any(one["included"] for one in tables),
            # The table *this ref names*, empty when it names none - which is not the same
            # as the table it resolves to, reported under `tables`. A caller that cannot
            # tell the two apart cannot address one row: it was sending the resolved table
            # back, which matched no ref and left a whole-game exclusion impossible to lift.
            "ref_table": named_table,
            "tables": tables}


def entries_of(name: str) -> dict:
    """The play lens: what a frontend would show, in the order it would show it.

    One entry per game. A game offering several tables contributes the one the collection
    selected. The theme payload is this same resolution, serialized differently.
    """
    _row_or_refuse(name)
    entries = _resolved(name)
    # The same group the theme payload stamps. A caller rendering a wheel needs to know
    # which letter or year it is sitting in, and deriving it a second way is how the two
    # lenses would come to disagree.
    order_by = get_collections_manager().get_order(name)["by"]
    key = group_key(order_by)
    return {"collection": name, "count": len(entries),
            "group_by": group_kind(order_by) if key is not None else "",
            "entries": [entry_lens.entry_resource(one, key(one.game) if key else None)
                        for one in entries]}


def image_path(name: str) -> Path:
    """The file behind a collection's icon, or a refusal."""
    here = collection_icon_path(_row_or_refuse(name).get("image"))
    if here is None:
        raise service_errors.NotFoundError(
            t("error.collections.no_image", name=(name)))
    return here


# -- writes -----------------------------------------------------------------------


def _known_games_or_refuse(games: Iterable[str]) -> None:
    known = set(game_repository.catalog())
    unknown = [game_id for game_id in games if game_id not in known]
    if unknown:
        raise service_errors.RefusedError(t("error.collections.unknown_game_ids"),
                                          details={"ids": unknown})


def _write_criteria(manager: CollectionStore, name: str, criteria: dict,
                    order: dict) -> None:
    """Store a criteria block and the order it carries. One writer for create and patch,
    so the two cannot disagree about which keys a block holds."""
    manager.make_filter_collection(name, criteria, order=order)


def create(name: str, games: Iterable[str] = (), description: str = "",
           criteria: dict | None = None,
           order: dict | None = None) -> dict:
    """Criteria and hand-picked games together, if that is what was asked for: the two are
    combinable and the kind is derived from what is stored."""
    name = (name or "").strip()
    if not name:
        raise service_errors.RefusedError(
            t("error.collections.collection_needs_name"))

    with get_collections_manager().mutate() as manager:
        if name in manager.get_collections_name():
            raise service_errors.BlockedError(
                t("error.collections.collection_named_already_exists", name=(name)))
        _known_games_or_refuse(games)
        manager.add_collection(name, list(games))
        if description:
            manager.set_description(name, description)
        if criteria is not None:
            _write_criteria(manager, name, criteria, order or {})
    return resource(name)


def delete(name: str) -> None:
    with get_collections_manager().mutate() as manager:
        _named_or_refuse(manager, name)
        manager.delete_collection(name)
    forget_in_settings(name)


def add_member(name: str, game_id: str, table_id: str = "",
               after_table: str | None = None) -> None:
    """Idempotent: adding a game that is already a member is a success, because the
    caller's intent - that it be in there - is satisfied either way.

    `table_id` holds this collection to exactly that table; absent, the member names the
    game and resolves to whichever table is its default, so it follows a replacement.
    `after_table` puts the new ref beside a sibling instead of at the end.
    """
    _game_or_refuse(game_id)
    _one_table_of(game_id, table_id)
    with get_collections_manager().mutate() as manager:
        _named_or_refuse(manager, name)
        manager.add_member(name, game_id, table_id, after_table)


def set_member_table(name: str, game_id: str, table_id: str, was: str | None) -> None:
    """Change which of a game's tables this collection holds, keeping its position.

    Reached without deleting the member and adding it back, which would send a curated row
    to the end of the list.
    """
    _game_or_refuse(game_id)
    _one_table_of(game_id, table_id)
    with get_collections_manager().mutate() as manager:
        _named_or_refuse(manager, name)
        try:
            manager.set_member_table(name, game_id, table_id, was)
        except DuplicateMemberError as exc:
            # A conflict, not a miss: the collection already holds that pairing and is
            # allowed it once. Refused rather than merged, because merging drops a row and
            # nothing could say which one went.
            raise service_errors.BlockedError(str(exc)) from exc
        except ValueError as exc:
            raise service_errors.NotFoundError(str(exc)) from exc


def remove_member(name: str, game_id: str, table: str | None = None) -> None:
    """A table names exactly one row, `""` the row that names no table, and None every ref
    naming this game. Absent and empty were the same thing until 2026-08-30, so deleting
    the row that follows a game's default took every other row for that game with it."""
    with get_collections_manager().mutate() as manager:
        _named_or_refuse(manager, name)
        here = [ref for ref in manager.get_member_refs(name)
                if ref.get("game") == game_id
                and (table is None or (ref.get("table") or "") == table)]
        if not here:
            raise service_errors.NotFoundError(
                t("error.collections.not", game_id=(game_id), name=(name)))
        manager.remove_member(name, game_id, table)


def exclude(name: str, game_id: str, table_id: str = "") -> None:
    """Take something out of what the criteria matched, and keep taking it out.

    Naming a table freezes a choice; excluding one says "everything except this" and still
    tracks whatever is added later. Neither substitutes for the other.
    """
    _game_or_refuse(game_id)
    _one_table_of(game_id, table_id)
    with get_collections_manager().mutate() as manager:
        _named_or_refuse(manager, name)
        manager.exclude(name, game_id, table_id)


def unexclude(name: str, game_id: str, table: str | None = None) -> None:
    """A table lifts one exclusion, `""` the one that names no table, and None every
    exclusion naming this game."""
    with get_collections_manager().mutate() as manager:
        _named_or_refuse(manager, name)
        here = [ref for ref in manager.get_excluded_refs(name)
                if ref.get("game") == game_id
                and (table is None or (ref.get("table") or "") == table)]
        if not here:
            raise service_errors.NotFoundError(
                t("error.collections.not_excluded", game_id=(game_id), name=(name)))
        manager.unexclude(name, game_id, table)


def set_image(name: str, filename: str, content: bytes) -> dict:
    """Store an icon and hang it on this collection."""
    _row_or_refuse(name)
    if not content:
        raise service_errors.RefusedError(t("error.collections.file_empty"))
    try:
        stored = save_collection_icon(filename or "", content)
    except ValueError as exc:
        raise service_errors.RefusedError(str(exc)) from exc
    with get_collections_manager().mutate() as manager:
        manager.set_image(name, stored)
    return resource(name)


def clear_image(name: str) -> None:
    """The file stays on disk - another collection may be using it, and an icon nobody
    references costs a few kilobytes against deleting one somebody still shows."""
    _row_or_refuse(name)
    with get_collections_manager().mutate() as manager:
        manager.set_image(name, None)


def keep_result(name: str) -> dict:
    """Criteria as a way of building a list rather than a rule to keep.

    What they match right now becomes the membership, naming each table it resolved to, and
    the criteria are removed. The collection stops changing under its owner - which is the
    whole difference between a list and a rule.

    Exclusions go too. They said "everything except this" about a rule; with no rule left
    there is nothing for them to except, and keeping them would silently subtract from a
    list somebody now edits by hand.

    The cap is applied and then lifted: it capped the rule's output, and re-applying it to
    a list that is already that output would cut it a second time. Order is left alone - it
    decides how the membership is handed out, not what is in it.
    """
    _row_or_refuse(name)
    if not get_collections_manager().has_filters(name):
        raise service_errors.BlockedError(
            t("error.collections.no_criteria_keep_result", name=(name)))
    refs = [{"game": game_identity.game_id(entry.game),
             "table": str(entry.table.get("id", ""))} for entry in _resolved(name)]
    with get_collections_manager().mutate() as writer:
        writer.set_members(name, refs)
        writer.clear_filters(name)
        for ref in writer.get_excluded_refs(name):
            writer.unexclude(name, ref["game"], ref.get("table", ""))
        writer.set_limit(name, None)
    return resource(name)


def patch(name: str, *, new_name: str | None = None, games: Iterable[str] | None = None,
          criteria: dict | None = None, criteria_order: dict | None = None,
          limit: int | None = None, clear_limit: bool = False,
          description: str | None = None, image: str | None = None,
          order_by: str | None = None, direction: str | None = None,
          paging_group: str | None = None) -> dict:
    """Name, image, criteria, membership and cap, in one place.

    A patch: only what is given is written. Renaming should not require restating a
    collection's criteria, and a caller that has to send the whole thing back is a caller
    racing whatever else edited it meanwhile.
    """
    final = name
    renamed_from: str | None = None
    with get_collections_manager().mutate() as manager:
        _named_or_refuse(manager, name)

        if games is not None:
            _known_games_or_refuse(games)
            manager.set_members(name, list(games))

        if criteria is not None:
            _write_criteria(manager, name, criteria, criteria_order or {})

        if clear_limit:
            manager.set_limit(name, None)
        elif limit is not None:
            if limit < 1:
                raise service_errors.RefusedError(
                    t("error.collections.cap_fewer_one_game"))
            manager.set_limit(name, limit)

        if description is not None:
            manager.set_description(name, description)

        if image is not None:
            manager.set_image(name, image)

        # After the criteria, so an order given alongside one is the explicit answer rather
        # than being overwritten by the order inside the criteria block.
        if order_by is not None or direction is not None or paging_group is not None:
            _set_order_fields(manager, name, order_by, direction, paging_group)

        # Last, so every other edit above addressed the collection by the name it had.
        if new_name is not None and new_name.strip() != name:
            final = _rename(manager, name, new_name)
            renamed_from = name

    # Outside the mutate block: the collections file is written first, so a settings write
    # that fails cannot leave the setting pointing at a rename that did not happen.
    if renamed_from is not None:
        follow_rename_in_settings(renamed_from, final)
    return resource(final)


def _rename(manager: CollectionStore, name: str, wanted: str) -> str:
    new_name = wanted.strip()
    if not new_name:
        raise service_errors.RefusedError(
            t("error.collections.collection_needs_name"))
    if new_name in manager.get_collections_name():
        raise service_errors.BlockedError(
            t("error.collections.collection_named_already_exists", name=(new_name)))
    manager.rename_collection(name, new_name)
    return new_name


def _set_order_fields(manager: CollectionStore, name: str, order_by: str | None,
                      direction: str | None,
                      paging_group: str | None) -> None:
    order = manager.get_order(name)
    by = order_by or order["by"]
    if by not in SORT_LABELS and by != MANUAL_ORDER:
        raise service_errors.RefusedError(
            t("error.collections.nothing_ordered", by=(by)),
            details={"choices": [*SORT_LABELS, MANUAL_ORDER]})
    # Refused rather than normalized away. `normalize_paging_group` answers None for
    # anything it cannot read, which would turn a typo into "follow the player" and report
    # success - the same silent-accept order_by was fixed for.
    if paging_group and normalize_paging_group(paging_group) is None:
        raise service_errors.RefusedError(
            t("error.collections.nothing_pages", wanted_paging=(paging_group)),
            details={"choices": list(PAGING_GROUPS)})
    # `manual` is the stored member array. A filter collection has none, so the order would
    # name something that does not exist.
    if by == MANUAL_ORDER and manager.is_filter_based(name):
        raise service_errors.BlockedError(
            t("error.collections.filter_collection_no_arrangement", name=(name)))
    manager.set_order(name, by,
                      direction or order.get("direction") or DEFAULT_DIRECTION,
                      # "" is a value here - it says "follow the player" - so it cannot
                      # fall back to what is stored the way the other two do.
                      paging_group if paging_group is not None
                      else order.get("paging_group"))


def set_arrangement(name: str, games: list[str]) -> None:
    """The whole list, in order, atomically.

    Every id must already be a member: reordering is not a way to add one, and a list that
    quietly added would make a dropped id indistinguishable from a new one. The list is one
    entry **per row**, so a game holding two named tables is named twice - compared by
    content and by length, so a caller that omits one is told rather than silently
    removing it.
    """
    with get_collections_manager().mutate() as manager:
        _named_or_refuse(manager, name)
        if manager.is_filter_based(name):
            raise service_errors.BlockedError(
                t("error.collections.filter_collection_order_comes", name=(name)))
        # Per ref, not per game: an order is over the rows, and one game can hold several.
        # `get_members` de-duplicates by design, so comparing against it read 7 where the
        # collection has 8 rows and refused every move.
        members = [ref["game"] for ref in manager.get_member_refs(name)]
        sent = list(games)
        if sorted(sent) != sorted(members):
            _refuse_arrangement(members, sent)
        # The stored refs, moved - not rebuilt from the ids sent. A member names a game and
        # optionally one of its tables, and writing bare ids back is what `set_members`
        # warns about: every table this collection had *named* is discarded, and a game
        # holding two of them collapses to one entry, and the caller is told nothing.
        #
        # A game's own refs keep their relative order, and are dealt out one per occurrence:
        # a game listed twice takes its first stored ref at the first position and its
        # second at the second. That is the only reading a list of names allows, and it is
        # the right one - the request cannot say which table goes where, but it does not
        # have to, because their order among themselves is what it is asking to preserve.
        grouped: dict[str, list[dict]] = {}
        for ref in manager.get_member_refs(name):
            grouped.setdefault(ref["game"], []).append(ref)
        manager.set_members(name, [grouped[game].pop(0) for game in sent])
        # Setting an order is what makes the member array the order. Without this the
        # resolver falls back to `title`, so the list would come back sorted and the call
        # would have written something nothing reads.
        manager.set_order(name, MANUAL_ORDER)


def _refuse_arrangement(members: list[str], sent: list[str]) -> None:
    # Counts, because the sets can match while the lists do not: a game named twice is one
    # entry in both sets and two rows in the collection. Reported without them, such a
    # request failed with both lists empty and the caller was told only that something was
    # wrong.
    raise service_errors.RefusedError(
        t("error.collections.order_must_list_exactly"),
        details={"missing": sorted(set(members) - set(sent)),
                 "not_members": sorted(set(sent) - set(members)),
                 "sent": len(sent), "members": len(members)})
