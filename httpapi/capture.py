"""Recording this device's own screens into its tables' media."""

from __future__ import annotations

from fastapi import APIRouter, Response
from fastapi.responses import FileResponse

from common.capture import preflight, proposals, run, trial

from . import jobs as jobs_api
from . import models, scopes
from .auth import requires

router = APIRouter(prefix="/capture", tags=["capture"])


@router.get("", summary="What this device can record, and why not",
            dependencies=[requires(scopes.PLAY_READ)])
def get_capture() -> models.CaptureReport:
    return models.CaptureReport.model_validate(preflight.report())


def _request(body: models.CaptureRequest) -> run.Request:
    return run.Request(games=body.games,
                       tables=[(one.game, one.table) for one in body.tables],
                       kinds=body.kinds, existing=body.existing, settings=body.settings,
                       sound=body.sound,
                       confirmed=body.confirmed.count if body.confirmed else None,
                       review=body.review)


@router.post("/plan", summary="What a recording would fill and replace, doing nothing",
             dependencies=[requires(scopes.GAMES_READ)])
def plan_capture(body: models.CaptureRequest) -> models.CapturePlan:
    return models.CapturePlan.model_validate(run.plan(_request(body)))


@router.post("/runs", summary="Record one game or table", status_code=202,
             dependencies=[requires(scopes.CAPTURE_RUN)])
def start_capture(body: models.CaptureRequest, response: Response) -> models.JobResource:
    job = run.start(_request(body))
    response.headers["Location"] = f"/api/v1/jobs/{job.id}"
    return models.JobResource(**jobs_api.resource(job))


@router.post("/test", summary="Record a few seconds of the playfield with the commands",
             dependencies=[requires(scopes.CAPTURE_RUN)])
def test_capture(body: models.CaptureTestRequest) -> models.CaptureTest:
    return models.CaptureTest.model_validate(trial.test(body.settings))


@router.get("/proposals", summary="Recordings waiting for a decision",
            dependencies=[requires(scopes.GAMES_READ)])
def get_proposals() -> models.CaptureProposals:
    return models.CaptureProposals.model_validate(proposals.listing())


@router.get("/proposals/{proposal_id}/file", summary="Play a recording waiting for a decision",
            dependencies=[requires(scopes.GAMES_READ)])
def get_proposal_file(proposal_id: str) -> FileResponse:
    return FileResponse(proposals.file_of(proposal_id))


@router.post("/proposals/{proposal_id}", summary="Place a recording, or throw it away",
             dependencies=[requires(scopes.CAPTURE_RUN)])
def decide_proposal(proposal_id: str,
                    body: models.CaptureProposalUse) -> models.CaptureProposalUsed:
    return models.CaptureProposalUsed.model_validate(proposals.decide(proposal_id, body.use))


@router.delete("/proposals", summary="Throw away every recording waiting",
               dependencies=[requires(scopes.CAPTURE_RUN)])
def discard_proposals() -> models.CaptureProposalsDiscarded:
    return models.CaptureProposalsDiscarded.model_validate(proposals.discard_all())
