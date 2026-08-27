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

from fastapi import APIRouter, Body, Response

from common.games import game_identity
from common.games.collection_filters import group_key, group_kind
from common.games.collection_resolver import (
    UnresolvableCollectionError,
    resolve,
    resolve_games,
    visible_entries,
)
from common.games.collection_store import MANUAL_ORDER
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
from .games import _catalog, _resource

router = APIRouter(prefix="/collections", tags=["collections"])


def _links(name: str) -> dict:
    from urllib.parse import quote

    encoded = quote(name, safe="")
    return {"self": f"/api/v1/collections/{encoded}",
            "games": f"/api/v1/collections/{encoded}/games"}


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
            "letter": raw.get("letter", "All"),
            "theme": raw.get("theme", "All"),
            "game_type": raw.get("table_type", "All"),
            "manufacturer": raw.get("manufacturer", "All"),
            "year": raw.get("year", "All"),
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
        "image": row.get("image") or None,
        "game_count": row.get("game_count"),
        "filters": filters,
        # Read for every collection, not only a filter one: a manual collection is
        # capped and ordered the same way, and reporting it only sometimes is how a
        # client learns to ask twice.
        "limit": get_collections_manager().get_limit(name),
        "order_by": order["by"],
        "direction": order["direction"],
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


@router.post("", summary="Create a collection", status_code=201,
             dependencies=[requires(scopes.COLLECTIONS_WRITE)])
def create_collection(response: Response,
                      request: models.CreateCollectionRequest = Body(...),
                      ) -> models.CollectionResource:
    name = request.name.strip()
    if not name:
        raise InvalidRequestError("A collection needs a name")
    if request.filters is not None and request.games:
        raise InvalidRequestError(
            "A collection is either filter-based or an explicit list of games, not both")

    with get_collections_manager().mutate() as manager:
        if name in manager.get_collections_name():
            raise ConflictError(f"A collection named {name} already exists")

        if request.filters is not None:
            f = request.filters
            manager.add_filter_collection(
                name, f.letter, f.theme, f.game_type, f.manufacturer, f.year,
                f.rating, "true" if f.rating_or_higher else "false",
                f.order_by, f.direction, played=f.played)
        else:
            known = set(_catalog())
            unknown = [game_id for game_id in request.games if game_id not in known]
            if unknown:
                raise InvalidRequestError("Unknown game ids", details={"ids": unknown})
            manager.add_collection(name, request.games)

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


@router.put("/{name}/games/{game_id}", summary="Add a game to a collection",
            status_code=204, dependencies=[requires(scopes.COLLECTIONS_WRITE)])
def add_member(name: str, game_id: str) -> Response:
    """Idempotent: adding a game that is already a member is a success, because the
    caller's intent - that it be in there - is satisfied either way."""
    if game_id not in _catalog():
        raise NotFoundError(f"No game with id {game_id}")
    with get_collections_manager().mutate() as manager:
        if name not in manager.get_collections_name():
            raise NotFoundError(f"No collection named {name}")
        if manager.is_filter_based(name):
            raise ConflictError(
                f"{name} is a filter collection - its membership comes from its criteria")
        manager.add_member(name, game_id)
    return Response(status_code=204)


@router.delete("/{name}/games/{game_id}", summary="Remove a game from a collection",
               status_code=204, dependencies=[requires(scopes.COLLECTIONS_WRITE)])
def remove_member(name: str, game_id: str) -> Response:
    with get_collections_manager().mutate() as manager:
        if name not in manager.get_collections_name():
            raise NotFoundError(f"No collection named {name}")
        if manager.is_filter_based(name):
            raise ConflictError(
                f"{name} is a filter collection - its membership comes from its criteria")
        if game_id not in manager.get_members(name):
            raise NotFoundError(f"{game_id} is not in {name}")
        manager.remove_member(name, game_id)
    return Response(status_code=204)


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
    if request.games is not None and request.filters is not None:
        raise InvalidRequestError(
            "A collection is either filter-based or an explicit list of games, not both")

    final = name
    with get_collections_manager().mutate() as manager:
        if name not in manager.get_collections_name():
            raise NotFoundError(f"No collection named {name}")

        if request.games is not None:
            if manager.is_filter_based(name):
                raise ConflictError(
                    f"{name} is a filter collection - its membership comes from its "
                    "criteria")
            known = set(_catalog())
            unknown = [game_id for game_id in request.games if game_id not in known]
            if unknown:
                raise InvalidRequestError("Unknown game ids", details={"ids": unknown})
            manager.set_members(name, request.games)

        if request.filters is not None:
            f = request.filters
            manager.make_filter_collection(
                name,
                {"letter": f.letter, "theme": f.theme, "game_type": f.game_type,
                 "manufacturer": f.manufacturer, "year": f.year, "rating": f.rating,
                 "rating_or_higher": "true" if f.rating_or_higher else "false",
                 "played": f.played},
                order={"by": f.order_by, "direction": f.direction})

        if request.clear_limit:
            manager.set_limit(name, None)
        elif request.limit is not None:
            if request.limit < 1:
                raise InvalidRequestError("A cap of fewer than one game shows nothing")
            manager.set_limit(name, request.limit)

        if request.image is not None:
            manager.set_image(name, request.image)

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
    membership is compared as a set, so a caller that omits one is told rather than
    silently removing it.
    """
    with get_collections_manager().mutate() as manager:
        if name not in manager.get_collections_name():
            raise NotFoundError(f"No collection named {name}")
        if manager.is_filter_based(name):
            raise ConflictError(
                f"{name} is a filter collection - its order comes from its criteria")
        members = list(manager.get_members(name))
        sent = list(request.games)
        if sorted(sent) != sorted(members):
            missing = sorted(set(members) - set(sent))
            extra = sorted(set(sent) - set(members))
            raise InvalidRequestError(
                "An order must list exactly the collection's members",
                details={"missing": missing, "not_members": extra})
        manager.set_members(name, sent)
        # Setting an order is what makes the member array the order. Without this the
        # resolver falls back to `title`, so the list would come back sorted and the
        # call would have written something nothing reads.
        manager.set_order(name, MANUAL_ORDER)
    return Response(status_code=204)
