"""Collections: the groupings a user makes over their library.

Two kinds behind one resource. A **manual** collection stores an explicit list of
game ids. A **filter** collection stores criteria and resolves to whatever matches
when you ask - so it has no member list to add to, and `PUT .../games/{id}` on one
is refused rather than silently doing nothing.

Membership is the table's own id (`VPinFE.id`), not its VPS id: a table with no
VPSdb match still belongs to collections, which is why membership moved off the VPS
id in the first place. The key on disk is still `vpsids` for files written before
that migration - see common/tables/collection_store.py.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Body, File, Request, Response, UploadFile
from starlette.concurrency import run_in_threadpool

from common.games import game_identity
from common.games.collection_filters import UNCONSTRAINED, group_key, group_kind
from common.games.collection_resolver import (
    UnresolvableCollectionError,
    resolve,
    resolve_games,
    visible_entries,
)
from common.games.collection_store import (
    DEFAULT_DIRECTION,
    MANUAL_ORDER,
    PAGING_GROUPS,
    SORT_LABELS,
    DuplicateMemberError,
    normalize_paging_group,
)
from common.games.collections_service import (
    get_collections_manager,
    get_collections_metadata,
)
from common.games.game_metadata import (
    game_rating,
    game_themes,
    game_title,
    play_record,
    table_descriptor,
)
from common.games.media_lookup import resolved_kinds
from common.shared_assets import manufacturer_logo_web_path
from common.timestamps import epoch_to_iso
from common.values import is_truthy

from . import models, scopes
from .auth import requires
from .errors import ConflictError, InvalidRequestError, NotFoundError
from .games import _catalog, _resource, revalidating_file

logger = logging.getLogger("vpinfe.httpapi.collections")

router = APIRouter(prefix="/collections", tags=["collections"])


def _many_out(value) -> list[str]:
    """A stored criterion as the list a client reads.

    Storage joins several values with a comma and the matcher splits them again, so
    this is the same set said in the shape the schema declares. "All" is one value like
    any other - it is the vocabulary for unconstrained, not an empty list.
    """
    if isinstance(value, list):
        return [str(part).strip() for part in value if str(part).strip()]
    parts = [part.strip() for part in str(value or "").split(",") if part.strip()]
    return parts or [UNCONSTRAINED]


def _many_in(value) -> str:
    """A criterion as it is stored. A list joins; a string is already stored form."""
    if isinstance(value, list):
        joined = ",".join(str(part).strip() for part in value if str(part).strip())
        return joined or UNCONSTRAINED
    return str(value or UNCONSTRAINED)


def _links(name: str) -> dict:
    from urllib.parse import quote

    encoded = quote(name, safe="")
    return {"self": f"/api/v1/collections/{encoded}",
            "games": f"/api/v1/collections/{encoded}/games"}


def _resolved_count(name: str) -> int:
    """How many entries this collection hands out. Resolved, because that is what its
    size means - a rule's matches are stored nowhere and a stored member that names a
    game this library lost resolves to nothing."""
    try:
        return len(resolve(name, get_collections_manager(), list(_catalog().values())))
    except Exception:
        # A collection this build cannot resolve still has to list. Its own routes say
        # why; a number in a table is not the place to raise it.
        logger.warning("could not size collection %r", name, exc_info=True)
        return 0


def _resource_for(row: dict) -> dict:
    name = row["name"]
    filters = None
    # From the `order` block, which is where the resolver reads it. The criteria carry a
    # default for keys the collection never set, so reading the sort there reports
    # "Alpha" for a collection that is ordered by anything else.
    order = get_collections_manager().get_order(name)
    if row["is_filter"]:
        raw = get_collections_manager().get_filters(name)
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
        "filters": filters,
        # Read for every collection, not only a filter one: a manual collection is
        # capped and ordered the same way, and reporting it only sometimes is how a
        # client learns to ask twice.
        "limit": get_collections_manager().get_limit(name),
        "order_by": order["by"],
        "direction": order["direction"],
        "paging_group": order.get("paging_group") or "",
        "links": _links(name),
    }


def _row_or_404(name: str) -> dict:
    for row in get_collections_metadata():
        if row["name"] == name:
            return row
    raise NotFoundError(f"No collection named {name}")


@router.get("", summary="List collections",
            dependencies=[requires(scopes.COLLECTIONS_READ)])
def list_collections() -> models.CollectionList:
    return {"collections": [_resource_for(row) for row in get_collections_metadata()]}


@router.get("/{name}", summary="One collection",
            dependencies=[requires(scopes.COLLECTIONS_READ)])
def get_collection(name: str) -> models.CollectionResource:
    return _resource_for(_row_or_404(name))


@router.get("/{name}/games", summary="The games in a collection",
            dependencies=[requires(scopes.COLLECTIONS_READ)])
def collection_games(name: str) -> models.GameList:
    """Resolved membership, so a filter collection answers the same question a
    manual one does. Ordering is the collection's own."""
    _row_or_404(name)
    from common.games.game_repository import collections_by_game_id, game_to_row

    by_collection = collections_by_game_id()
    # The management lens: same membership and order as the play lens, but a game with
    # nothing launchable still belongs here. Sharing the resolver is what stops this
    # answering in one order while the frontend answers in another.
    try:
        members = resolve_games(name, get_collections_manager(), list(_catalog().values()))
    except UnresolvableCollectionError as exc:
        raise ConflictError(str(exc), details={"unknown_filters": exc.axes}) from exc
    resources = [_resource(game_to_row(game, by_collection), game_identity.game_id(game))
                 for game in members]
    return {"total": len(resources), "offset": 0, "count": len(resources),
            "games": resources}


@router.get("/{name}/members", summary="A collection's stored membership, and why",
            dependencies=[requires(scopes.COLLECTIONS_READ)])
def collection_members(name: str) -> models.CollectionMemberList:
    """What is written down, not what resolved - which is the difference an editor
    needs and every other lens hides.

    `/games` and `/entries` both report what came *out* of the resolver, so a member
    naming something this library no longer has simply is not in them. It stays in the
    file, keeps being counted, and nothing can say so. Here it is a row with
    `origin: "missing"`.

    Nothing is pruned on the strength of this. A library on a share that was not
    mounted at scan time reports every game missing, and a cleanup that ran on that
    signal would empty every collection. Absence is not deletion.
    """
    _row_or_404(name)
    manager = get_collections_manager()
    catalog = _catalog()
    excluded = manager.get_excluded_refs(name)
    excluded_games = {r["game"] for r in excluded if not r.get("table")}
    excluded_tables = {r["table"] for r in excluded if r.get("table")}

    out = (excluded_games, excluded_tables)
    members: list[dict] = []
    named_games = set()
    for ref in manager.get_member_refs(name):
        named_games.add(ref["game"])
        members.append(_member_row(ref["game"], "named", ref.get("table", ""),
                                   catalog, out))
    # Whatever the criteria matched and nobody named. Members come first because that
    # is the order the resolver walks and the order the collection is handed out in.
    try:
        matched = resolve_games(name, manager, list(catalog.values()))
    except UnresolvableCollectionError as exc:
        raise ConflictError(str(exc), details={"unknown_filters": exc.axes}) from exc
    for game in matched:
        found = game_identity.game_id(game)
        if found and found not in named_games:
            members.append(_member_row(found, "filter", "", catalog, out))
    # Exclusions last, and listed rather than silent: a row somebody took out is the
    # one row they may want back, and nothing else reports it.
    for ref in excluded:
        members.append({**_member_row(ref["game"], "excluded",
                                      ref.get("table", ""), catalog, out),
                        "origin": "excluded", "included": False})
    return {"collection": name, "count": len(members),
            "playable": sum(1 for m in members if m["included"]),
            "members": members}


def _member_row(game_id: str, origin: str, named_table: str,
                catalog: dict, excluded: tuple[set, set]) -> dict:
    """One stored member, and what became of it.

    At module level rather than nested in the route, because the contract test reads
    every `return` inside an annotated endpoint as that endpoint's payload - and a
    helper's rows are not the route's.
    """
    from common.games.game_repository import game_to_row

    from .games import _tables
    excluded_games, excluded_tables = excluded
    game = catalog.get(game_id)
    if game is None:
        return {"game": game_id, "name": "", "origin": "missing",
                "included": False, "ref_table": named_table, "tables": []}
    known = _tables(game, game_to_row(game))
    by_id = {str(t.get("id")): t for t in known}
    chosen = named_table or (str(known[0].get("id")) if known else "")
    tables = []
    if named_table and named_table not in by_id:
        # The game is here; the table it names is not. Reported rather than resolved
        # to the default, which would quietly change what the collection holds.
        tables.append({"id": named_table, "included": False, "origin": "missing"})
    elif chosen:
        table = by_id[chosen]
        kept_out = ("excluded" if chosen in excluded_tables or game_id in excluded_games
                    else "hidden" if table.get("hidden") else "")
        tables.append({"id": chosen,
                       "version": str(table.get("version") or ""),
                       "authors": [str(a) for a in (table.get("authors") or [])],
                       "filename": str(table.get("filename") or ""),
                       "included": not kept_out,
                       "origin": kept_out or ("named" if named_table else "default")})
    return {"game": game_id, "name": str(game_to_row(game).get("name") or ""),
            "origin": origin, "included": any(t["included"] for t in tables),
            # The table *this ref names*, empty when it names none - which is not the
            # same as the table it resolves to, reported under `tables`. A client that
            # cannot tell the two apart cannot address one row: it was sending the
            # resolved table back, which matched no ref and left a whole-game exclusion
            # impossible to lift.
            "ref_table": named_table,
            "tables": tables}


def _entry_resource(entry, group=None) -> dict:
    """One entry as REST serves it.

    `default` is computed, never read off the entry: it is the game's own choice and
    lives in the vpinfe section, not on the table. visible_entries puts it first.
    """
    game_ident = game_identity.game_id(entry.game)
    offered = visible_entries(entry.game)
    default_id = offered[0].get("id", "") if offered else ""
    meta = entry.game.meta_config or {}
    info = meta.get("Info") or {}
    prefix = f"/api/v1/games/{game_ident}"
    maker = str(info.get("Manufacturer", "") or "")
    return {
        "game": {
            "id": game_ident,
            "vps_id": str(info.get("VPSId", "") or ""),
            "name": game_title(entry.game),
            "manufacturer": maker,
            "year": str(info.get("Year", "") or ""),
            "type": str(info.get("Type", "") or ""),
            "themes": game_themes(entry.game),
            "dir_name": str(getattr(entry.game, "gameDirName", "") or ""),
            "manufacturer_logo": manufacturer_logo_web_path(maker),
            "created_at": epoch_to_iso(getattr(entry.game, "creation_time", None)) or None,
            "rating": game_rating(entry.game),
            "user": play_record(meta),
        },
        "table": table_descriptor(entry.table, default_id=default_id),
        "siblings": entry.siblings,
        "assets": {
            "pup_pack": bool(getattr(entry.game, "pupPackExists", False)),
            "alt_color": bool(getattr(entry.game, "altColorExists", False)),
            "alt_sound": bool(getattr(entry.game, "altSoundExists", False)),
        },
        "media": resolved_kinds(entry.game),
        # None when the order has no groups; `group_by` on the list says which.
        "group": group,
        "links": {"game": prefix, "launch": f"{prefix}/launch",
                  "media": f"{prefix}/media"},
    }


def _resolved(name: str):
    """The collection's entries, or a 409 naming what this build could not read.

    Refusing beats resolving what is left: dropping a criterion answers a different
    question and does it silently. Every other collection still answers.
    """
    try:
        return resolve(name, get_collections_manager(), list(_catalog().values()))
    except UnresolvableCollectionError as exc:
        raise ConflictError(
            str(exc), details={"unknown_filters": exc.axes}) from exc


@router.get("/{name}/entries", summary="The entries a collection resolves to",
            dependencies=[requires(scopes.COLLECTIONS_READ)])
def collection_entries(name: str) -> models.EntryList:
    """The play lens: what a frontend would show, in the order it would show it.

    One entry per game. A game offering several tables contributes the one the
    collection selected; `siblings` says how many it has and `GET /games/{id}/tables`
    lists them. The theme payload is this same resolution, serialized differently.
    """
    _row_or_404(name)
    entries = _resolved(name)
    # The same group the theme payload stamps. A client rendering a wheel needs to know
    # which letter or year it is sitting in, and deriving it a second way is how the two
    # lenses would come to disagree.
    order_by = get_collections_manager().get_order(name)["by"]
    key = group_key(order_by)
    return {"collection": name, "count": len(entries),
            "group_by": group_kind(order_by) if key is not None else "",
            "entries": [_entry_resource(e, key(e.game) if key else None)
                        for e in entries]}


def _criteria_for(f) -> dict:
    """A criteria block in the shape the store and the matcher read.

    One translation, shared by what writes a collection and what previews one, so a
    rule cannot resolve differently before and after it is saved. `game_type` is stored
    as `table_type`, the spelling on disk from before the vocabulary alignment.
    """
    if f is None:
        return {}
    return {"letter": _many_in(f.letter), "theme": _many_in(f.theme),
            "table_type": _many_in(f.game_type),
            "manufacturer": _many_in(f.manufacturer), "year": _many_in(f.year),
            "rating": f.rating,
            "rating_or_higher": "true" if f.rating_or_higher else "false",
            "played": f.played}


def _write_filters(manager, name: str, f) -> None:
    """Store a criteria block, and the order it carries.

    One writer for create and patch, so the two cannot disagree about which keys a
    block holds. `game_type` is stored as `table_type`, the spelling on disk from
    before the vocabulary alignment.
    """
    manager.make_filter_collection(name, _criteria_for(f),
                                   order={"by": f.order_by, "direction": f.direction})


@router.post("", summary="Create a collection", status_code=201,
             dependencies=[requires(scopes.COLLECTIONS_WRITE)])
def create_collection(response: Response,
                      request: models.CreateCollectionRequest = Body(...),
                      ) -> models.CollectionResource:
    name = request.name.strip()
    if not name:
        raise InvalidRequestError("A collection needs a name")

    with get_collections_manager().mutate() as manager:
        if name in manager.get_collections_name():
            raise ConflictError(f"A collection named {name} already exists")

        # Criteria and hand-picked games together, if that is what was asked for.
        # COLLECTIONS 2.11 makes them combinable and derives the kind from what is
        # stored; refusing the pair was this API carrying 2.x's two kinds forward.
        known = set(_catalog())
        unknown = [game_id for game_id in request.games if game_id not in known]
        if unknown:
            raise InvalidRequestError("Unknown game ids", details={"ids": unknown})
        manager.add_collection(name, request.games)
        if request.description:
            manager.set_description(name, request.description)
        if request.filters is not None:
            _write_filters(manager, name, request.filters)

    response.headers["Location"] = _links(name)["self"]
    return _resource_for(_row_or_404(name))


@router.delete("/{name}", summary="Delete a collection", status_code=204,
               dependencies=[requires(scopes.COLLECTIONS_WRITE)])
def delete_collection(name: str) -> Response:
    with get_collections_manager().mutate() as manager:
        if name not in manager.get_collections_name():
            raise NotFoundError(f"No collection named {name}")
        manager.delete_collection(name)
    return Response(status_code=204)


def _one_table_of(game_id: str, table_id: str) -> None:
    """Refuse a table that is not this game's. A ref naming a table of some other game
    resolves to nothing and reads as a missing table forever after."""
    if not table_id:
        return
    from common.games.game_repository import game_to_row

    from .games import _tables
    game = _catalog().get(game_id)
    known = {str(t.get("id")) for t in _tables(game, game_to_row(game))} if game else set()
    if table_id not in known:
        raise NotFoundError(f"{game_id} has no table {table_id}")


@router.put("/{name}/games/{game_id}", summary="Add a game to a collection",
            status_code=204, dependencies=[requires(scopes.COLLECTIONS_WRITE)])
def add_member(name: str, game_id: str,
               request: models.MemberRequest | None = Body(default=None)) -> Response:
    """Idempotent: adding a game that is already a member is a success, because the
    caller's intent - that it be in there - is satisfied either way.

    `table` names one of the game's tables and holds this collection to exactly that
    one. Absent, the member names the game and resolves to whichever table is its
    default, so the collection follows a replacement.

    `after_table` puts the new ref beside a sibling instead of at the end, which is
    what makes a second table of one game visibly arrive.

    Works on any collection. Criteria and named members are combinable (COLLECTIONS
    2.11) and a member overrides what the criteria say for that game.
    """
    if game_id not in _catalog():
        raise NotFoundError(f"No game with id {game_id}")
    table_id = (request.table if request else "") or ""
    _one_table_of(game_id, table_id)
    after = request.after_table if request else None
    with get_collections_manager().mutate() as manager:
        if name not in manager.get_collections_name():
            raise NotFoundError(f"No collection named {name}")
        manager.add_member(name, game_id, table_id, after)
    return Response(status_code=204)


@router.put("/{name}/games/{game_id}/table",
            summary="Set which table a member names", status_code=204,
            dependencies=[requires(scopes.COLLECTIONS_WRITE)])
def set_member_table(name: str, game_id: str,
                     request: models.MemberTableRequest = Body(...)) -> Response:
    """Change which of a game's tables this collection holds, keeping its position.

    The two tools of COLLECTIONS 2.12 are naming a table and excluding one; this is how
    a caller reaches the first without deleting the member and adding it back, which
    would send a curated row to the end of the list.
    """
    if game_id not in _catalog():
        raise NotFoundError(f"No game with id {game_id}")
    _one_table_of(game_id, request.table)
    with get_collections_manager().mutate() as manager:
        if name not in manager.get_collections_name():
            raise NotFoundError(f"No collection named {name}")
        try:
            manager.set_member_table(name, game_id, request.table, request.was)
        except DuplicateMemberError as exc:
            # A conflict, not a miss: the collection already holds that pairing and
            # 2.10 allows it once. Refused rather than merged, because merging drops a
            # row and nothing on the wire could say which one went.
            raise ConflictError(str(exc)) from exc
        except ValueError as exc:
            raise NotFoundError(str(exc)) from exc
    return Response(status_code=204)


@router.delete("/{name}/games/{game_id}", summary="Remove a game from a collection",
               status_code=204, dependencies=[requires(scopes.COLLECTIONS_WRITE)])
def remove_member(name: str, game_id: str, table: str | None = None) -> Response:
    """`?table=` removes exactly one row, `?table=` with no value the one that names no
    table, and omitting it entirely removes every ref naming this game.

    Absent and empty were the same thing until 2026-08-30, so deleting the row that
    follows a game's default took every other row for that game with it."""
    with get_collections_manager().mutate() as manager:
        if name not in manager.get_collections_name():
            raise NotFoundError(f"No collection named {name}")
        refs = manager.get_member_refs(name)
        here = [r for r in refs if r.get("game") == game_id
                and (table is None or (r.get("table") or "") == table)]
        if not here:
            raise NotFoundError(f"{game_id} is not in {name}")
        manager.remove_member(name, game_id, table)
    return Response(status_code=204)


@router.put("/{name}/excluded/{game_id}", summary="Exclude a game from a collection",
            status_code=204, dependencies=[requires(scopes.COLLECTIONS_WRITE)])
def add_exclusion(name: str, game_id: str,
                  request: models.MemberRequest | None = Body(default=None)) -> Response:
    """Take something out of what the criteria matched, and keep taking it out.

    The other half of COLLECTIONS 2.12: naming a table freezes a choice, excluding one
    says "everything except this" and still tracks whatever is added later. Neither
    substitutes for the other, and until now only naming had a route.
    """
    if game_id not in _catalog():
        raise NotFoundError(f"No game with id {game_id}")
    table_id = (request.table if request else "") or ""
    _one_table_of(game_id, table_id)
    with get_collections_manager().mutate() as manager:
        if name not in manager.get_collections_name():
            raise NotFoundError(f"No collection named {name}")
        manager.exclude(name, game_id, table_id)
    return Response(status_code=204)


@router.delete("/{name}/excluded/{game_id}", summary="Stop excluding a game",
               status_code=204, dependencies=[requires(scopes.COLLECTIONS_WRITE)])
def remove_exclusion(name: str, game_id: str, table: str | None = None) -> Response:
    """`?table=abc` lifts one exclusion, `?table=` with no value the one that names no
    table, and omitting it lifts every exclusion naming this game.

    Absent and empty were the same until 2026-08-30, which left an exclusion of a whole
    game impossible to lift on its own."""
    with get_collections_manager().mutate() as manager:
        if name not in manager.get_collections_name():
            raise NotFoundError(f"No collection named {name}")
        excluded = manager.get_excluded_refs(name)
        here = [r for r in excluded if r.get("game") == game_id
                and (table is None or (r.get("table") or "") == table)]
        if not here:
            raise NotFoundError(f"{game_id} is not excluded from {name}")
        manager.unexclude(name, game_id, table)
    return Response(status_code=204)


@router.put("/{name}/image", summary="Set a collection's image",
            dependencies=[requires(scopes.COLLECTIONS_WRITE)])
async def set_image(name: str, file: UploadFile = File(...)
                    ) -> models.CollectionResource:
    """Upload an icon and hang it on this collection.

    Stored under /api/v1 rather than only in the Manager UI's own static tree, which is
    where collection icons used to live: the filename was on the resource and no client
    outside that one process could either write one or fetch it back.
    """
    from common.games.collections_service import save_collection_icon
    _row_or_404(name)
    content = await file.read()
    if not content:
        raise InvalidRequestError("That file is empty")
    try:
        stored = await run_in_threadpool(save_collection_icon, file.filename or "", content)
    except ValueError as exc:
        raise InvalidRequestError(str(exc)) from exc
    with get_collections_manager().mutate() as manager:
        manager.set_image(name, stored)
    return _resource_for(_row_or_404(name))


@router.delete("/{name}/image", summary="Clear a collection's image",
               status_code=204, dependencies=[requires(scopes.COLLECTIONS_WRITE)])
def clear_image(name: str) -> Response:
    """The file stays on disk - another collection may be using it, and an icon nobody
    references costs a few kilobytes against deleting one somebody still shows."""
    _row_or_404(name)
    with get_collections_manager().mutate() as manager:
        manager.set_image(name, None)
    return Response(status_code=204)


@router.get("/{name}/image", summary="A collection's image",
            dependencies=[requires(scopes.COLLECTIONS_READ)])
def get_image(name: str, request: Request):
    from common.games.collections_service import collection_icon_path
    row = _row_or_404(name)
    here = collection_icon_path(row.get("image"))
    if here is None:
        raise NotFoundError(f"{name} has no image")
    # Named for the collection, not the file: a new image changes what this serves.
    return revalidating_file(here, request)


@router.post("/{name}/members/from_filters",
             summary="Keep what the criteria match, and drop the criteria",
             dependencies=[requires(scopes.COLLECTIONS_WRITE)])
def members_from_filters(name: str) -> models.CollectionResource:
    """Criteria as a way of building a list rather than a rule to keep.

    What it matches right now becomes the membership, naming each table it resolved to,
    and the criteria are removed. The collection stops changing under its owner - which
    is the whole difference between a list and a rule, and the reason `manual` order is
    only offered once nothing is dynamic.

    Exclusions go too. They said "everything except this" about a rule; with no rule
    left there is nothing for them to except, and keeping them would silently subtract
    from a list somebody now edits by hand.

    The cap is applied and then lifted: it capped the rule's output, and re-applying it
    to a list that is already that output would cut it a second time. Order is left
    alone - it decides how the membership is handed out, not what is in it.
    """
    _row_or_404(name)
    manager = get_collections_manager()
    if not manager.has_filters(name):
        raise ConflictError(f"{name} has no criteria to keep the result of")
    entries = _resolved(name)
    refs = [{"game": game_identity.game_id(entry.game),
             "table": str(entry.table.get("id", ""))} for entry in entries]
    with get_collections_manager().mutate() as writer:
        writer.set_members(name, refs)
        writer.clear_filters(name)
        for ref in writer.get_excluded_refs(name):
            writer.unexclude(name, ref["game"], ref.get("table", ""))
        writer.set_limit(name, None)
    return _resource_for(_row_or_404(name))


@router.patch("/{name}", summary="Change a collection",
              dependencies=[requires(scopes.COLLECTIONS_WRITE)])
def patch_collection(name: str,
                     request: models.PatchCollectionRequest = Body(...),
                     ) -> models.CollectionResource:
    """Name, image, criteria, membership and cap, in one place.

    A patch: only what is sent is written. Renaming should not require restating a
    collection's criteria, and a client that has to send the whole thing back is a
    client racing whatever else edited it meanwhile.
    """

    final = name
    with get_collections_manager().mutate() as manager:
        if name not in manager.get_collections_name():
            raise NotFoundError(f"No collection named {name}")

        if request.games is not None:
            known = set(_catalog())
            unknown = [game_id for game_id in request.games if game_id not in known]
            if unknown:
                raise InvalidRequestError("Unknown game ids", details={"ids": unknown})
            manager.set_members(name, request.games)

        if request.filters is not None:
            _write_filters(manager, name, request.filters)

        if request.clear_limit:
            manager.set_limit(name, None)
        elif request.limit is not None:
            if request.limit < 1:
                raise InvalidRequestError("A cap of fewer than one game shows nothing")
            manager.set_limit(name, request.limit)

        if request.description is not None:
            manager.set_description(name, request.description)

        if request.image is not None:
            manager.set_image(name, request.image)

        # After `filters`, so an order sent alongside one is the explicit answer rather
        # than being overwritten by the order inside the filter block.
        if (request.order_by is not None or request.direction is not None
                or request.paging_group is not None):
            order = manager.get_order(name)
            by = request.order_by or order["by"]
            if by not in SORT_LABELS and by != MANUAL_ORDER:
                raise InvalidRequestError(
                    f"Nothing is ordered by {by}",
                    details={"choices": [*SORT_LABELS, MANUAL_ORDER]})
            # `manual` is the stored member array. A filter collection has none, so
            # the order would name something that does not exist.
            wanted_paging = request.paging_group
            # Refused rather than normalised away. `normalize_paging_group` answers
            # None for anything it cannot read, which would turn a typo into "follow
            # the player" and report success - the same silent-accept this route was
            # fixed for on order_by.
            if wanted_paging and normalize_paging_group(wanted_paging) is None:
                raise InvalidRequestError(
                    f"Nothing pages by {wanted_paging}",
                    details={"choices": list(PAGING_GROUPS)})
            if by == MANUAL_ORDER and manager.is_filter_based(name):
                raise ConflictError(
                    f"{name} is a filter collection - it has no arrangement to follow")
            manager.set_order(name, by,
                              request.direction or order.get("direction")
                              or DEFAULT_DIRECTION,
                              # "" is a value here - it says "follow the player" - so
                              # it cannot fall back to what is stored the way the
                              # other two do.
                              request.paging_group if request.paging_group is not None
                              else order.get("paging_group"))

        # Last, so every other edit above addressed the collection by the name it had.
        if request.name is not None and request.name.strip() != name:
            new_name = request.name.strip()
            if not new_name:
                raise InvalidRequestError("A collection needs a name")
            if new_name in manager.get_collections_name():
                raise ConflictError(f"A collection named {new_name} already exists")
            manager.rename_collection(name, new_name)
            final = new_name

    return _resource_for(_row_or_404(final))


@router.put("/{name}/order", summary="Set the order of a collection's games",
            status_code=204, dependencies=[requires(scopes.COLLECTIONS_WRITE)])
def set_order(name: str,
              request: models.CollectionOrderRequest = Body(...)) -> Response:
    """The whole list, in order, atomically.

    Every id must already be a member: reordering is not a way to add one, and a list
    that quietly added would make a dropped id indistinguishable from a new one. The
    list is one entry **per row**, so a game holding two named tables is named twice -
    compared by content and by length, so a caller that omits one is told rather than
    silently removing it.
    """
    with get_collections_manager().mutate() as manager:
        if name not in manager.get_collections_name():
            raise NotFoundError(f"No collection named {name}")
        if manager.is_filter_based(name):
            raise ConflictError(
                f"{name} is a filter collection - its order comes from its criteria")
        # Per ref, not per game: an order is over the rows, and section 2.10 lets one
        # game hold several. `get_members` de-duplicates by design, so comparing
        # against it read 7 where the collection has 8 rows and refused every move.
        members = [ref["game"] for ref in manager.get_member_refs(name)]
        sent = list(request.games)
        if sorted(sent) != sorted(members):
            missing = sorted(set(members) - set(sent))
            extra = sorted(set(sent) - set(members))
            # Counts, because the sets can match while the lists do not: a game named
            # twice is one entry in both sets and two rows in the collection. Reported
            # without them, such a request failed with both lists empty and the caller
            # was told only that something was wrong.
            raise InvalidRequestError(
                "An order must list exactly the collection's members",
                details={"missing": missing, "not_members": extra,
                         "sent": len(sent), "members": len(members)})
        # The stored refs, moved - not rebuilt from the ids sent. A member names a game
        # and optionally one of its tables (COLLECTIONS section 2.10), and writing bare
        # ids back is what `set_members` warns about: every table this collection had
        # *named* is discarded, and a game holding two of them collapses to one entry.
        # Measured before this: a three-ref tournament list came back as two bare games,
        # on a 204.
        #
        # A game's own refs keep their relative order, and are dealt out one per
        # occurrence: a game listed twice takes its first stored ref at the first
        # position and its second at the second. That is the only reading a list of
        # names allows, and it is the right one - the request cannot say which table
        # goes where, but it does not have to, because their order among themselves is
        # what it is asking to preserve.
        grouped: dict[str, list[dict]] = {}
        for ref in manager.get_member_refs(name):
            grouped.setdefault(ref["game"], []).append(ref)
        manager.set_members(name, [grouped[game].pop(0) for game in sent])
        # Setting an order is what makes the member array the order. Without this the
        # resolver falls back to `title`, so the list would come back sorted and the
        # call would have written something nothing reads.
        manager.set_order(name, MANUAL_ORDER)
    return Response(status_code=204)
