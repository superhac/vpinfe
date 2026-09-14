"""What this instance is: discovery and health.

Not "meta" - every endpoint is metadata about something. These answer "what am I talking
to", which is the question discovery exists for.

Who this install is and how it announces itself is `common/install_presence.py`; what it
could become is `common/online/app_updater.py`. The discovery document is here, because
links over the wire are this layer's.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, BackgroundTasks, Body

from common import install_identity, install_presence
from common.games import launcher_migration, locations
from common.online import app_updater
from common.paths import get_ini_config
from common.vpinfe_version import get_version

from . import capabilities, models, scopes
from .auth import requires

logger = logging.getLogger("vpinfe.httpapi.instance")

# Startup wiring, called where the app is built.
announce_on_the_network = install_presence.announce_on_the_network


def mint_identity() -> None:
    """Give this install an id if it has none, seed its stores, and put it in its own
    registry.

    At startup rather than on a request: discovery only reads, so a GET never writes to
    the config file, and the id is on disk before anything can ask for it. Composed here
    rather than in common/ because two of the three things it seeds belong to the games
    package, and the layer that holds identity may not reach into a domain.
    """
    try:
        config = get_ini_config()
        install_identity.ensure_id(config)
    except Exception as exc:
        logger.warning("Could not mint this install's identity: %s", exc)
        return
    launcher_migration.ensure_seeded(config)
    locations.ensure_seeded(config)
    install_presence.record_self()


def discovery_payload(prefix: str, api_version: str) -> dict:
    """The discovery document. Links are relative so they survive a reverse proxy;
    present-but-null means a known link this instance does not offer."""
    return {
        # `name` is the product, byte-identical everywhere; `install_id` is who this is.
        "name": "VPinFE",
        **install_presence.identity(),
        "api_version": api_version,
        "vpinfe_version": get_version(),
        "capabilities": capabilities.declared(),
        "services": install_presence.service_ports(),
        "extensions": [],
        "links": {
            "self": prefix,
            "health": f"{prefix}/health",
            "openapi": f"{prefix}/openapi.json",
            "docs": f"{prefix}/docs",
            "collections": f"{prefix}/collections",
            "events": f"{prefix}/events",
            "jobs": f"{prefix}/jobs",
            "manufacturers": f"{prefix}/manufacturers",
            "devices": f"{prefix}/devices",
        },
    }


def build_router(prefix: str, api_version: str) -> APIRouter:
    router = APIRouter(tags=["instance"])

    @router.get("/", summary="API discovery", dependencies=[requires(scopes.INSTANCE_READ)])
    def discovery() -> models.Discovery:
        return models.Discovery(**discovery_payload(prefix, api_version))

    @router.get("/health", summary="Liveness check", dependencies=[requires(scopes.INSTANCE_READ)])
    def health() -> models.Health:
        return models.Health(status="ok")

    @router.get("/update", summary="Whether a newer build is published",
                dependencies=[requires(scopes.INSTANCE_READ)])
    async def update() -> models.UpdateCheck:
        """Served because a client cannot otherwise ask: 2.x calls the check in-process,
        which any consumer over HTTP has no way to do. Reaches the network, so it runs
        off the loop."""
        from starlette.concurrency import run_in_threadpool

        return models.UpdateCheck.model_validate(
            await run_in_threadpool(app_updater.check_now))

    @router.post("/update", summary="Take the published build", status_code=202,
                 dependencies=[requires(scopes.SYSTEM_ADMIN)])
    async def perform_update(
            background: BackgroundTasks,
            # Optional so a caller with nothing to say can post an empty body; the
            # defaults are what that means.
            payload: models.UpdateRequest | None = Body(default=None),
    ) -> models.UpdateStarted:
        """Stage the published build, then go down so the staged updater can apply it.

        `support_reason` is returned as the detail rather than a sentence, because the
        sentences a person reads belong to the surface showing them and restating them
        here would be a second copy to keep true.
        """
        from starlette.concurrency import run_in_threadpool

        wanted = payload or models.UpdateRequest()
        started = await run_in_threadpool(app_updater.take_published,
                                          stop_table=wanted.stop_table)
        # After the response: the staged updater waits on this pid, and quitting inside
        # the handler would take the process down before the caller was told anything.
        background.add_task(app_updater.quit_for_update)
        return models.UpdateStarted.model_validate(started)

    return router
