"""The table catalog.

A table is the pinball-machine concept - folder, identity, metadata, media. The
launchable artifact is a game file, exposed as a sub-resource, because a table is
not permanently one .vpx.
"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, Query
from starlette.background import BackgroundTask
from starlette.responses import FileResponse

from common import table_identity
from common.table_repository import collections_map, ensure_tables_loaded, table_to_row

from .errors import InvalidRequestError, NotFoundError

logger = logging.getLogger("vpinfe.httpapi.tables")

router = APIRouter(prefix="/tables", tags=["tables"])


def _catalog() -> dict:
    """Every table keyed by id, minting ids for any that lack one.

    Writes only for tables without an id, so this is a no-op once the library has
    been through it. main.py does the same at startup; this keeps the API correct
    when it is driven without a full app boot.
    """
    return table_identity.ensure_unique_ids(ensure_tables_loaded())


def _table_or_404(table_id: str):
    table = _catalog().get(table_id)
    if table is None:
        raise NotFoundError(f"No table with id {table_id}")
    return table


def _resource(row: dict, table_id: str) -> dict:
    prefix = f"/api/v1/tables/{table_id}"
    return {
        "id": table_id,
        # Correlation with VPSdb, VPinPlay and the like - not this table's identity.
        "vps_id": row.get("vpsid", ""),
        "name": row.get("name", ""),
        "manufacturer": row.get("manufacturer", ""),
        "year": str(row.get("year") or ""),
        "type": row.get("type", ""),
        "themes": row.get("themes") or [],
        "authors": row.get("authors") or [],
        "rom": row.get("rom", ""),
        "version": row.get("version", ""),
        "rating": row.get("rating", 0),
        "collections": row.get("collections") or [],
        "media": {
            "b2s": row.get("b2s_exists", False),
            "pup_pack": row.get("pup_pack_exists", False),
            "alt_colour": row.get("serum_exists", False) or row.get("vni_exists", False),
            "alt_sound": row.get("alt_sound_exists", False),
        },
        "links": {
            "self": prefix,
            "files": f"{prefix}/files",
            "archive": f"{prefix}/archive",
        },
    }


def _game_files(table, row: dict) -> list[dict]:
    """The table's launchable artifacts.

    One .vpx today. The shape is the 1-to-many one so that adding another format
    does not change the contract.
    """
    filename = row.get("filename", "")
    if not filename:
        return []
    path = Path(row.get("table_path", "")) / filename
    return [{
        "format": "vpx",
        "app": "vpx",
        "filename": filename,
        "default": True,
        "available": path.is_file(),
    }]


@router.get("", summary="List tables")
def list_tables(
    q: str = Query("", description="Match against name, manufacturer or rom"),
    limit: int = Query(0, ge=0, description="0 returns everything"),
    offset: int = Query(0, ge=0),
) -> dict:
    catalog = _catalog()
    collections = collections_map()

    items = []
    for table_id, table in catalog.items():
        row = table_to_row(table, collections)
        items.append((row.get("name", "").lower(), _resource(row, table_id)))
    items.sort(key=lambda pair: pair[0])
    resources = [resource for _name, resource in items]

    if q:
        needle = q.strip().lower()
        resources = [
            r for r in resources
            if needle in r["name"].lower()
            or needle in (r["manufacturer"] or "").lower()
            or needle in (r["rom"] or "").lower()
        ]

    total = len(resources)
    if offset:
        resources = resources[offset:]
    if limit:
        resources = resources[:limit]
    return {"total": total, "offset": offset, "count": len(resources), "tables": resources}


@router.get("/{table_id}", summary="One table")
def get_table(table_id: str) -> dict:
    table = _table_or_404(table_id)
    return _resource(table_to_row(table, collections_map()), table_id)


@router.get("/{table_id}/files", summary="A table's game files")
def get_table_files(table_id: str) -> dict:
    table = _table_or_404(table_id)
    return {"files": _game_files(table, table_to_row(table))}


@router.get("/{table_id}/archive", summary="Download the table folder as an archive")
def get_table_archive(table_id: str, download_token: str = ""):
    from managerui.services.archive_service import cleanup_archive, create_vpxz_archive

    table = _table_or_404(table_id)
    table_dir_name = getattr(table, "tableDirName", "")
    try:
        archive = create_vpxz_archive(table_dir_name)
    except ValueError as exc:
        raise InvalidRequestError("Invalid table path") from exc
    except FileNotFoundError as exc:
        raise NotFoundError("Table not found") from exc

    logger.info("Created download archive: %s", archive.path)

    def cleanup():
        cleanup_archive(archive)
        logger.info("Cleaned up temp archive: %s", archive.temp_dir)

    headers = {}
    if download_token and download_token.isalnum():
        # Progress signal for the page that started the download. Not authentication.
        headers["Set-Cookie"] = (
            f"vpinfe_vpxz_download_{download_token}=1; Max-Age=60; Path=/; SameSite=Lax")

    return FileResponse(
        archive.path,
        media_type="application/octet-stream",
        filename=archive.filename,
        headers=headers,
        background=BackgroundTask(cleanup),
    )
