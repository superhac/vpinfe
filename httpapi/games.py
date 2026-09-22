"""The game catalog.

A game is the pinball-machine concept - folder, identity, metadata, media and
assets. The launchable artifact is a table, exposed as a sub-resource, because a
game is not permanently one .vpx.

The answers come from `common/games/`: `game_lens` and `table_lens` read, `game_ops`,
`table_ops` and `media_ops` write. What is here is the wire - the path, the scope, the
model, and the few things only a request has, like an upload's bytes and a file response.
"""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path

from fastapi import APIRouter, Body, File, Query, Request, UploadFile
from starlette.background import BackgroundTask
from starlette.concurrency import run_in_threadpool
from starlette.responses import FileResponse, Response

from common import media_browse
from common.games import (
    archive_service,
    collection_ops,
    game_lens,
    game_ops,
    library_vps_state,
    media_ops,
    table_ops,
)
from common.host import play_service

from . import models, responses, scopes
from .auth import ForbiddenError, requires

logger = logging.getLogger("vpinfe.httpapi.games")

router = APIRouter(prefix="/games", tags=["games"])


@router.get("", summary="List games", dependencies=[requires(scopes.GAMES_READ)])
def list_games(
    q: str = Query("", description="Match against name, manufacturer or rom"),
    limit: int = Query(0, ge=0, description="0 returns everything"),
    offset: int = Query(0, ge=0),
) -> models.GameList:
    return models.GameList.model_validate(game_lens.listing(q, limit, offset))


@router.post("", summary="Create a game", status_code=201,
             dependencies=[requires(scopes.GAMES_WRITE)])
def create_game(body: models.NewGameRequest) -> models.GameResource:
    """A folder with a record in it, in the location new games go to."""
    return models.GameResource(**game_ops.create(body.name, body.location))


@router.get("/{game_id}", summary="One game", dependencies=[requires(scopes.GAMES_READ)])
def get_game(game_id: str) -> models.GameResource:
    return models.GameResource(**game_lens.detail(game_id))


@router.get("/{game_id}/collections", summary="The collections holding a game",
            dependencies=[requires(scopes.COLLECTIONS_READ)])
def get_game_collections(game_id: str) -> models.GameCollections:
    return models.GameCollections.model_validate(collection_ops.collections_of(game_id))


@router.get("/{game_id}/tables", summary="A game's tables",
            dependencies=[requires(scopes.GAMES_READ)])
def get_games(game_id: str) -> models.TableList:
    return models.TableList.model_validate(table_ops.rows_of(game_id))


@router.get("/{game_id}/media", summary="A game's shared media",
            dependencies=[requires(scopes.GAMES_READ)])
def get_game_media(game_id: str) -> models.MediaList:
    """Media is the artwork shown about a game - every kind, present or not, so a client
    can enumerate what is possible instead of guessing."""
    return models.MediaList.model_validate(media_ops.game_media(game_id))


@router.get("/{game_id}/media/overrides",
            summary="Kinds where a table has art of its own",
            dependencies=[requires(scopes.GAMES_READ)])
def get_media_overrides(game_id: str) -> models.MediaOverrideList:
    return models.MediaOverrideList.model_validate(media_ops.overrides(game_id))


@router.get("/{game_id}/media/{kind}", summary="One shared media file",
            dependencies=[requires(scopes.GAMES_READ)])
def get_game_media_file(game_id: str, kind: str, request: Request) -> Response:
    return responses.revalidating_file(media_ops.media_file(game_id, kind), request)


@router.get("/{game_id}/tables/{table_id}/media", summary="One table's media",
            dependencies=[requires(scopes.GAMES_READ)])
def get_table_media(game_id: str, table_id: str) -> models.MediaList:
    return models.MediaList.model_validate(media_ops.table_media(game_id, table_id))


@router.get("/{game_id}/tables/{table_id}/media/{kind}", summary="One table's media file",
            dependencies=[requires(scopes.GAMES_READ)])
def get_table_media_file(game_id: str, table_id: str, kind: str,
                         request: Request) -> Response:
    return responses.revalidating_file(
        media_ops.media_file(game_id, kind, table_id), request)


@router.get("/{game_id}/media/{kind}/placements",
            summary="Where a file for this kind could go, and what it would replace",
            dependencies=[requires(scopes.GAMES_READ)])
def get_placements(game_id: str, kind: str) -> models.MediaPlacementList:
    return models.MediaPlacementList.model_validate(
        media_ops.placements(game_id, kind))


@router.post("/{game_id}/media/{kind}/import",
             summary="Put a file from this machine into a slot",
             dependencies=[requires(scopes.GAMES_WRITE), requires(scopes.FILESYSTEM_READ)])
def import_media(game_id: str, kind: str, body: models.MediaImport) -> models.MediaWritten:
    """Copy artwork in from anywhere on this machine the install is allowed to read.

    Both scopes, because it is both things: it reads a file off the disk and it writes a
    game's media, and holding one of those is not permission for the other. Which paths
    this install may read is this layer's question, so it is answered here.
    """
    source = media_browse.within_roots(body.path)
    return models.MediaWritten(
        **media_ops.place_file(game_id, kind, body.table, source))


@router.post("/{game_id}/media/{kind}/fetch",
             summary="Take a file from an online catalog into a slot",
             dependencies=[requires(scopes.GAMES_WRITE), requires(scopes.VPS_READ)])
def fetch_media(game_id: str, kind: str, body: models.MediaFetch) -> models.MediaWritten:
    return models.MediaWritten(**media_ops.fetch_file(
        game_id, kind, body.table, body.source, body.vps_id, body.size))


@router.get("/{game_id}/media/{kind}/detail", summary="One shared slot, in detail",
            dependencies=[requires(scopes.GAMES_READ)])
def get_game_media_detail(game_id: str, kind: str) -> models.MediaDetail:
    return models.MediaDetail(**media_ops.detail(game_id, kind))


@router.get("/{game_id}/tables/{table_id}/media/{kind}/detail",
            summary="One build's slot, in detail",
            dependencies=[requires(scopes.GAMES_READ)])
def get_table_media_detail(game_id: str, table_id: str, kind: str) -> models.MediaDetail:
    return models.MediaDetail(**media_ops.detail(game_id, kind, table_id))


@router.post("/{game_id}/media/{kind}/retier",
             summary="Rename a placed file so it serves a different tier",
             dependencies=[requires(scopes.GAMES_WRITE)])
def retier_media(game_id: str, kind: str, body: models.MediaRetier,
                 table: str = Query("", description="the build the file serves now")
                 ) -> models.MediaWritten:
    """`table` says where the file is now and the body says where it should go; either may
    be empty, which means the folder's shared name."""
    return models.MediaWritten.model_validate(
        media_ops.retier(game_id, kind, table, body.table))


@router.get("/{game_id}/media/{kind}/displaced",
            summary="What placing this file here would replace",
            dependencies=[requires(scopes.GAMES_READ)])
def get_game_media_displaced(game_id: str, kind: str,
                             filename: str = Query(...)) -> models.MediaDisplaced:
    return models.MediaDisplaced(**media_ops.displaced(game_id, kind, filename))


@router.get("/{game_id}/tables/{table_id}/media/{kind}/displaced",
            summary="What placing this file for one build would replace",
            dependencies=[requires(scopes.GAMES_READ)])
def get_table_media_displaced(game_id: str, table_id: str, kind: str,
                              filename: str = Query(...)) -> models.MediaDisplaced:
    return models.MediaDisplaced(
        **media_ops.displaced(game_id, kind, filename, table_id))


async def _staged_write(game_id: str, kind: str, table_id: str, stem: str,
                        upload: UploadFile) -> dict:
    """Hold the upload's bytes somewhere real, then hand the path to the service.

    Here rather than in the service because the staging is the request's: this owns the
    bytes as they arrive and clears the temporary file whatever the write does.
    """
    media_ops.kind_or_refuse(kind)
    with tempfile.NamedTemporaryFile(suffix=Path(upload.filename or "").suffix,
                                     delete=False) as staged:
        staged.write(await upload.read())
        staged_path = staged.name
    try:
        return await run_in_threadpool(media_ops.place_upload, game_id, kind, table_id,
                                       Path(staged_path), stem)
    finally:
        Path(staged_path).unlink(missing_ok=True)


@router.put("/{game_id}/media/{kind}", summary="Place a file every table shares",
            dependencies=[requires(scopes.GAMES_WRITE)])
async def put_game_media(game_id: str, kind: str,
                         file: UploadFile = File(...)) -> models.MediaWritten:
    """Named for the folder, so every table in it resolves this unless it has its own."""
    stem = Path(game_lens.game_or_refuse(game_id).full_path_game or "").name
    return models.MediaWritten(**await _staged_write(game_id, kind, "", stem, file))


@router.put("/{game_id}/tables/{table_id}/media/{kind}",
            summary="Place a file for one build", dependencies=[requires(scopes.GAMES_WRITE)])
async def put_table_media(game_id: str, table_id: str, kind: str,
                          file: UploadFile = File(...)) -> models.MediaWritten:
    """Named for this .vpx, so it serves this build and no other."""
    stem = media_ops.stem_or_refuse(game_lens.game_or_refuse(game_id), table_id)
    return models.MediaWritten(
        **await _staged_write(game_id, kind, table_id, stem, file))


@router.delete("/{game_id}/media/{kind}", summary="Remove the file every table shares",
               dependencies=[requires(scopes.GAMES_WRITE)])
def delete_game_media(game_id: str, kind: str) -> models.MediaRemoved:
    """Only the folder-named file. A build's own art and the default both survive."""
    return models.MediaRemoved.model_validate(media_ops.remove(game_id, kind))


@router.delete("/{game_id}/tables/{table_id}/media/{kind}",
               summary="Remove one build's file",
               dependencies=[requires(scopes.GAMES_WRITE)])
def delete_table_media(game_id: str, table_id: str, kind: str) -> models.MediaRemoved:
    return models.MediaRemoved.model_validate(
        media_ops.remove(game_id, kind, table_id))


@router.put("/{game_id}/tables/{table_id}/hidden",
            summary="Offer this table in the frontend, or stop offering it",
            dependencies=[requires(scopes.GAMES_WRITE)])
def put_table_hidden(game_id: str, table_id: str,
                     body: models.TableVisibility) -> models.Table:
    return models.Table(**table_ops.set_hidden(game_id, table_id, body.hidden))


@router.post("/{game_id}/tables/{table_id}/script",
             summary="Extract this table's script beside it",
             dependencies=[requires(scopes.GAMES_WRITE)])
def extract_table_script(game_id: str, table_id: str) -> models.Table:
    """**This changes which script the table runs.** VPX loads a sidecar in place of the
    one inside the .vpx, so extracting is how a table is patched."""
    return models.Table(**table_ops.extract_script(game_id, table_id))


@router.delete("/{game_id}/tables/{table_id}/script",
               summary="Remove the script beside this table",
               dependencies=[requires(scopes.GAMES_WRITE)])
def delete_table_script(game_id: str, table_id: str) -> models.Table:
    """Puts the table back on the script inside its .vpx. Whatever the sidecar held goes
    with it, which is why the surface asks first."""
    return models.Table(**table_ops.delete_script(game_id, table_id))


@router.put("/{game_id}/tables/{table_id}/rating", summary="Rate one table",
            dependencies=[requires(scopes.GAMES_WRITE)])
def put_table_rating(game_id: str, table_id: str,
                     payload: models.RatingRequest) -> models.Table:
    """Returns the table rather than the rating, because a client that just rated one is
    about to redraw the row."""
    return models.Table(**table_ops.set_rating(game_id, table_id, payload.rating))


@router.put("/{game_id}/tables/{table_id}/source", summary="Say which release a table is",
            dependencies=[requires(scopes.GAMES_WRITE)])
def put_table_source(game_id: str, table_id: str,
                     payload: models.TableSourceRequest) -> models.Table:
    """An empty id takes the claim back."""
    return models.Table(
        **table_ops.set_source(game_id, table_id, payload.vps_file_id))


@router.put("/{game_id}/asset_source", summary="Say which VPS record one file is",
            dependencies=[requires(scopes.GAMES_WRITE)])
def put_asset_source(game_id: str,
                     payload: models.AssetSourceRequest) -> models.AssetSource:
    return models.AssetSource(
        **game_ops.set_file_source(game_id, payload.path, payload.vps_file_id))


@router.get("/{game_id}/vps_state", summary="What the catalog lists for this game, kind by kind",
            dependencies=[requires(scopes.GAMES_READ)])
def get_vps_state(game_id: str) -> models.VpsState:
    """State, not findings: which of these is worth telling somebody about is a judgement
    the surface makes with the library in front of it. `obtainable` says the catalog lists
    a file, never that the file is yours to take."""
    return models.VpsState(
        **library_vps_state.state_of(game_lens.game_or_refuse(game_id), game_id))


@router.get("/{game_id}/vps_details", summary="Where the game's details and its entry disagree",
            dependencies=[requires(scopes.GAMES_READ)])
def get_vps_details(game_id: str) -> models.VpsDetails:
    return models.VpsDetails.model_validate(game_ops.vps_details(game_id))


@router.put("/{game_id}/vps_details", summary="Take the entry's details",
            dependencies=[requires(scopes.GAMES_WRITE)])
def put_vps_details(game_id: str,
                    body: models.VpsAdoptRequest | None = None) -> models.VpsDetails:
    """Returns the disagreement that is left - none when everything was taken, and the
    rest when a caller named only some. A client is about to redraw the panel, and this
    is what it would ask for next."""
    return models.VpsDetails.model_validate(
        game_ops.adopt_details(game_id, (body.fields or None) if body else None))


@router.put("/{game_id}/default_table", summary="Which table this game offers first",
            dependencies=[requires(scopes.GAMES_WRITE)])
def put_default_table(game_id: str, body: models.TableDefault) -> models.TableList:
    """Record the choice, or clear it by naming nothing."""
    return models.TableList.model_validate(
        table_ops.set_default(game_id, body.table))


@router.post("/{game_id}/tables/import", summary="Copy a game file into this game",
             status_code=201,
             dependencies=[requires(scopes.GAMES_WRITE), requires(scopes.FILESYSTEM_READ)])
def import_table(game_id: str, body: models.TableImport) -> models.Table:
    """Both scopes, the same as putting artwork in a slot: it reads a file off the disk and
    it writes a game, and holding one of those is not permission for the other."""
    return models.Table(
        **table_ops.import_file(game_id, str(media_browse.within_roots(body.path))))


@router.post("/{game_id}/tables", summary="Add something this game holds with no file",
             status_code=201, dependencies=[requires(scopes.GAMES_WRITE)])
def add_keyed_table(game_id: str, body: models.NewTableRequest) -> models.Table:
    """Record a ROM, a Pinball FX table, or anything else its program finds by name - or,
    with a path, a file this game points at without holding."""
    if body.path:
        return models.Table(**table_ops.add_referenced(game_id, str(body.path)))
    return models.Table(**table_ops.add_keyed(game_id, body.app or "", body.key or ""))


@router.post("/{game_id}/tables/{table_id}/contain",
             summary="Copy a referenced table in and stop pointing at it",
             dependencies=[requires(scopes.GAMES_WRITE)])
def contain_table(game_id: str, table_id: str) -> models.Table:
    return models.Table(**table_ops.contain(game_id, table_id))


@router.delete("/{game_id}/tables/{table_id}", summary="Forget a table that is gone",
               dependencies=[requires(scopes.GAMES_WRITE)])
def delete_table(game_id: str, table_id: str) -> models.TableForgotten:
    """No file is deleted, because there is none - what goes is the entry describing it."""
    return models.TableForgotten.model_validate(table_ops.forget(game_id, table_id))


@router.post("/{game_id}/launch", summary="Launch a game on this play host",
             status_code=202, dependencies=[requires(scopes.LAUNCH_INVOKE)])
def launch_game(game_id: str,
                payload: models.LaunchRequest | None = Body(default=None),
                ) -> models.LaunchAccepted:
    """Start a game and return once it is starting, not once it is over."""
    started = play_service.start(game_id, (payload.file or None) if payload else None)
    return models.LaunchAccepted.model_validate(
        {**started,
         "links": {"state": "/api/v1/play/state", "events": "/api/v1/events"}})


@router.put("/{game_id}/details", summary="Say what the machine is",
            dependencies=[requires(scopes.GAMES_WRITE)])
def put_game_details(game_id: str, body: models.GameDetails) -> models.GameResource:
    """Describe a game no catalog has matched. Not where a VPS id goes - the alt_vps_id
    override is where that is said."""
    return models.GameResource(
        **game_ops.set_details(game_id, body.model_dump(exclude_unset=True)))


@router.put("/{game_id}/rating", summary="Rate a game",
            dependencies=[requires(scopes.GAMES_WRITE)])
def put_game_rating(game_id: str, payload: models.RatingRequest) -> models.Rating:
    """A whole-value PUT rather than a PATCH: the rating is the resource, and sending it
    again is the same request twice rather than a second increment."""
    return models.Rating.model_validate(game_ops.set_rating(game_id, payload.rating))


@router.put("/{game_id}/tags", summary="The tags on a game",
            dependencies=[requires(scopes.GAMES_WRITE)])
def put_game_tags(game_id: str, payload: models.TagsRequest) -> models.Tags:
    return models.Tags.model_validate(game_ops.set_tags(game_id, payload.tags))


@router.put("/{game_id}/guides", summary="The guides on a game",
            dependencies=[requires(scopes.GAMES_WRITE)])
def put_game_guides(game_id: str, payload: models.GuidesRequest) -> models.Guides:
    """The whole list, in order: which of VPS's are hidden, and the person's own. A guide
    VPS lists cannot be left out, only hidden."""
    return models.Guides.model_validate(game_ops.set_guides(
        game_id, [one.model_dump() for one in payload.guides]))


@router.put("/{game_id}/play_record", summary="Set a game's play counters",
            dependencies=[requires(scopes.GAMES_WRITE)])
def put_play_record(game_id: str, body: models.PlayRecordUpdate) -> models.PlayRecord:
    """For a library that arrives already played. Rating, favorite and tags are opinions
    and have their own routes; these three are a record of what happened."""
    return models.PlayRecord(**game_ops.set_play_record(
        game_id, play_count=body.play_count,
        play_time_seconds=body.play_time_seconds, last_played=body.last_played))


@router.delete("/{game_id}/play_record", summary="Reset a game's play counters",
               dependencies=[requires(scopes.GAMES_WRITE)])
def reset_play_record(game_id: str) -> models.PlayRecord:
    """A DELETE, because what it removes is a record of what happened."""
    return models.PlayRecord(**game_ops.reset_play_record(game_id))


@router.delete("/{game_id}/tables/{table_id}/play_record",
               summary="Reset one table's play counters",
               dependencies=[requires(scopes.GAMES_WRITE)])
def reset_table_record(game_id: str, table_id: str) -> models.TablePlayRecord:
    return models.TablePlayRecord(
        **table_ops.reset_play_record(game_id, table_id))


@router.put("/{game_id}/favorite", summary="Mark a game a favorite",
            dependencies=[requires(scopes.GAMES_WRITE)])
def put_game_favorite(game_id: str, payload: models.FavoriteRequest) -> models.Favorite:
    """A whole-value PUT, for the reason the rating gives: the flag is the resource, and
    sending it twice is the same request rather than a toggle that races itself."""
    return models.Favorite.model_validate(
        game_ops.set_favorite(game_id, payload.favorite))


def _sent(payload: models.OverridesPatch) -> dict:
    """Only the fields the client actually sent. `None` is "leave alone"; `""` and
    `false` are real values that clear an override."""
    return {name: value for name, value in payload.model_dump().items()
            if value is not None}


@router.put("/{game_id}/overrides", summary="Set a game's overrides",
            dependencies=[requires(scopes.GAMES_WRITE)])
def put_game_overrides(game_id: str,
                       payload: models.OverridesPatch) -> models.GameOverrides:
    return models.GameOverrides.model_validate(
        game_ops.set_overrides(game_id, _sent(payload)))


@router.put("/{game_id}/tables/{table_id}/overrides",
            summary="Set one table's overrides",
            dependencies=[requires(scopes.GAMES_WRITE)])
def put_table_overrides(game_id: str, table_id: str,
                        payload: models.OverridesPatch) -> models.TableOverrides:
    return models.TableOverrides(
        **table_ops.set_overrides(game_id, table_id, _sent(payload)))


@router.delete("/{game_id}/vps_match", summary="Say this game is in no catalog",
               dependencies=[requires(scopes.GAMES_WRITE)])
def delete_game_vps_match(game_id: str) -> models.GameOverrides:
    """Different from clearing the override, which puts the scan's answer back. This says
    there is no answer, and the scan's is not to be used."""
    return models.GameOverrides.model_validate(game_ops.declare_no_match(game_id))


@router.get("/{game_id}/archive", summary="Download the game folder as an archive",
            dependencies=[requires(scopes.GAMES_READ)])
def get_game_archive(request: Request, game_id: str, download_token: str = "",
                     full: bool = False, file: str = "") -> FileResponse:
    if full:
        # The default bundle rides games:read; the whole folder is its own permission.
        # Local trust grants both today.
        identity = getattr(request.state, "identity", None)
        if identity is None or not identity.can(scopes.GAMES_EXPORT_FULL):
            raise ForbiddenError(f"Requires {scopes.GAMES_EXPORT_FULL}")

    archive = archive_service.archive_for(game_id, everything=full, table=file)
    logger.info("Created download archive: %s", archive.path)

    def cleanup() -> None:
        archive_service.cleanup_archive(archive)
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
