"""Collections: the groupings a user makes over their library.

Two kinds behind one resource. A **manual** collection stores an explicit list of
table ids. A **filter** collection stores criteria and resolves to whatever matches
when you ask - so it has no member list to add to, and `PUT .../tables/{id}` on one
is refused rather than silently doing nothing.

Membership is the table's own id (`VPinFE.id`), not its VPS id: a table with no
VPSdb match still belongs to collections, which is why membership moved off the VPS
id in the first place. The key on disk is still `vpsids` for files written before
that migration - see common/tables/vpxcollections.py.
"""

from __future__ import annotations

import threading

from fastapi import APIRouter, Body, Response

from common.tables import table_identity
from common.tables.collections_service import (
    filter_games_by_collection,
    get_collections_manager,
    get_collections_metadata,
)

from . import models, scopes
from .auth import requires
from .errors import ConflictError, InvalidRequestError, NotFoundError
from .tables import _catalog, _resource

router = APIRouter(prefix="/collections", tags=["collections"])

# The whole file is rewritten on every save, so two overlapping requests could lose
# one another's edit. Serialising here covers the API; a Manager UI write still goes
# its own way, which is tolerable only because collection edits are rare and small.
_write_lock = threading.RLock()


def _links(name: str) -> dict:
    from urllib.parse import quote

    encoded = quote(name, safe="")
    return {"self": f"/api/v1/collections/{encoded}",
            "tables": f"/api/v1/collections/{encoded}/tables"}


def _resource_for(row: dict) -> dict:
    name = row["name"]
    filters = None
    if row["is_filter"]:
        raw = get_collections_manager().get_filters(name)
        filters = {
            "letter": raw.get("letter", "All"),
            "theme": raw.get("theme", "All"),
            "table_type": raw.get("table_type", "All"),
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
        # membership moved onto table ids. The honest name belongs in the contract.
        "type": "filter" if row["is_filter"] else "manual",
        "image": row.get("image") or None,
        "table_count": row.get("table_count"),
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


@router.get("/{name}/tables", summary="The tables in a collection",
            dependencies=[requires(scopes.COLLECTIONS_READ)])
def collection_games(name: str) -> models.GameList:
    """Resolved membership, so a filter collection answers the same question a
    manual one does. Ordering is the collection's own."""
    _row_or_404(name)
    from common.tables.table_repository import collections_by_game_id, game_to_row

    catalog = _catalog()
    members, _filters = filter_games_by_collection(list(catalog.values()), name)
    by_collection = collections_by_game_id()
    resources = [_resource(game_to_row(game, by_collection), table_identity.table_id(game))
                 for game in members]
    return {"total": len(resources), "offset": 0, "count": len(resources),
            "tables": resources}


@router.post("", summary="Create a collection", status_code=201,
             dependencies=[requires(scopes.COLLECTIONS_WRITE)])
def create_collection(response: Response,
                      request: models.CreateCollectionRequest = Body(...),
                      ) -> models.CollectionResource:
    name = request.name.strip()
    if not name:
        raise InvalidRequestError("A collection needs a name")
    if request.filters is not None and request.tables:
        raise InvalidRequestError(
            "A collection is either filter-based or an explicit list of tables, not both")

    with _write_lock:
        manager = get_collections_manager()
        manager.reload()
        if name in manager.get_collections_name():
            raise ConflictError(f"A collection named {name} already exists")

        if request.filters is not None:
            f = request.filters
            manager.add_filter_collection(
                name, f.letter, f.theme, f.table_type, f.manufacturer, f.year,
                f.rating, "true" if f.rating_or_higher else "false",
                f.sort_by, f.order_by)
        else:
            known = set(_catalog())
            unknown = [table_id for table_id in request.tables if table_id not in known]
            if unknown:
                raise InvalidRequestError("Unknown table ids", details={"ids": unknown})
            manager.add_collection(name, request.tables)
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


@router.put("/{name}/tables/{table_id}", summary="Add a table to a collection",
            status_code=204, dependencies=[requires(scopes.COLLECTIONS_WRITE)])
def add_member(name: str, table_id: str) -> Response:
    """Idempotent: adding a table that is already a member is a success, because the
    caller's intent - that it be in there - is satisfied either way."""
    if table_id not in _catalog():
        raise NotFoundError(f"No table with id {table_id}")
    with _write_lock:
        manager = get_collections_manager()
        manager.reload()
        if name not in manager.get_collections_name():
            raise NotFoundError(f"No collection named {name}")
        if manager.is_filter_based(name):
            raise ConflictError(
                f"{name} is a filter collection - its membership comes from its criteria")
        manager.add_member(name, table_id)
        manager.save()
    return Response(status_code=204)


@router.delete("/{name}/tables/{table_id}", summary="Remove a table from a collection",
               status_code=204, dependencies=[requires(scopes.COLLECTIONS_WRITE)])
def remove_member(name: str, table_id: str) -> Response:
    with _write_lock:
        manager = get_collections_manager()
        manager.reload()
        if name not in manager.get_collections_name():
            raise NotFoundError(f"No collection named {name}")
        if manager.is_filter_based(name):
            raise ConflictError(
                f"{name} is a filter collection - its membership comes from its criteria")
        if table_id not in manager.get_members(name):
            raise NotFoundError(f"{table_id} is not in {name}")
        manager.remove_member(name, table_id)
        manager.save()
    return Response(status_code=204)
