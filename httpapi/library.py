"""Operations over the library as a whole, rather than one game.

A scan rewrites metadata across every game folder, which is why it lives here and not
under /games/{id} - it is not an operation on a game, and pretending it were would put a
library-wide write behind a per-table path.

`common/games/library_ops.py` does the work. The long ones answer 202 with a Location
header: accepted, not done, and something to watch while it runs.
"""

from __future__ import annotations

from fastapi import APIRouter, Body, Response

from common import jobs as job_registry
from common.games import game_service, library_ops

from . import jobs as jobs_api
from . import models, scopes
from .auth import requires
from .criteria import criteria_for

router = APIRouter(prefix="/library", tags=["library"])


def _accepted(response: Response, job: job_registry.Job) -> models.JobResource:
    """A started job, as the caller is handed it: where to watch, and what it is."""
    response.headers["Location"] = f"/api/v1/jobs/{job.id}"
    return models.JobResource(**jobs_api.resource(job))


@router.get("/filters", summary="What this library can be filtered on",
            dependencies=[requires(scopes.GAMES_READ)])
def filters() -> models.FilterAxisList:
    """Every filter axis, with the values this library holds. Projected from the registry
    the resolver matches on, so the two cannot disagree."""
    return models.FilterAxisList.model_validate(library_ops.filter_axes())


@router.get("/tags", summary="Every tag, and what each one says",
            dependencies=[requires(scopes.GAMES_READ)])
def list_tags() -> models.TagList:
    return models.TagList.model_validate(library_ops.tags())


@router.put("/tags/{tag}", summary="Say what a tag means and what color it wears",
            dependencies=[requires(scopes.GAMES_WRITE)])
def put_tag(tag: str, body: models.TagUpdate) -> models.TagResource:
    return models.TagResource.model_validate(
        library_ops.put_tag(tag, body.description, body.color))


@router.post("/tags/merge", summary="Fold tags into one",
             dependencies=[requires(scopes.GAMES_WRITE)])
def merge_tags(payload: models.TagMerge) -> models.TagSweep:
    """Rename is one source into a name nothing uses; merge is several into one."""
    return models.TagSweep.model_validate(
        library_ops.merge_tags(payload.sources, payload.into))


@router.delete("/tags/{tag}", summary="Remove a tag from every game",
               dependencies=[requires(scopes.GAMES_WRITE)])
def delete_tag(tag: str) -> models.TagSweep:
    return models.TagSweep.model_validate(library_ops.drop_tag(tag))


@router.get("/entries", summary="The entries the whole library resolves to",
            dependencies=[requires(scopes.GAMES_READ)])
def entries() -> models.EntryList:
    """The play lens over everything, which is what a frontend shows before a collection
    is chosen. `GET /collections/{name}/entries` is the same lens narrowed to one."""
    return models.EntryList.model_validate(library_ops.entries())


@router.post("/preview", summary="What a rule would match, storing nothing",
             dependencies=[requires(scopes.GAMES_READ)])
def preview(request: models.PreviewRequest = Body(...)) -> models.EntryList:
    """A POST because criteria are a structure rather than a query string: the registry
    grows, and several axes take a list."""
    return models.EntryList.model_validate(
        library_ops.preview(criteria_for(request.filters), request.limit or 0))


@router.post("/scan", summary="Rebuild game metadata from VPSdb", status_code=202,
             dependencies=[requires(scopes.GAMES_WRITE)])
def scan(response: Response,
         request: models.ScanRequest | None = Body(default=None)) -> models.JobResource:
    """Accepted, not done: the work runs on its own thread and reports on the event
    stream. The scope is games:write because that is what a scan does - it writes a .info
    for every game it can match."""
    options = request or models.ScanRequest()
    return _accepted(response, library_ops.scan(options.model_dump()))


@router.get("/policy", summary="What this library collects",
            dependencies=[requires(scopes.CONFIG_READ)])
def get_policy() -> models.LibraryPolicy:
    """The library's, not a machine's - so every install reading it gets one answer rather
    than each carrying its own copy of a question about somebody else's files."""
    return models.LibraryPolicy(**library_ops.policy())


@router.put("/policy", summary="Change what this library collects",
            dependencies=[requires(scopes.CONFIG_WRITE)])
def put_policy(payload: models.LibraryPolicyChange = Body(...)) -> models.LibraryPolicy:
    """A patch: only the keys sent are written."""
    return models.LibraryPolicy(
        **library_ops.set_policy(payload.model_dump(exclude_unset=True)))


@router.get("/watching", summary="Since when a catalog change counts as new",
            dependencies=[requires(scopes.GAMES_READ)])
def get_watching() -> models.Watching:
    """Empty means nobody has answered yet. Answering with everything the catalog has ever
    published would make the first look useless, which is why this is asked."""
    return models.Watching.model_validate(library_ops.watching_since())


@router.put("/watching", summary="Start watching from here",
            dependencies=[requires(scopes.GAMES_WRITE)])
def put_watching(payload: models.WatchingRequest) -> models.Watching:
    """One mechanism for both answers a first run offers: review everything is the
    beginning of time, start clean is now. There is no separate mode."""
    return models.Watching.model_validate(library_ops.watch_from(payload.since))


@router.post("/watching/acknowledge", summary="Dismiss one catalog change",
             dependencies=[requires(scopes.GAMES_WRITE)])
def acknowledge(payload: models.AcknowledgeRequest) -> models.Acknowledged:
    library_ops.acknowledge(payload.game_id, payload.kind, payload.vps_file_id)
    return models.Acknowledged(ok=True)


@router.get("/vps_state", summary="What the catalog lists across the whole library",
            dependencies=[requires(scopes.GAMES_READ)])
def library_vps_state() -> models.LibraryVpsState:
    """The last rollup counted, and when. Never live: a request that counted it would be
    seconds slow on any real library. `computed` empty means it has never run, which is
    not the same as every count being zero."""
    return models.LibraryVpsState(**library_ops.vps_rollup())


@router.post("/vps_state", summary="Count it again", status_code=202,
             dependencies=[requires(scopes.GAMES_READ)])
def recount_vps_state(response: Response) -> models.JobResource:
    """Accepted, not done. Read-only work, so it takes its own job kind and may run beside
    a scan rather than queueing behind one."""
    return _accepted(response, library_ops.recount_vps_state())


@router.post("/refresh", summary="Find tables added or removed on disk", status_code=202,
             dependencies=[requires(scopes.GAMES_WRITE)])
def refresh(response: Response) -> models.JobResource:
    """Accepted, not done. The local counterpart to a scan: it re-reads the folders, gives
    every .vpx it finds an id, notes the ones that are gone, and reads whatever nothing has
    read yet. It never touches the network."""
    return _accepted(response, library_ops.refresh())


@router.get("/info", summary="What the library's metadata files need",
            dependencies=[requires(scopes.GAMES_READ)])
def info_maintenance() -> models.InfoMaintenance:
    return models.InfoMaintenance.model_validate(library_ops.info_maintenance())


@router.post("/info/upgrade", summary="Bring every .info onto the current format",
             status_code=202, dependencies=[requires(scopes.GAMES_WRITE)])
def upgrade_info(response: Response) -> models.JobResource:
    """Accepted, not done. Each file is copied to `<name>.info.bak` before it is
    rewritten, which is what `/info/restore` puts back."""
    return _accepted(response, library_ops.one_info_pass(game_service.upgrade_info))


@router.post("/info/restore", summary="Put back the .info files saved before an upgrade",
             status_code=202, dependencies=[requires(scopes.GAMES_WRITE)])
def restore_info(response: Response) -> models.JobResource:
    """Accepted, not done. Everything written since the backup was taken goes with it - a
    rating set afterwards is in the new file, not the old one."""
    return _accepted(response, library_ops.one_info_pass(game_service.restore_info))


@router.get("/patches", summary="What script fixes are published for this library",
            dependencies=[requires(scopes.GAMES_READ)])
def script_patches() -> models.ScriptPatches:
    """Its own read rather than a flag on the apply, because what is being decided is
    whether to let something write a file into every game folder that needs one. Being
    able to ask first is the difference between a confirm and a leap."""
    return models.ScriptPatches(**library_ops.offered_patches())


@router.post("/patches", summary="Fetch the published script fixes", status_code=202,
             dependencies=[requires(scopes.GAMES_WRITE)])
def apply_script_patches(response: Response) -> models.JobResource:
    """Accepted, not done. A table that already has a sidecar is left alone and recorded
    as patched: whatever is in that file is what the table runs, and replacing it would
    overwrite somebody else's work."""
    return _accepted(response, library_ops.apply_script_patches())
