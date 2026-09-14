"""The game catalog.

A game is the pinball-machine concept - folder, identity, metadata, media and
assets. The launchable artifact is a table, exposed as a sub-resource, because a
game is not permanently one .vpx.
"""

from __future__ import annotations

import logging
import os
import threading
from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, Body, File, Query, Request, UploadFile
from starlette.background import BackgroundTask
from starlette.concurrency import run_in_threadpool
from starlette.responses import FileResponse

from common import apps
from common.games import (
    asset_origin,
    game_identity,
    game_lens,
    game_repository,
    game_service,
    library_vps_state,
    locations,
    media_lookup,
    media_placement,
    media_service,
    table_lens,
    tables,
)
from common.games.game_metadata import (
    adopt_vps_details,
    load_game_meta,
    meta_file_path,
    reset_game_play_record,
    reset_table_play_record,
    set_asset_source,
    set_game_favorite,
    set_game_play_record,
    set_game_rating,
    set_game_tags,
    set_table_rating,
    set_table_source,
    vpinfe_section,
    vps_details_differ,
)
from common.games.game_repository import collections_by_game_id, game_to_row
from common.games.ids import new_id
from common.games.info_file import MetaConfig
from common.games.tables import (
    ABSENT_SINCE_KEY,
    entry_filename,
    entry_for_filename,
    table_entries,
)
from common.host import launch, launch_state
from common.i18n import t
from common.media_specs import MEDIA_SPECS
from common.paths import get_ini_config

from . import filesystem, models, responses, scopes
from .auth import ForbiddenError, requires
from .errors import ConflictError, FeatureUnavailableError, InvalidRequestError, NotFoundError

logger = logging.getLogger("vpinfe.httpapi.games")


router = APIRouter(prefix="/games", tags=["games"])

def _game_or_404(game_id: str):
    game = game_repository.catalog().get(game_id)
    if game is None:
        raise NotFoundError(t("error.games.no_game_id", game_id=(game_id)))
    return game


def folder_of(game_id: str) -> Path:
    """The folder one game lives in, for a caller that has an id and needs the files.

    Here rather than in the caller because the id-to-game lookup is this module's, and a
    second one would be a second answer to which game an id names.
    """
    return Path(str(_game_or_404(game_id).fullPathGame))


@router.get("", summary="List games", dependencies=[requires(scopes.GAMES_READ)])
def list_games(
    q: str = Query("", description="Match against name, manufacturer or rom"),
    limit: int = Query(0, ge=0, description="0 returns everything"),
    offset: int = Query(0, ge=0),
) -> models.GameList:
    catalog = game_repository.catalog()
    collections = collections_by_game_id()

    items = []
    for game_id, game in catalog.items():
        row = game_to_row(game, collections)
        items.append((row.get("name", "").lower(), game_lens.game_resource(row, game_id)))
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
    return models.GameList.model_validate(
        {"total": total, "offset": offset, "count": len(resources), "games": resources})


@router.post("", summary="Create a game", status_code=201,
             dependencies=[requires(scopes.GAMES_WRITE)])
def create_game(body: models.NewGameRequest) -> models.GameResource:
    """Make a folder with a record in it, in the location new games go to.

    The only way to bring an entry into being without a file arriving: an upload creates
    one on the way past, and every other write needs a game that already exists.
    """
    try:
        folder = game_service.create_game(body.name, body.location)
    except FileExistsError as exc:
        raise ConflictError(t("error.games.already_folder_name"),
                            details={"path": str(exc)}) from exc
    except ValueError as exc:
        raise InvalidRequestError(str(exc), details=_where_else(body.location)) from exc
    except OSError as exc:
        raise ConflictError(t("error.games.could_not_create", exc=(exc))) from exc

    # Canonically, never by spelling. Re-reading one folder resolves the path it is
    # given, so the game just created carries the real path while every game a scan
    # found carries the location's own spelling - and under /var on macOS those differ.
    wanted = locations.canonical(str(folder))
    made = next((game for game in game_repository.catalog().values()
                 if locations.canonical(str(getattr(game, "fullPathGame", ""))) == wanted),
                None)
    if made is None:
        # The folder and its record are on disk and the library did not pick them up.
        # Saying so beats a 500: what was asked for happened, and what is wrong is that
        # the location it landed in is not one this install reads.
        raise ConflictError(
            t("error.games.created_install_not_read"),
            details={"path": str(folder)})
    return get_game(game_identity.game_id(made))


def _where_else(wanted: str) -> dict:
    """The locations that would have worked, for a refusal to offer."""
    where = locations.destination(wanted)
    return {"alternatives": [{"location_id": one.location_id, "name": one.name,
                              "path": one.path} for one in where.alternatives]}


@router.get("/{game_id}", summary="One game", dependencies=[requires(scopes.GAMES_READ)])
def get_game(game_id: str) -> models.GameResource:
    game = _game_or_404(game_id)
    row = game_to_row(game, collections_by_game_id())
    resource = game_lens.game_resource(row, game_id)
    resource["assets"] = game_lens.inventory_assets(Path(row.get("game_dir", "")))
    return models.GameResource(**resource)


@router.get("/{game_id}/tables", summary="A game's tables",
            dependencies=[requires(scopes.GAMES_READ)])
def get_games(game_id: str) -> models.TableList:
    game = _game_or_404(game_id)
    return models.TableList.model_validate(
        {"tables": table_lens.table_rows(game, game_to_row(game))})


def _table_stem_or_404(game, table_id: str) -> str:
    """The stem to resolve against, or 404 if that table is not this game's."""
    filename = media_lookup.table_filename(game, table_id)
    if not filename:
        raise NotFoundError(t("error.games.game_no_such_table"),
                            details={"game": getattr(game, "gameDirName", ""),
                                     "table": table_id})
    return Path(filename).stem


@router.get("/{game_id}/media", summary="A game's shared media",
            dependencies=[requires(scopes.GAMES_READ)])
def get_game_media(game_id: str) -> models.MediaList:
    """Media is the artwork shown about a game - every kind, present or not,
    so a client can enumerate what is possible instead of guessing.

    Resolved with no table stem, so this is what every table in the folder shares.
    Art named for one build belongs to that build and answers under its table.
    """
    game = _game_or_404(game_id)
    game_dir = Path(getattr(game, "fullPathGame", "") or "")
    prefix = f"/api/v1/games/{game_id}/media"
    return models.MediaList.model_validate(
        {"media": media_service.media_map(game_dir, prefix)})


def _media_file_or_404(game, kind: str, table_stem: str | None,
                       request: Request | None = None):
    known = {spec.kind for spec in MEDIA_SPECS}
    if kind not in known:
        raise InvalidRequestError(t("error.games.unknown_media_kind"),
                                  details={"unknown": kind, "known": sorted(known)})
    game_dir = Path(getattr(game, "fullPathGame", "") or "")
    hit = media_service.resolved_media(game_dir, table_stem).get(kind)
    path = hit.path if hit is not None else None
    if path is None or not path.is_file():
        raise NotFoundError(t("error.games.game_no_media", kind=(kind)))
    return responses.revalidating_file(path, request)


@router.get("/{game_id}/media/overrides",
            summary="Kinds where a table has art of its own",
            dependencies=[requires(scopes.GAMES_READ)])
def get_media_overrides(game_id: str) -> models.MediaOverrideList:
    """Where the game's art is not the whole story.

    Asked from the game's own lens, which otherwise cannot see a table-specific file at
    all: resolving without a table stem never looks at that tier. A curator scanning a
    folder wants the odd one out, and the odd one out is invisible without this.

    One walk for every kind and every table, because the caller is drawing a map of all
    of them and twenty round trips to answer one question would be worse.
    """
    from common.media_specs import MEDIA_SPECS, media_candidates

    game = _game_or_404(game_id)
    game_dir = Path(getattr(game, "fullPathGame", "") or "")
    files, medias = media_service.media_contents(game_dir)
    variant, active_sets = media_service.media_settings()

    # What the game itself resolves, to compare against. A .vpx named after its folder
    # makes its own tier and the game's the same filename, and then the same file - so
    # without this it is reported as overriding itself, which is most single-table
    # folders and the commonest shape there is.
    shared = {spec.kind: next((item.path for item in media_candidates(
        game_dir, files, medias, spec.kind, variant, None, active_sets)), None)
        for spec in MEDIA_SPECS}

    found: dict[str, list[dict]] = {}
    for table in table_lens.table_rows(game, game_to_row(game)):
        stem = Path(str(table.get("filename") or "")).stem
        if not table.get("id") or not stem:
            continue
        for spec in MEDIA_SPECS:
            own = next((item for item in media_candidates(
                game_dir, files, medias, spec.kind, variant, stem, active_sets)
                if item.tier == "table"), None)
            if own is not None and own.path != shared.get(spec.kind):
                found.setdefault(spec.kind, []).append({
                    "table": table["id"],
                    "filename": table.get("filename") or "",
                    "version": table.get("version") or "",
                    "file": own.path.name,
                })
    return models.MediaOverrideList.model_validate({"overrides": found})


@router.get("/{game_id}/media/{kind}", summary="One shared media file",
            dependencies=[requires(scopes.GAMES_READ)])
def get_game_media_file(game_id: str, kind: str, request: Request):
    return _media_file_or_404(_game_or_404(game_id), kind, None, request)


@router.get("/{game_id}/tables/{table_id}/media", summary="One table's media",
            dependencies=[requires(scopes.GAMES_READ)])
def get_table_media(game_id: str, table_id: str) -> models.MediaList:
    """The same kinds, resolved for one build rather than for the folder.

    Two builds of a game can genuinely differ - a VR room and a desktop table are
    not the same picture - so each answers for itself. `via: "table"` marks a file
    named for this .vpx; anything else it shares with its siblings.
    """
    game = _game_or_404(game_id)
    game_dir = Path(getattr(game, "fullPathGame", "") or "")
    prefix = f"/api/v1/games/{game_id}/tables/{table_id}/media"
    stem = _table_stem_or_404(game, table_id)
    return models.MediaList.model_validate(
        {"media": media_service.media_map(game_dir, prefix, stem)})


@router.get("/{game_id}/tables/{table_id}/media/{kind}", summary="One table's media file",
            dependencies=[requires(scopes.GAMES_READ)])
def get_table_media_file(game_id: str, table_id: str, kind: str,
                         request: Request):
    game = _game_or_404(game_id)
    return _media_file_or_404(game, kind, _table_stem_or_404(game, table_id),
                              request)


async def _write_media(game, kind: str, stem: str, upload: UploadFile,
                       prefix: str, table_stem: str | None):
    """Store the bytes at `stem`'s tier, then answer with what now resolves.

    The reply is the slot as it stands rather than a bare 201: a shared file is
    outranked by any table-specific one, so "written" and "in use" are different
    facts and the caller should not have to guess which it got.
    """
    import tempfile

    known = {spec.kind for spec in MEDIA_SPECS}
    if kind not in known:
        raise InvalidRequestError(t("error.games.unknown_media_kind"),
                                  details={"unknown": kind, "known": sorted(known)})
    game_dir = Path(getattr(game, "fullPathGame", "") or "")
    suffix = Path(upload.filename or "").suffix
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as staged:
        staged.write(await upload.read())
        staged_path = staged.name
    try:
        written = await run_in_threadpool(
            media_placement.place, game_dir, kind, stem, staged_path)
    except media_placement.UnplaceableError as exc:
        raise InvalidRequestError(str(exc)) from exc
    finally:
        Path(staged_path).unlink(missing_ok=True)

    await run_in_threadpool(media_placement.record_origin, game_dir, written)
    entries = media_service.media_map(game_dir, prefix, table_stem)
    return {"written": written.name, "media": {kind: entries[kind]}}


def _file_facts(path: Path, kind: str) -> dict:
    """Size, date and pixel size - what tells two candidates for a slot apart.

    Every part is best-effort: a file that cannot be opened still has a name worth
    showing, and a slot that reports nothing at all is worse than one missing a number.
    """
    from common.media_specs import media_family

    facts: dict = {"size_bytes": None, "modified": None, "width": None, "height": None}
    try:
        stat = path.stat()
    except OSError:
        return facts
    facts["size_bytes"] = stat.st_size
    facts["modified"] = datetime.fromtimestamp(stat.st_mtime,
                                               tz=UTC).isoformat()
    if media_family(kind) == "image":
        try:
            from PIL import Image
            with Image.open(path) as img:
                facts["width"], facts["height"] = img.size
        except Exception:
            logger.debug("Could not read image size for %s", path, exc_info=True)
    return facts


def _media_detail(game, kind: str, table_stem: str | None, prefix: str) -> dict:
    """One slot: the winner, what it is, and every tier that holds a file for it."""
    from common.media_specs import MEDIA_SPECS, canonical_kind, media_candidates, media_family

    kind = canonical_kind(kind)
    if kind not in {spec.kind for spec in MEDIA_SPECS}:
        raise InvalidRequestError(t("error.games.unknown_media_kind"),
                                  details={"unknown": kind,
                                           "known": sorted(spec.kind for spec in MEDIA_SPECS)})
    game_dir = Path(getattr(game, "fullPathGame", "") or "")
    hit = media_service.resolved_media(game_dir, table_stem).get(kind)
    path = hit.path if hit is not None else None

    files, medias = media_service.media_contents(game_dir)
    variant, active_sets = media_service.media_settings()
    candidates = media_candidates(game_dir, files, medias, kind, variant,
                                  table_stem, active_sets)
    recorded = asset_origin.sources(game_dir)
    hosts = {key: str(source.get("host", "") or "").strip()
             for key, source in recorded.items()
             if str(source.get("host", "") or "").strip()}
    return {
        "kind": kind,
        "family": media_family(kind),
        "present": path is not None,
        "file": path.name if path is not None else None,
        "path": asset_origin.path_of(game_dir, path) or None,
        "via": hit.tier if hit is not None else None,
        "origin": (asset_origin.origin_of(hosts, game_dir, path)
                   or None) if path is not None else None,
        "matched_to": asset_origin.match_of(recorded, game_dir, path) or None,
        "tiers": [{"tier": item.tier, "file": item.path.name,
                   "wins": item.path == path}
                  for item in candidates],
        "links": {"self": f"{prefix}/{kind}" if path is not None else None},
        **(_file_facts(path, kind) if path is not None else
           {"size_bytes": None, "modified": None, "width": None, "height": None}),
    }


def _into_slot(game, kind: str, table_id: str, source: Path, game_id: str,
               origin: str = "user", md5: str = "") -> dict:
    """Copy a file into the slot and answer with what now resolves.

    Shared by every route that fills a slot from a file that already exists somewhere -
    one on this machine, one the catalog published. Where the source is allowed to be
    is each caller's own question; this one is only about the write.
    """
    known = {spec.kind for spec in MEDIA_SPECS}
    if kind not in known:
        raise InvalidRequestError(t("error.games.unknown_media_kind"),
                                  details={"unknown": kind, "known": sorted(known)})
    game_dir = Path(getattr(game, "fullPathGame", "") or "")
    table_stem = _table_stem_or_404(game, table_id) if table_id else game_dir.name
    try:
        written = media_placement.place(game_dir, kind, table_stem, source)
    except media_placement.UnplaceableError as exc:
        raise InvalidRequestError(str(exc)) from exc
    # Recorded with who placed it, which is what lets a later media refresh tell its
    # own art from something hand-placed and leave the latter alone.
    media_placement.record_origin(game_dir, written, origin, md5)
    prefix = (f"/api/v1/games/{game_id}/tables/{table_id}/media" if table_id
              else f"/api/v1/games/{game_id}/media")
    entries = media_service.media_map(game_dir, prefix, table_stem if table_id else None)
    return {"written": written.name, "media": {kind: entries[kind]}}


def _placement(game_dir: Path, kind: str, spec, table_id: str, stem: str,
               label: str) -> dict:
    """One destination: what the file would be called there, and what it would take.

    The extension is trimmed back off the name because the file decides it, and it is
    only supplied here to satisfy the family check.
    """
    suffix = spec.family[0]
    going = media_placement.displaced(game_dir, kind, stem, suffix)
    return {"table": table_id, "label": label,
            "base": media_placement.target_name(kind, stem, suffix)[:-len(suffix)],
            # `as_posix`, never `str`: a relative path on the wire is forward-slashed
            # whatever host built it. `str(WindowsPath)` gave clients "medias\\bg.png"
            # on Windows and "medias/bg.png" everywhere else, for the same library.
            "displaces": sorted(path.relative_to(game_dir).as_posix()
                                for path in going)}


@router.get("/{game_id}/media/{kind}/placements",
            summary="Where a file for this kind could go, and what it would replace",
            dependencies=[requires(scopes.GAMES_READ)])
def get_placements(game_id: str, kind: str) -> models.MediaPlacementList:
    """Every name this kind can take in this folder, with the cost of each.

    The tier is a filename, so choosing where a file lands is choosing what it is
    called - and that is a decision worth making at the moment of the write rather
    than inferring from which lens somebody happened to leave open.

    Answered without the file, because it can be: what a write displaces is the whole
    family at that tier, which does not depend on the extension arriving.
    """
    spec = next((item for item in MEDIA_SPECS if item.kind == kind), None)
    if spec is None:
        raise InvalidRequestError(t("error.games.unknown_media_kind"),
                                  details={"unknown": kind,
                                           "known": sorted(item.kind for item in MEDIA_SPECS)})
    game = _game_or_404(game_id)
    game_dir = Path(getattr(game, "fullPathGame", "") or "")

    found = [_placement(game_dir, kind, spec, "", game_dir.name,
                        "Shared by every table")]
    for table in table_lens.table_rows(game, game_to_row(game)):
        stem = Path(table["filename"]).stem
        option = _placement(game_dir, kind, spec, table["id"], stem, table["filename"])
        # A .vpx named after its folder makes the two tiers the same filename, and they
        # are then the same file - the resolver finds it looking for either. Most
        # single-table folders are like that, so this is the common case rather than a
        # corner, and offering both would be two choices that do one thing.
        if table.get("id") and option["base"] not in {item["base"] for item in found}:
            found.append(option)
    return models.MediaPlacementList.model_validate(
        {"placements": found, "extensions": list(spec.family)})


@router.post("/{game_id}/media/{kind}/import",
             summary="Put a file from this machine into a slot",
             dependencies=[requires(scopes.GAMES_WRITE), requires(scopes.FILESYSTEM_READ)])
def import_media(game_id: str, kind: str, body: models.MediaImport) -> models.MediaWritten:
    """Copy artwork in from anywhere on this machine the install is allowed to read.

    Both scopes, because it is both things: it reads a file off the disk and it writes
    a game's media, and holding one of those is not permission for the other.

    A copy, not a move. The file is as likely to be a download somebody wants to keep
    as a stray, and deciding that for them is not this operation's job.
    """
    game = _game_or_404(game_id)
    source = filesystem.within_roots(body.path)
    if not source.is_file():
        raise InvalidRequestError(t("error.games.not_file"), details={"path": body.path})
    return models.MediaWritten(**_into_slot(game, kind, body.table, source, game_id))


@router.post("/{game_id}/media/{kind}/fetch",
             summary="Take a file from an online catalog into a slot",
             dependencies=[requires(scopes.GAMES_WRITE), requires(scopes.VPS_READ)])
def fetch_media(game_id: str, kind: str, body: models.MediaFetch) -> models.MediaWritten:
    """Download what an online catalog publishes and put it in the slot.

    A source and an id, never a URL: the only links this follows are ones a source
    produced for that id and kind, which is what stops it being a way to make this install
    fetch whatever a caller likes. The id does not have to be this game's - a mod, or a
    game the matcher got wrong, is exactly when the art has to come from another entry.
    """
    import tempfile

    from common.http_client import download_file
    from common.online import asset_sources

    from .mediasources import enabled_ids

    game = _game_or_404(game_id)
    offer = asset_sources.url_for(body.source, kind, body.vps_id, body.size,
                                  enabled_ids())
    if offer is None:
        raise NotFoundError(t("error.games.source_no_such_art"),
                            details={"source": body.source, "vps_id": body.vps_id,
                                     "kind": kind, "size": body.size})
    with tempfile.TemporaryDirectory() as staging:
        staged = Path(staging) / Path(offer.url).name
        try:
            download_file(offer.url, staged)
        except Exception as exc:
            raise FeatureUnavailableError(
                t("error.games.could_not_reach", source=(body.source), exc=(exc))) from exc
        # Stamped with the source and the source's own hash. Without the hash this art
        # is indistinguishable from hand-placed later, so a refresh would leave it
        # untouched forever - the bulk downloader has always recorded one.
        return models.MediaWritten(**_into_slot(game, kind, body.table, staged, game_id,
                          offer.source, offer.md5))


@router.get("/{game_id}/media/{kind}/detail", summary="One shared slot, in detail",
            dependencies=[requires(scopes.GAMES_READ)])
def get_game_media_detail(game_id: str, kind: str) -> models.MediaDetail:
    """What a curator needs about a slot and a frontend never asks for - the file's
    size and shape, and every tier holding one, not just the tier that won."""
    game = _game_or_404(game_id)
    return models.MediaDetail(**_media_detail(game, kind, None, f"/api/v1/games/{game_id}/media"))


@router.get("/{game_id}/tables/{table_id}/media/{kind}/detail",
            summary="One build's slot, in detail",
            dependencies=[requires(scopes.GAMES_READ)])
def get_table_media_detail(game_id: str, table_id: str, kind: str) -> models.MediaDetail:
    game = _game_or_404(game_id)
    return models.MediaDetail(**_media_detail(game, kind, _table_stem_or_404(game, table_id),
                         f"/api/v1/games/{game_id}/tables/{table_id}/media"))


@router.post("/{game_id}/media/{kind}/retier",
             summary="Rename a placed file so it serves a different tier",
             dependencies=[requires(scopes.GAMES_WRITE)])
def retier_media(game_id: str, kind: str, body: models.MediaRetier,
                 table: str = Query("", description="the build the file serves now")
                 ) -> models.MediaWritten:
    """Change who a file serves without sending it again.

    The tier is the filename, so this is a rename. `table` says where the file is now
    and the body says where it should go; either may be empty, which means the folder's
    shared name.
    """
    game = _game_or_404(game_id)
    game_dir = Path(getattr(game, "fullPathGame", "") or "")
    from_stem = _table_stem_or_404(game, table) if table else game_dir.name
    to_stem = _table_stem_or_404(game, body.table) if body.table else game_dir.name
    try:
        written = media_placement.retier(game_dir, kind, from_stem, to_stem)
    except media_placement.UnplaceableError as exc:
        raise InvalidRequestError(str(exc)) from exc

    prefix = (f"/api/v1/games/{game_id}/tables/{body.table}/media" if body.table
              else f"/api/v1/games/{game_id}/media")
    stem = to_stem if body.table else None
    entries = media_service.media_map(game_dir, prefix, stem)
    return models.MediaWritten.model_validate(
        {"written": written.name, "media": {kind: entries[kind]}})


def _displaced(game, kind: str, stem: str, filename: str) -> dict:
    """What a place of `filename` would displace at `stem`'s tier."""
    game_dir = Path(getattr(game, "fullPathGame", "") or "")
    try:
        going = media_placement.displaced(game_dir, kind, stem, Path(filename).suffix)
    except media_placement.UnplaceableError as exc:
        raise InvalidRequestError(str(exc)) from exc
    # Forward-slashed on the wire whatever host built it - see `_placements`.
    return {"displaced": sorted(path.relative_to(game_dir).as_posix()
                                for path in going)}


@router.get("/{game_id}/media/{kind}/displaced",
            summary="What placing this file here would replace",
            dependencies=[requires(scopes.GAMES_READ)])
def get_game_media_displaced(game_id: str, kind: str,
                             filename: str = Query(...)) -> models.MediaDisplaced:
    """Asked before an upload, so a confirmation can name the files rather than warn
    in the abstract - and so the bytes are not sent for a drop the user cancels."""
    game = _game_or_404(game_id)
    return models.MediaDisplaced(
        **_displaced(game, kind, Path(getattr(game, "fullPathGame", "")).name, filename))


@router.get("/{game_id}/tables/{table_id}/media/{kind}/displaced",
            summary="What placing this file for one build would replace",
            dependencies=[requires(scopes.GAMES_READ)])
def get_table_media_displaced(game_id: str, table_id: str, kind: str,
                              filename: str = Query(...)) -> models.MediaDisplaced:
    game = _game_or_404(game_id)
    return models.MediaDisplaced(
        **_displaced(game, kind, _table_stem_or_404(game, table_id), filename))


@router.put("/{game_id}/media/{kind}", summary="Place a file every table shares",
            dependencies=[requires(scopes.GAMES_WRITE)])
async def put_game_media(game_id: str, kind: str,
                         file: UploadFile = File(...)) -> models.MediaWritten:
    """Named for the folder, so every table in it resolves this unless it has its own."""
    game = _game_or_404(game_id)
    return await _write_media(game, kind, Path(getattr(game, "fullPathGame", "")).name,
                              file, f"/api/v1/games/{game_id}/media", None)


@router.put("/{game_id}/tables/{table_id}/media/{kind}",
            summary="Place a file for one build", dependencies=[requires(scopes.GAMES_WRITE)])
async def put_table_media(game_id: str, table_id: str, kind: str,
                          file: UploadFile = File(...)) -> models.MediaWritten:
    """Named for this .vpx, so it serves this build and no other."""
    game = _game_or_404(game_id)
    stem = _table_stem_or_404(game, table_id)
    return await _write_media(
        game, kind, stem, file,
        f"/api/v1/games/{game_id}/tables/{table_id}/media", stem)


@router.delete("/{game_id}/media/{kind}", summary="Remove the file every table shares",
               dependencies=[requires(scopes.GAMES_WRITE)])
def delete_game_media(game_id: str, kind: str) -> models.MediaRemoved:
    """Only the folder-named file. A build's own art and the default both survive."""
    game = _game_or_404(game_id)
    game_dir = Path(getattr(game, "fullPathGame", "") or "")
    try:
        removed = media_placement.remove(game_dir, kind, game_dir.name)
    except media_placement.UnplaceableError as exc:
        raise InvalidRequestError(str(exc)) from exc
    return models.MediaRemoved.model_validate({"removed": removed})


@router.delete("/{game_id}/tables/{table_id}/media/{kind}",
               summary="Remove one build's file",
               dependencies=[requires(scopes.GAMES_WRITE)])
def delete_table_media(game_id: str, table_id: str, kind: str) -> models.MediaRemoved:
    game = _game_or_404(game_id)
    game_dir = Path(getattr(game, "fullPathGame", "") or "")
    try:
        removed = media_placement.remove(game_dir, kind,
                                         _table_stem_or_404(game, table_id))
    except media_placement.UnplaceableError as exc:
        raise InvalidRequestError(str(exc)) from exc
    return models.MediaRemoved.model_validate({"removed": removed})


@router.put("/{game_id}/tables/{table_id}/hidden",
            summary="Offer this table in the frontend, or stop offering it",
            dependencies=[requires(scopes.GAMES_WRITE)])
def put_table_hidden(game_id: str, table_id: str,
                     body: models.TableVisibility) -> models.Table:
    """Take a table out of play without taking it off disk.

    The two are different acts and only one is reversible by itself: a hidden table is
    still there with its stats and its match, and a patch base that stopped being
    offered is exactly what this is for.
    """
    game = _game_or_404(game_id)
    filename = _table_filename_or_404(game, table_id)
    meta = MetaConfig(str(meta_file_path(game)))
    meta.set_table_hidden(filename, bool(body.hidden))
    game.meta_config = load_game_meta(game)
    return models.Table(**_table_or_404(game, table_id))


@router.post("/{game_id}/tables/{table_id}/script",
             summary="Extract this table's script beside it",
             dependencies=[requires(scopes.GAMES_WRITE)])
def extract_table_script(game_id: str, table_id: str) -> models.Table:
    """Write the table's script out as a `<table>.vbs` next to the .vpx.

    **This changes which script the table runs.** VPX loads a sidecar in place of the
    one inside the .vpx, so extracting is how a table is patched - and it is why the
    install reports the script as internal or external rather than as merely extracted.

    Runs the configured launcher with `-extractvbs`, so it answers for the machine it
    is called on, the same as `/launch`: an install with no VPX cannot do this.
    """
    game = _game_or_404(game_id)
    filename = _table_filename_or_404(game, table_id)
    game_dir = Path(getattr(game, "fullPathGame", "") or "")
    if not (game_dir / filename).is_file():
        raise NotFoundError(t("error.games.table_s_file_not"),
                            details={"table": table_id})
    table_id = entry_for_filename(table_entries(game.meta_config), filename)[0]
    # Asked before the work rather than read out of the failure: with the table's file
    # accounted for, every remaining launcher error means this machine cannot do it,
    # which is 501 and the answer /launch already gives - not a missing resource.
    try:
        launch.binary_for(table_id, filename)
    except launch.LaunchUnavailableError as exc:
        raise FeatureUnavailableError(
            t("error.games.extracting_script_runs_visual", exc=(exc))
        ) from exc
    try:
        game_service.extract_vbs(game_dir, filename, table_id)
    except Exception as exc:
        raise InvalidRequestError(t("error.games.could_not_extract_script", exc=(exc))) from exc
    return models.Table(**_table_or_404(game, table_id))


@router.delete("/{game_id}/tables/{table_id}/script",
               summary="Remove the script beside this table",
               dependencies=[requires(scopes.GAMES_WRITE)])
def delete_table_script(game_id: str, table_id: str) -> models.Table:
    """Take the sidecar away, which puts the table back on the script inside its .vpx.

    Whatever the sidecar held goes with it - a patch, an edit - and nothing else knows
    what was in it, which is why the surface asks first.
    """
    game = _game_or_404(game_id)
    game_dir = Path(getattr(game, "fullPathGame", "") or "")
    script = game_dir / f"{_table_stem_or_404(game, table_id)}.vbs"
    if not script.is_file():
        raise NotFoundError(t("error.games.table_no_script_beside"),
                            details={"table": table_id})
    script.unlink()
    return models.Table(**_table_or_404(game, table_id))


@router.put("/{game_id}/tables/{table_id}/rating", summary="Rate one table",
            dependencies=[requires(scopes.GAMES_WRITE)])
def put_table_rating(game_id: str, table_id: str,
                     payload: models.RatingRequest) -> models.Table:
    """A table's own rating, which refines the game's rather than replacing it.

    The open question the per-table rating left was how a user sets one when the wheel
    shows a single entry per game. The Console's Tables grid is the answer: the row you
    rate is the file. Additive on both lenses.

    Returns the table rather than the rating, because a client that just rated one is
    about to redraw the row.
    """
    game = _game_or_404(game_id)
    filename = _table_filename_or_404(game, table_id)
    set_table_rating(game, filename, payload.rating)
    game.meta_config = load_game_meta(game)
    return models.Table(**_table_or_404(game, table_id))


@router.put("/{game_id}/tables/{table_id}/source", summary="Say which release a table is",
            dependencies=[requires(scopes.GAMES_WRITE)])
def put_table_source(game_id: str, table_id: str,
                     payload: models.TableSourceRequest) -> models.Table:
    """Bind one table to the upstream release somebody says it is, or unbind it.

    A person picking from a list, never a guess: the identifier this records was
    retired at chance and is confidently wrong more often than not, so nothing here
    proposes an answer. An empty id takes the claim back.

    Returns the table, because a client that just bound one is about to redraw the row.
    """
    game = _game_or_404(game_id)
    filename = _table_filename_or_404(game, table_id)
    set_table_source(game, filename, payload.vps_file_id)
    game.meta_config = load_game_meta(game)
    return models.Table(**_table_or_404(game, table_id))


@router.put("/{game_id}/asset_source", summary="Say which VPS record one file is",
            dependencies=[requires(scopes.GAMES_WRITE)])
def put_asset_source(game_id: str,
                     payload: models.AssetSourceRequest) -> models.AssetSource:
    """Bind one media or asset file to the upstream record somebody says it is.

    Addressed by path rather than by kind and tier, because the ledger is keyed by path
    and a folder can hold several files of one kind. The path is not required to resolve
    to anything: binding a file the resolver currently passes over is legitimate, and
    refusing it would make the tier rules govern what may be recorded.
    """
    game = _game_or_404(game_id)
    try:
        source = set_asset_source(game, payload.path, payload.vps_file_id)
    except ValueError as exc:
        raise InvalidRequestError(str(exc)) from exc
    return models.AssetSource(**source)


@router.get("/{game_id}/vps_state", summary="What the catalog lists for this game, kind by kind",
            dependencies=[requires(scopes.GAMES_READ)])
def get_vps_state(game_id: str) -> models.VpsState:
    """Per kind: whether we hold one, how many the entry lists, and whether any of
    those is a file rather than a page.

    State, not findings. Which of these is worth telling somebody about is a judgement
    the surface makes with the library in front of it, and a producer deciding it here
    would be baking in the judgement the measurements say we make badly.

    `obtainable` is the honest word: it says the catalog lists a file, never that the
    file is yours to take. A host can hold something this account may not see, and
    nothing on this side can tell that without asking.
    """
    return models.VpsState(**library_vps_state.state_of(_game_or_404(game_id), game_id))


@router.get("/{game_id}/vps_details", summary="Where the game's details and its entry disagree",
            dependencies=[requires(scopes.GAMES_READ)])
def get_vps_details(game_id: str) -> models.VpsDetails:
    """Empty for a game whose details came from the entry it is still matched to.

    Which is every game that has never been re-matched: the details were written from
    the entry, so they agree with it by construction. Correcting a match is what fills
    this, and it fills it completely - the details go on describing the machine the
    game used to be.
    """
    game = _game_or_404(game_id)
    entry = game_service.matched_vps_entry(game)
    if not entry:
        return models.VpsDetails.model_validate({"differs": []})
    found = vps_details_differ(load_game_meta(game), entry)
    return models.VpsDetails.model_validate(
        {"differs": [{"field": field, "ours": _said(ours), "theirs": _said(theirs)}
                     for field, (ours, theirs) in found.items()]})


def _said(value) -> str:
    """One line a person reads, whatever the field holds - a year is a number and
    themes are a list, and a caller rendering a comparison wants neither shape."""
    if isinstance(value, list):
        return ", ".join(str(item) for item in value)
    return str(value if value is not None else "")


@router.put("/{game_id}/vps_details", summary="Take the entry's details",
            dependencies=[requires(scopes.GAMES_WRITE)])
def put_vps_details(game_id: str) -> models.VpsDetails:
    """Make the game's details describe the entry it is matched to.

    All of them together: they are one machine's facts, and a library holding this
    one's year beside that one's maker describes no machine at all. `Info.VPSId` is not
    among them - it is what VPS supplied, and the value a surface offers to revert a
    corrected match to.

    Returns the disagreement that is left, which is none - a client that just adopted
    is about to redraw the panel, and this is what it would ask for next.
    """
    game = _game_or_404(game_id)
    entry = game_service.matched_vps_entry(game)
    if not entry:
        raise NotFoundError(t("error.games.game_matched_no_vps"),
                            details={"game_id": game_id})
    adopt_vps_details(game, entry)
    return get_vps_details(game_id)


@router.put("/{game_id}/default_table", summary="Which table this game offers first",
            dependencies=[requires(scopes.GAMES_WRITE)])
def put_default_table(game_id: str, body: models.TableDefault) -> models.TableList:
    """Record the choice, or clear it by naming nothing.

    A game's default is the one a member naming only the game resolves to, so this is
    the difference between a collection playing the VR build and the desktop one.
    """
    game = _game_or_404(game_id)
    if body.table:
        _table_filename_or_404(game, body.table)
    meta = MetaConfig(str(meta_file_path(game)))
    try:
        meta.set_default_table(body.table)
    except ValueError as exc:
        raise InvalidRequestError(str(exc), details={"table": body.table}) from exc
    game.meta_config = load_game_meta(game)
    return models.TableList.model_validate(
        {"tables": table_lens.table_rows(game, game_to_row(game))})


def _table_filename_or_404(game, table_id: str) -> str:
    """The .vpx an id names, or a 404. Distinct from the media lens's stem lookup:
    this one wants the name on disk, not the stem a file would be named after."""
    entry = table_entries(load_game_meta(game)).get(table_id)
    filename = entry_filename(entry) if isinstance(entry, dict) else ""
    if not filename:
        raise NotFoundError(t("error.games.game_no_such_table"),
                            details={"game": getattr(game, "gameDirName", ""),
                                     "table": table_id})
    return filename


def _table_or_404(game, table_id: str) -> dict:
    found = next((t for t in table_lens.table_rows(game, game_to_row(game))
                  if t.get("id") == table_id), None)
    if found is None:
        raise NotFoundError(t("error.games.game_no_such_table"), details={"table": table_id})
    return found


@router.post("/{game_id}/tables/import", summary="Copy a game file into this game",
             status_code=201,
             dependencies=[requires(scopes.GAMES_WRITE), requires(scopes.FILESYSTEM_READ)])
def import_table(game_id: str, body: models.TableImport) -> models.Table:
    """Bring a game file in from anywhere on this machine the install may read.

    Both scopes, the same as putting artwork in a slot: it reads a file off the disk and
    it writes a game, and holding one of those is not permission for the other.

    One call rather than pointing at it and then bringing it in: an import interrupted
    between those two leaves a library of entries referencing a folder that was only
    ever meant to be read from. A copy, not a move.
    """

    game = _game_or_404(game_id)
    source = filesystem.within_roots(body.path)
    if not source.is_file():
        raise InvalidRequestError(t("error.games.not_file"), details={"path": body.path})
    if apps.app_for(source.name) is None:
        raise InvalidRequestError(
            t("error.games.nothing_build_knows_plays", name=(source.name)))

    game_dir = Path(getattr(game, "fullPathGame", "") or "")
    table_id = new_id()
    try:
        game_service.add_table_file(game_dir, source, table_id)
    except FileExistsError as exc:
        raise ConflictError(t("error.games.game_already_file_name"),
                            details={"filename": str(exc)}) from exc
    except (OSError, ValueError) as exc:
        raise ConflictError(t("error.games.could_not_bring", exc=(exc))) from exc

    game.meta_config = load_game_meta(game)
    return models.Table(**_table_or_404(game, table_id))


@router.post("/{game_id}/tables", summary="Add something this game holds with no file",
             status_code=201, dependencies=[requires(scopes.GAMES_WRITE)])
def add_keyed_table(game_id: str, body: models.NewTableRequest) -> models.Table:
    """Record a ROM, a Pinball FX table, or anything else its program finds by name.

    Nothing is scanned into existence here, and nothing can be: a folder scan finds
    files, and this is the one kind of entry that has none. Adding it is the only way
    it can arrive.

    We never resolve the key. The whole reason a key is not a path is that the program
    already looks it up, and better - pointing at `roms/mm.zip` would break the moment
    somebody reorganized their rompath.
    """
    game = _game_or_404(game_id)
    if body.path:
        return _add_referenced_table(game, str(body.path))

    app_id = str(body.app or "").strip()
    if apps.get(app_id) is None:
        raise InvalidRequestError(
            t("error.games.no_app_called_build", app_id=(app_id),
                    join=(', '.join(app.id for app in apps.all_apps()))))
    if not apps.get(app_id).claim.accepts_keys:
        raise InvalidRequestError(
            t("error.games.plays_files_not_names", app_name=(apps.app_name(app_id))))
    key = str(body.key or "").strip()
    if not key:
        raise InvalidRequestError(t("error.games.say_what_program_calls"))

    table_id = new_id()
    meta = MetaConfig(str(meta_file_path(game)))
    if not meta.add_keyed_table(app_id, key, table_id):
        raise ConflictError(t("error.games.game_already_one"),
                            details={"app": app_id, "key": key})
    game.meta_config = load_game_meta(game)
    return models.Table(**_table_or_404(game, table_id))


def _add_referenced_table(game, path: str):
    """A game file that lives somewhere else - on a read-only share, or one file two
    games both point at.

    Checked against the disk now, because a path that is wrong the moment it is typed is
    a typo and should be refused rather than kept as a broken record. A path that stops
    resolving later is a different thing: the location is unreachable, the entry stands,
    and nothing here is lost.
    """
    from common.games import locations

    game_dir = str(getattr(game, "fullPathGame", "") or "")
    target = os.path.expanduser(str(path or "").strip())
    if not target:
        raise InvalidRequestError(t("error.games.say_where_file"))
    if not os.path.isabs(target):
        raise InvalidRequestError(t("error.games.give_full_path_file"))
    if not os.path.isfile(target):
        raise NotFoundError(t("error.games.no_file"), details={"path": target})
    if apps.app_for(os.path.basename(target)) is None:
        raise InvalidRequestError(
            t("error.games.nothing_build_knows_plays", name=(os.path.basename(target))))
    if locations.canonical(os.path.dirname(target)) == locations.canonical(game_dir):
        raise InvalidRequestError(
            t("error.games.file_already_game_s"))

    # Relative where it survives the library moving, absolute where it would not.
    stored = locations.portable_reference(game_dir, target)
    table_id = new_id()
    meta = MetaConfig(str(meta_file_path(game)))
    if not meta.add_referenced_table(stored, table_id):
        raise ConflictError(t("error.games.game_already_points_file"),
                            details={"path": stored})
    game.meta_config = load_game_meta(game)
    return _table_or_404(game, table_id)


@router.post("/{game_id}/tables/{table_id}/contain",
             summary="Copy a referenced table in and stop pointing at it",
             dependencies=[requires(scopes.GAMES_WRITE)])
def contain_table(game_id: str, table_id: str) -> models.Table:
    """Bring the file into the game folder, so the entry stops depending on somewhere
    else being there.

    Per entry rather than for the whole library: the ten tables somebody actually cares
    about are worth the disk, and the rest can stay where they are.

    The id survives, which is the point - a collection that named this table and the
    play record on it both stay pointed at it. The file is copied and not moved: what it
    references may be read-only, shared with another game, or somebody else's.
    """
    import shutil

    game = _game_or_404(game_id)
    config = load_game_meta(game)
    entry = table_entries(config).get(table_id)
    if not isinstance(entry, dict) or not tables.entry_reference(entry):
        raise NotFoundError(t("error.games.game_no_such_reference"),
                            details={"table": table_id})

    game_dir = Path(getattr(game, "fullPathGame", "") or "")
    source = Path(tables.resolved_reference(str(game_dir),
                                            tables.entry_reference(entry)))
    if not source.is_file():
        raise ConflictError(
            t("error.games.file_not_reachable_nothing"),
            details={"path": str(source)})
    landing = game_dir / source.name
    if landing.exists():
        raise ConflictError(t("error.games.game_already_file_name"),
                            details={"filename": source.name})

    try:
        shutil.copy2(source, landing)
    except OSError as exc:
        raise ConflictError(t("error.games.could_not_copy", exc=(exc))) from exc

    meta = MetaConfig(str(meta_file_path(game)))
    if not meta.contain_referenced_table(table_id, source.name):
        # The copy landed and the record did not, which is the one state worth undoing:
        # a file in the folder with nothing describing it becomes a second table on the
        # next scan, beside the reference that is still there.
        landing.unlink(missing_ok=True)
        raise ConflictError(t("error.games.could_not_record"), details={"table": table_id})
    game.meta_config = load_game_meta(game)
    return models.Table(**_table_or_404(game, table_id))


@router.delete("/{game_id}/tables/{table_id}", summary="Forget a table that is gone",
               dependencies=[requires(scopes.GAMES_WRITE)])
def delete_table(game_id: str, table_id: str) -> models.TableForgotten:
    """Drop the record of a table whose file is no longer there.

    No file is deleted, because there is none - what goes is the entry describing it.
    Refused while the .vpx is on disk: that entry describes something the user owns, and
    the next refresh would mint it again anyway. Putting the file back and refreshing
    brings the table back, under a new id.
    """
    game = _game_or_404(game_id)
    config = load_game_meta(game)
    entry = table_entries(config).get(table_id)
    if not isinstance(entry, dict):
        raise NotFoundError(t("error.games.game_no_such_table"),
                            details={"game": getattr(game, "gameDirName", ""),
                                     "table": table_id})
    meta = MetaConfig(str(meta_file_path(game)))
    if tables.entry_key(entry) or tables.entry_reference(entry):
        # Nothing in this folder will mint one of these again, which is exactly why
        # forgetting it is safe where forgetting a table that is there is not. A
        # reference forgotten leaves the file it pointed at alone.
        meta.forget_keyed_table(table_id)
        game.meta_config = load_game_meta(game)
        return models.TableForgotten.model_validate({"forgotten": table_id})

    if not entry.get(ABSENT_SINCE_KEY):
        raise ConflictError(t("error.games.table_s_file_still"),
                            details={"table": table_id,
                                     "filename": entry.get("filename", "")})

    meta.forget_table(table_id)
    # The scan's copy still describes the table that just went.
    game.meta_config = load_game_meta(game)
    return models.TableForgotten.model_validate({"forgotten": table_id})


@router.post("/{game_id}/launch", summary="Launch a game on this play host",
             status_code=202, dependencies=[requires(scopes.LAUNCH_INVOKE)])
def launch_game(game_id: str,
                 payload: models.LaunchRequest | None = Body(default=None),
                 ) -> models.LaunchAccepted:
    """Start a game and return once it is starting, not once it is over.

    The same service the wheel and the Remote Control page use, so a launch from
    here counts as a play and releases the peripherals like any other.
    """
    game = _game_or_404(game_id)
    table = (payload.file or None) if payload else None
    ini_config = get_ini_config()

    try:
        resolved = launch.check_launchable(game, ini_config, table)
    except launch.LaunchBusyError as exc:
        raise ConflictError(str(exc)) from exc
    except launch.UnknownTableError as exc:
        raise InvalidRequestError(str(exc), details={"file": table}) from exc
    except launch.LaunchUnavailableError as exc:
        raise FeatureUnavailableError(str(exc)) from exc

    def run():
        try:
            launch.launch_game(game, ini_config, source=launch_state.SOURCE_API,
                                table=table)
        except Exception:
            logger.exception("Launch of %s failed", game_id)

    threading.Thread(target=run, daemon=True,
                     name=f"api-launch-{game_id[:8]}").start()
    return models.LaunchAccepted.model_validate(
        {"launching": True, "game_id": game_id,
         "file": Path(resolved).name,
         "links": {"state": "/api/v1/play/state", "events": "/api/v1/events"}})


@router.put("/{game_id}/details", summary="Say what the machine is",
            dependencies=[requires(scopes.GAMES_WRITE)])
def put_game_details(game_id: str, body: models.GameDetails) -> models.GameResource:
    """Describe a game no catalog has matched.

    Everything in a game's details normally arrives from VPSdb, which leaves nothing for
    one that came from somewhere else - a library converted from another frontend carries
    a year and a manufacturer, and they would otherwise be read and then dropped.

    Not where a VPS id goes. Saying which catalog record a game is claims an identity
    rather than describing a machine, and there is already a way to say it - the alt_vps_id
    override, which survives a rebuild because it is kept beside what was discovered
    rather than written on top of it.
    """
    game = _game_or_404(game_id)
    try:
        game_service.set_details(Path(str(game.fullPathGame)),
                                 body.model_dump(exclude_unset=True))
    except FileNotFoundError as exc:
        raise ConflictError(t("error.games.game_no_record_write"),
                            details={"path": str(exc)}) from exc
    except OSError as exc:
        raise ConflictError(t("error.games.could_not_write_2", exc=(exc))) from exc
    return get_game(game_id)


@router.put("/{game_id}/rating", summary="Rate a game",
            dependencies=[requires(scopes.GAMES_WRITE)])
def put_game_rating(game_id: str, payload: models.RatingRequest) -> models.Rating:
    """Set `User.Rating` on a game, 0-5.

    A whole-value PUT rather than a PATCH: the rating is the resource, and sending
    it again is the same request twice rather than a second increment.
    """
    game = _game_or_404(game_id)
    return models.Rating.model_validate({"rating": set_game_rating(game, payload.rating)})


@router.put("/{game_id}/tags", summary="The tags on a game",
            dependencies=[requires(scopes.GAMES_WRITE)])
def put_game_tags(game_id: str, payload: models.TagsRequest) -> models.Tags:
    """Set the whole set, the way the rating sets a whole value.

    Not a bag: a repeat is dropped, so sending the same tag twice is the same request
    twice. Case is left alone - two spellings stay two tags until somebody merges them,
    and folding them here would hide the duplicate rather than let it be found.
    """
    game = _game_or_404(game_id)
    return models.Tags.model_validate({"tags": set_game_tags(game, payload.tags)})


@router.put("/{game_id}/play_record", summary="Set a game's play counters",
            dependencies=[requires(scopes.GAMES_WRITE)])
def put_play_record(game_id: str, body: models.PlayRecordUpdate) -> models.PlayRecord:
    """Set a game's counters, for a library that arrives already played.

    The other half of the reset below, which says in its own note that setting a count
    to a number is the migration case and is not what it does. This is that case: a
    library converted from another frontend carries a play count and a last-played date,
    and dropping them makes a collection that sorts by either of those wrong on arrival.

    Rating, favorite and tags are opinions and have their own routes; these three are a
    record of what happened.
    """
    game = _game_or_404(game_id)
    return models.PlayRecord(**set_game_play_record(
        game,
        play_count=body.play_count,
        run_time_seconds=body.play_time_seconds,
        last_played=body.last_played))


@router.delete("/{game_id}/play_record", summary="Reset a game's play counters",
               dependencies=[requires(scopes.GAMES_WRITE)])
def reset_play_record(game_id: str) -> models.PlayRecord:
    """Put the counters back to nothing, leaving rating, favorite and tags alone.

    A DELETE, because what it removes is a record of what happened - and reset is the
    correction people actually want. A table launched twenty times while somebody was
    testing it reads as a favourite forever otherwise. Setting a count to a number is
    the migration case and is not this.
    """
    game = _game_or_404(game_id)
    return models.PlayRecord(**reset_game_play_record(game))


@router.delete("/{game_id}/tables/{table_id}/play_record",
               summary="Reset one table's play counters",
               dependencies=[requires(scopes.GAMES_WRITE)])
def reset_table_record(game_id: str, table_id: str) -> models.TablePlayRecord:
    """One table's counters. The game's total is not touched: they are two records of
    two things, and a game played on one build has still been played."""
    game = _game_or_404(game_id)
    filename = _table_filename_or_404(game, table_id)
    return models.TablePlayRecord(**reset_table_play_record(game, filename))


@router.put("/{game_id}/favorite", summary="Mark a game a favorite",
            dependencies=[requires(scopes.GAMES_WRITE)])
def put_game_favorite(game_id: str, payload: models.FavoriteRequest) -> models.Favorite:
    """Set `User.Favorite` on a game.

    A whole-value PUT, for the reason the rating gives: the flag is the resource, and
    sending it twice is the same request rather than a toggle that races itself.

    The field has been in the .info since the initial checkin with nothing ever writing
    it. This is the producer, and it writes a real boolean.
    """
    game = _game_or_404(game_id)
    return models.Favorite.model_validate({"favorite": set_game_favorite(game, payload.favorite)})


# Which keys each level will accept. Declared rather than inferred, so sending a
# table's key to the game route is refused instead of silently doing nothing - a
# write that reports success and changes nothing is the worst of the options.
_GAME_OVERRIDES = {"alt_title": "alt_title", "alt_vps_id": "alt_vpsid",
                   "frontend_dof_event": "frontend_dof_event"}
_TABLE_OVERRIDES = ("alt_launcher", "plugin_profile", "delete_nvram_on_close")


def _sent(payload: models.OverridesPatch) -> dict:
    """Only the fields the client actually sent. `None` is "leave alone"; `""` and
    `false` are real values that clear an override."""
    return {name: value for name, value in payload.model_dump().items()
            if value is not None}


@router.put("/{game_id}/overrides", summary="Set a game's overrides",
            dependencies=[requires(scopes.GAMES_WRITE)])
def put_game_overrides(game_id: str,
                       payload: models.OverridesPatch) -> models.GameOverrides:
    """What the user says about the machine, kept beside what VPS said.

    A PATCH in effect: only what is sent is written, because the six overrides are
    edited one field at a time and restating the others would make every save a race
    with whatever another surface changed meanwhile.
    """
    game = _game_or_404(game_id)
    changes = _sent(payload)
    unknown = set(changes) - set(_GAME_OVERRIDES)
    if unknown:
        raise InvalidRequestError(
            t("error.games.not_game_s_set", join=(', '.join(sorted(unknown)))))

    game_dir = Path(game.fullPathGame)
    for name, value in changes.items():
        if not game_service.update_vpinfe_setting(game_dir, _GAME_OVERRIDES[name],
                                                  value):
            raise ConflictError(t("error.games.could_not_write", name=(name)))
    return game_lens.game_resource(game_to_row(_game_or_404(game_id)), game_id)["overrides"]


@router.put("/{game_id}/tables/{table_id}/overrides",
            summary="Set one table's overrides",
            dependencies=[requires(scopes.GAMES_WRITE)])
def put_table_overrides(game_id: str, table_id: str,
                        payload: models.OverridesPatch) -> models.TableOverrides:
    """What the user says about one launchable file.

    Written onto the table's own entry, never onto the folder - a folder value is read
    as a fallback for a 2.x library but is not where anything lands now.
    """
    game = _game_or_404(game_id)
    changes = _sent(payload)
    unknown = set(changes) - set(_TABLE_OVERRIDES)
    if unknown:
        raise InvalidRequestError(
            t("error.games.not_table_s_set", join=(', '.join(sorted(unknown)))))

    game_dir = Path(game.fullPathGame)
    entries = table_entries(load_game_meta(game))
    if table_id not in entries:
        raise NotFoundError(t("error.games.no_table_id_game", table_id=(table_id),
                game_id=(game_id)))
    for name, value in changes.items():
        if not game_service.update_table_vpinfe_setting(game_dir, table_id, name,
                                                        value):
            raise ConflictError(t("error.games.could_not_write", name=(name)))
    fresh = table_entries(load_game_meta(_game_or_404(game_id)))
    return models.TableOverrides(**table_lens.table_overrides(fresh.get(table_id) or {},
                            vpinfe_section(_game_or_404(game_id).meta_config)))


@router.get("/{game_id}/archive", summary="Download the game folder as an archive",
            dependencies=[requires(scopes.GAMES_READ)])
def get_game_archive(request: Request, game_id: str, download_token: str = "",
                      full: bool = False, file: str = ""):
    from common.games.archive_service import cleanup_archive, create_vpxz_archive

    game = _game_or_404(game_id)
    if full:
        # The default bundle rides games:read; the whole folder is its own
        # permission. Local trust grants both today.
        identity = getattr(request.state, "identity", None)
        if identity is None or not identity.can(scopes.GAMES_EXPORT_FULL):
            raise ForbiddenError(f"Requires {scopes.GAMES_EXPORT_FULL}")
    game_dir_name = getattr(game, "gameDirName", "")
    try:
        archive = create_vpxz_archive(game_dir_name, everything=full,
                                      table=file or None)
    except ValueError as exc:
        raise InvalidRequestError(t("error.games.invalid_game_path")) from exc
    except FileNotFoundError as exc:
        raise NotFoundError(t("error.games.game_not_found")) from exc

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
