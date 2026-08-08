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

import threading

from fastapi import APIRouter, Body, Response

from common.games import game_identity
from common.games.collection_resolver import (
    UnresolvableCollectionError,
    resolve,
    resolve_games,
    visible_entries,
)
from common.games.collections_service import (
    get_collections_manager,
    get_collections_metadata,
)
from common.games.game_metadata import game_rating, game_title

from . import models, scopes
from .auth import requires
from .errors import ConflictError, InvalidRequestError, NotFoundError
from .games import _catalog, _resource

router = APIRouter(prefix="/collections", tags=["collections"])

# The whole file is rewritten on every save, so two overlapping requests could lose
# one another's edit. Serialising here covers the API; a Manager UI write still goes
# its own way, which is tolerable only because collection edits are rare and small.
_write_lock = threading.RLock()


def _links(name: str) -> dict:
    from urllib.parse import quote

    encoded = quote(name, safe="")
    return {"self": f"/api/v1/collections/{encoded}",
            "games": f"/api/v1/collections/{encoded}/games"}


def _resource_for(row: dict) -> dict:
    name = row["name"]
    filters = None
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
            "sort_by": raw.get("sort_by", "Alpha"),
            "order_by": raw.get("order_by", "Descending"),
        }
    return {
        "name": name,
        # On the wire this is "manual"; on disk it is still "vpsid", from before
        # membership moved onto game ids. The honest name belongs in the contract.
        "type": "filter" if row["is_filter"] else "manual",
        "image": row.get("image") or None,
        "game_count": row.get("game_count"),
        "filters": filters,
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


def _entry_resource(entry) -> dict:
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
    return {
        "game": {
            "id": game_ident,
            "vps_id": str(info.get("VPSId", "") or ""),
            "name": game_title(entry.game),
            "manufacturer": str(info.get("Manufacturer", "") or ""),
            "year": str(info.get("Year", "") or ""),
            "type": str(info.get("Type", "") or ""),
            "rating": game_rating(entry.game),
        },
        "table": {
            "id": entry.table_id,
            "filename": entry.filename,
            "version": str(entry.table.get("version", "") or ""),
            "rom": str(entry.table.get("rom", "") or ""),
            "default": entry.table_id == default_id,
        },
        "siblings": entry.siblings,
        "links": {"game": prefix, "launch": f"{prefix}/launch",
                  "media": f"{prefix}/media"},
    }


def _resolved(name: str, expanded: bool):
    """The collection's entries, or a 409 naming what this build could not read.

    Refusing beats resolving what is left: dropping a criterion answers a different
    question and does it silently. Every other collection still answers.
    """
    try:
        return resolve(name, get_collections_manager(),
                       list(_catalog().values()), expanded=expanded)
    except UnresolvableCollectionError as exc:
        raise ConflictError(
            str(exc), details={"unknown_filters": exc.axes}) from exc


@router.get("/{name}/entries", summary="The entries a collection resolves to",
            dependencies=[requires(scopes.COLLECTIONS_READ)])
def collection_entries(name: str, expanded: bool = False) -> models.EntryList:
    """The play lens: what a frontend would show, in the order it would show it.

    One entry per game by default; `expanded=true` gives one per included table. The
    theme payload is this same resolution, serialized differently.
    """
    _row_or_404(name)
    entries = _resolved(name, expanded)
    return {"collection": name, "expanded": expanded, "count": len(entries),
            "entries": [_entry_resource(e) for e in entries]}


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

    with _write_lock:
        manager = get_collections_manager()
        manager.reload()
        if name in manager.get_collections_name():
            raise ConflictError(f"A collection named {name} already exists")

        if request.filters is not None:
            f = request.filters
            manager.add_filter_collection(
                name, f.letter, f.theme, f.game_type, f.manufacturer, f.year,
                f.rating, "true" if f.rating_or_higher else "false",
                f.sort_by, f.order_by)
        else:
            known = set(_catalog())
            unknown = [game_id for game_id in request.games if game_id not in known]
            if unknown:
                raise InvalidRequestError("Unknown game ids", details={"ids": unknown})
            manager.add_collection(name, request.games)
        manager.save()

    response.headers["Location"] = _links(name)["self"]
    return _resource_for(_row_or_404(name))


@router.delete("/{name}", summary="Delete a collection", status_code=204,
               dependencies=[requires(scopes.COLLECTIONS_WRITE)])
def delete_collection(name: str) -> Response:
    with _write_lock:
        manager = get_collections_manager()
        manager.reload()
        if name not in manager.get_collections_name():
            raise NotFoundError(f"No collection named {name}")
        manager.delete_collection(name)
        manager.save()
    return Response(status_code=204)


@router.put("/{name}/games/{game_id}", summary="Add a game to a collection",
            status_code=204, dependencies=[requires(scopes.COLLECTIONS_WRITE)])
def add_member(name: str, game_id: str) -> Response:
    """Idempotent: adding a game that is already a member is a success, because the
    caller's intent - that it be in there - is satisfied either way."""
    if game_id not in _catalog():
        raise NotFoundError(f"No game with id {game_id}")
    with _write_lock:
        manager = get_collections_manager()
        manager.reload()
        if name not in manager.get_collections_name():
            raise NotFoundError(f"No collection named {name}")
        if manager.is_filter_based(name):
            raise ConflictError(
                f"{name} is a filter collection - its membership comes from its criteria")
        manager.add_member(name, game_id)
        manager.save()
    return Response(status_code=204)


@router.delete("/{name}/games/{game_id}", summary="Remove a game from a collection",
               status_code=204, dependencies=[requires(scopes.COLLECTIONS_WRITE)])
def remove_member(name: str, game_id: str) -> Response:
    with _write_lock:
        manager = get_collections_manager()
        manager.reload()
        if name not in manager.get_collections_name():
            raise NotFoundError(f"No collection named {name}")
        if manager.is_filter_based(name):
            raise ConflictError(
                f"{name} is a filter collection - its membership comes from its criteria")
        if game_id not in manager.get_members(name):
            raise NotFoundError(f"{game_id} is not in {name}")
        manager.remove_member(name, game_id)
        manager.save()
    return Response(status_code=204)
