"""Slow work, as a resource.

The stream is how you follow a job; this is how you find out what is running
without having been connected, and how you learn the outcome if you missed the
event. Everything here is read-only - a job is started by asking for the work,
not by posting to /jobs, so the permission is always the permission of the work
itself.
"""

from __future__ import annotations

from fastapi import APIRouter, Query

from common import jobs as job_registry
from common.i18n import t

from . import models, scopes
from .auth import requires
from .errors import NotFoundError

router = APIRouter(prefix="/jobs", tags=["jobs"])


def resource(job: job_registry.Job, with_result: bool = False) -> dict:
    return {
        **job.snapshot(with_result),
        "links": {"self": f"/api/v1/jobs/{job.id}", "events": "/api/v1/events"},
    }


@router.get("", summary="Jobs, running first",
            dependencies=[requires(scopes.JOBS_READ)])
def list_jobs(kind: str = Query("", description="Filter by job kind")) -> models.JobList:
    found = job_registry.recent()
    if kind:
        found = [job for job in found if job.kind == kind]
    return {"jobs": [resource(job) for job in found]}


@router.get("/{job_id}", summary="One job",
            dependencies=[requires(scopes.JOBS_READ)])
def get_job(job_id: str) -> models.JobResource:
    """One job, and what it answered.

    The result is here and not on the list: some jobs answer with a row per game, and a
    listing carrying twenty of those would make watching the queue expensive.
    """
    job = job_registry.get(job_id)
    if job is None:
        raise NotFoundError(t("error.jobs.no_job_id", job_id=(job_id)))
    return resource(job, with_result=True)
