"""The table catalog.

A table is the pinball-machine concept - folder, identity, metadata, media and
assets. The
launchable artifact is a game file, exposed as a sub-resource, because a table is
not permanently one .vpx.
"""

from __future__ import annotations

import logging
import threading
from pathlib import Path

from fastapi import APIRouter, Body, Query, Request
from starlette.background import BackgroundTask
from starlette.responses import FileResponse

from common.config_access import MediaConfig
from common.host import launch, launch_state, pinmame_catalog
from common.media_paths import MEDIA_SPECS, resolve_media_files
from common.paths import get_ini_config
from common.tables import asset_resolver, table_identity
from common.tables.game_files import default_game_file, game_file_names
from common.tables.table_repository import (
    collections_by_table_id,
    ensure_tables_loaded,
    table_to_row,
)

from . import models, scopes
from .auth import ForbiddenError, requires
from .errors import ConflictError, FeatureUnavailableError, InvalidRequestError, NotFoundError

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
        # Assets, not media: these are what the table needs to play as intended.
        # Media is the artwork VPinFE shows while browsing - see docs/conventions.md.
        # Summary from the scan; the detail endpoint recomputes and attributes files.
        "assets": _asset_summary(row),
        "links": {
            "self": prefix,
            "game_files": f"{prefix}/game-files",
            "media": f"{prefix}/media",
            "archive": f"{prefix}/archive",
            "launch": f"{prefix}/launch",
        },
    }


def _asset_summary(row: dict) -> dict:
    """Presence per kind, as objects so a kind can grow attributes without a
    breaking change. alt_color keeps its formats - the flat boolean lost them."""
    formats = [name for name, flag in (("serum", "serum_exists"), ("vni", "vni_exists"))
               if row.get(flag)]
    return {
        "backglass": {"present": bool(row.get("b2s_exists"))},
        "settings": {"present": bool(row.get("ini_exists"))},
        "pup_pack": {"present": bool(row.get("pup_pack_exists"))},
        "alt_color": {"present": bool(formats), "formats": formats},
        "alt_sound": {"present": bool(row.get("alt_sound_exists"))},
        "music": {"present": bool(row.get("music_exists"))},
    }


def _listing(table_dir: Path) -> tuple[list[str], list[str]]:
    files: list[str] = []
    subdirs: list[str] = []
    if table_dir.is_dir():
        for entry in table_dir.iterdir():
            (files if entry.is_file() else subdirs).append(entry.name)
    return files, subdirs


def _inventory_assets(table_dir: Path) -> dict:
    """The inventory lens: every asset file attributed, plus the folder-wide kinds.

    Computed fresh per request, not from the scan - an audit that reports
    yesterday's folder is worse than none.
    """
    files, subdirs = _listing(table_dir)
    inv = asset_resolver.inventory(table_dir.name, files, game_file_names(files))
    for entry in inv.values():
        entry["present"] = bool(entry["files"])
    subdir_set = {name.lower() for name in subdirs}
    formats = [fmt for fmt, folder in (("serum", "serum"), ("vni", "vni"))
               if folder in subdir_set]
    inv["pup_pack"] = {"present": "pupvideos" in subdir_set}
    inv["alt_color"] = {"present": bool(formats), "formats": formats}
    inv["alt_sound"] = {"present": (table_dir / "pinmame" / "altsound").is_dir()}
    inv["music"] = {"present": "music" in subdir_set}
    return inv


def _game_files(table, row: dict) -> list[dict]:
    """The table's launchable artifacts.

    Enumerates what is actually in the folder rather than trusting the single
    filename recorded in the .info: a table folder can hold several .vpx files.
    Sorted, so the answer does not depend on directory order.

    The recorded filename is the default when it is actually present. When it is
    not, it is still reported - a table pointing at a missing file is something
    the caller should see - but the default falls to a file that exists, since
    the default is what a caller would launch.
    """
    table_dir = Path(row.get("table_path", ""))
    recorded = (row.get("filename") or "").strip()

    files, subdirs = _listing(table_dir)
    on_disk = game_file_names(files)

    names = list(on_disk)
    if recorded and recorded not in names:
        names.append(recorded)
    if not names:
        return []

    # Same resolver the launcher and the metadata build use, so all three agree.
    default = default_game_file(files, table_dir.name, recorded) or recorded

    # Dependency context, once per request: the alias map and the rom listing are
    # shared by every game file in the folder.
    aliases = asset_resolver.read_alias_map(str(table_dir))
    rom_files = asset_resolver.list_rom_files(str(table_dir))
    flex_raw = str(row.get("detectflex") or "").strip().lower()
    flex_detected = True if flex_raw == "true" else False if flex_raw == "false" else None
    pinmame_raw = str(row.get("detectpinmame") or "").strip().lower()
    pinmame_required = (True if pinmame_raw == "true"
                        else False if pinmame_raw == "false" else None)

    entries = []
    for name in names:
        entry = {
            "format": "vpx",
            "app": "vpx",
            "filename": name,
            "default": name == default,
            "available": name in on_disk,
            "assets": asset_resolver.resolve_for_game_file(name, table_dir.name, files),
        }
        if name == recorded:
            # The .info describes one game file today, so the script-declared
            # facts are only known for that one. The others get an honest unknown.
            chain = asset_resolver.resolve_rom_chain(row.get("rom", ""), aliases,
                                                     rom_files, pinmame_required)
            if chain["effective"]:
                # PinMAME's own audit, from the library the configured VPX ships.
                # No answer leaves the name-match conclusion standing.
                from common.config_access import SettingsConfig
                audit = pinmame_catalog.lookup(
                    SettingsConfig.from_config(get_ini_config()).vpx_bin_path,
                    str(table_dir / "pinmame" / "roms"), chain["effective"])
                asset_resolver.apply_audit(chain, audit)
            flex = asset_resolver.flexdmd_state(subdirs, flex_detected)
        else:
            chain = {"declared": None, "alias_of": None, "effective": None,
                     "required": None, "catalog": None, "clone_of": None,
                     "audit": None, "installed": None,
                     "reason": "unknown: the table metadata records one game file today"}
            flex = asset_resolver.flexdmd_state(subdirs, None)
        chain["nvram"] = asset_resolver.nvram_state(str(table_dir), chain["effective"])
        entry["dependencies"] = {"pinmame": chain, "flexdmd": flex}
        entries.append(entry)
    return entries


@router.get("", summary="List tables", dependencies=[requires(scopes.TABLES_READ)])
def list_tables(
    q: str = Query("", description="Match against name, manufacturer or rom"),
    limit: int = Query(0, ge=0, description="0 returns everything"),
    offset: int = Query(0, ge=0),
) -> models.TableList:
    catalog = _catalog()
    collections = collections_by_table_id()

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


@router.get("/{table_id}", summary="One table", dependencies=[requires(scopes.TABLES_READ)])
def get_table(table_id: str) -> models.TableResource:
    table = _table_or_404(table_id)
    row = table_to_row(table, collections_by_table_id())
    resource = _resource(row, table_id)
    resource["assets"] = _inventory_assets(Path(row.get("table_path", "")))
    return resource


@router.get("/{table_id}/game-files", summary="A table's game files",
            dependencies=[requires(scopes.TABLES_READ)])
def get_game_files(table_id: str) -> models.GameFileList:
    table = _table_or_404(table_id)
    return {"game_files": _game_files(table, table_to_row(table))}


def _default_stem(table) -> str | None:
    """The stem of the build that launches - tier 1 of media resolution."""
    vpx = str(getattr(table, "fullPathVPXfile", "") or "")
    return Path(vpx).stem if vpx else None


def _resolved_media(table_dir: Path, game_file_stem: str | None = None) -> dict:
    """Every media kind against the folder as it is right now."""
    files, subdirs = _listing(table_dir)
    medias: list[str] = []
    if "medias" in {name.lower() for name in subdirs}:
        try:
            medias = [entry.name for entry in (table_dir / "medias").iterdir()
                      if entry.is_file()]
        except OSError:
            medias = []
    table_type = MediaConfig.from_config(get_ini_config()).table_type
    return resolve_media_files(table_dir, set(files), set(medias), table_type,
                               game_file_stem)


@router.get("/{table_id}/media", summary="A table's media",
            dependencies=[requires(scopes.TABLES_READ)])
def get_table_media(table_id: str) -> models.MediaList:
    """Media is the artwork shown about a table - every kind, present or not,
    so a client can enumerate what is possible instead of guessing."""
    table = _table_or_404(table_id)
    table_dir = Path(getattr(table, "fullPathTable", "") or "")
    prefix = f"/api/v1/tables/{table_id}/media"
    resolved = _resolved_media(table_dir, _default_stem(table))
    logo = resolved.get("logo")
    return {"media": {
        key: {
            "present": path is not None,
            "file": path.name if path is not None else None,
            # A wheel served by the logo fallback says so, for clients that care.
            "via": ("logo" if key == "wheel" and path is not None
                    and logo is not None and path == logo else None),
            "links": {"self": f"{prefix}/{key}"} if path is not None else {"self": None},
        }
        for key, path in resolved.items()
    }}


@router.get("/{table_id}/media/{kind}", summary="One media file",
            dependencies=[requires(scopes.TABLES_READ)])
def get_table_media_file(table_id: str, kind: str):
    table = _table_or_404(table_id)
    known = {spec.key for spec in MEDIA_SPECS}
    if kind not in known:
        raise InvalidRequestError("Unknown media kind",
                                  details={"unknown": kind, "known": sorted(known)})
    table_dir = Path(getattr(table, "fullPathTable", "") or "")
    path = _resolved_media(table_dir, _default_stem(table)).get(kind)
    if path is None or not path.is_file():
        raise NotFoundError(f"This table has no {kind} media")
    return FileResponse(path)


@router.post("/{table_id}/launch", summary="Launch a table on this play host",
             status_code=202, dependencies=[requires(scopes.LAUNCH_INVOKE)])
def launch_table(table_id: str,
                 payload: models.LaunchRequest | None = Body(default=None),
                 ) -> models.LaunchAccepted:
    """Start a table and return once it is starting, not once it is over.

    The same service the wheel and the Remote Control page use, so a launch from
    here counts as a play and releases the peripherals like any other.
    """
    table = _table_or_404(table_id)
    game_file = (payload.file or None) if payload else None
    ini_config = get_ini_config()

    try:
        resolved = launch.check_launchable(table, ini_config, game_file)
    except launch.LaunchBusyError as exc:
        raise ConflictError(str(exc)) from exc
    except launch.UnknownGameFileError as exc:
        raise InvalidRequestError(str(exc), details={"file": game_file}) from exc
    except launch.LaunchUnavailableError as exc:
        raise FeatureUnavailableError(str(exc)) from exc

    def run():
        try:
            launch.launch_table(table, ini_config, source=launch_state.SOURCE_API,
                                game_file=game_file)
        except Exception:
            logger.exception("Launch of %s failed", table_id)

    threading.Thread(target=run, daemon=True,
                     name=f"api-launch-{table_id[:8]}").start()
    return {"launching": True, "table_id": table_id,
            "file": Path(resolved).name,
            "links": {"state": "/api/v1/play/state", "events": "/api/v1/events"}}


@router.get("/{table_id}/archive", summary="Download the table folder as an archive",
            dependencies=[requires(scopes.TABLES_READ)])
def get_table_archive(request: Request, table_id: str, download_token: str = "",
                      full: bool = False, file: str = ""):
    from managerui.services.archive_service import cleanup_archive, create_vpxz_archive

    table = _table_or_404(table_id)
    if full:
        # The default bundle rides tables:read; the whole folder is its own
        # permission. Local trust grants both today.
        identity = getattr(request.state, "identity", None)
        if identity is None or not identity.can(scopes.TABLES_EXPORT_FULL):
            raise ForbiddenError(f"Requires {scopes.TABLES_EXPORT_FULL}")
    table_dir_name = getattr(table, "tableDirName", "")
    try:
        archive = create_vpxz_archive(table_dir_name, everything=full,
                                      game_file=file or None)
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
