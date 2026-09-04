"""What this instance is: discovery and health.

Not "meta" - every endpoint is metadata about something. These answer "what am I
talking to", which is the question discovery exists for. Table metadata is a
different thing entirely and lives under common/.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, BackgroundTasks, Body

from common import (
    device_client,
    device_registry,
    discovery,
    install_identity,
    lifecycle,
)
from common.app_version import get_version
from common.config_access import NetworkConfig
from common.device_registry import get_device_registry
from common.host import launch_state
from common.paths import get_ini_config

from . import capabilities, models, scopes
from .auth import requires
from .errors import ConflictError, FeatureUnavailableError

logger = logging.getLogger("vpinfe.httpapi.instance")


def mint_identity() -> None:
    """Give this install an id if it has none, and put it in its own registry.

    At startup rather than on a request: discovery only reads, so a GET never writes to
    the config file, and the id is on disk before anything can ask for it.

    The hub records itself because it is a device too - it is the one you are standing
    at. Leaving it out meant every screen listing devices had to synthesise a row for
    the machine it was running on, and that row was the only one nothing could forget.
    """
    try:
        config = get_ini_config()
        install_identity.ensure_id(config)
    except Exception as exc:
        logger.warning("Could not mint this install's identity: %s", exc)
        return
    record_self()


def announce_on_the_network() -> None:
    """Say what this install is, and note the ones that say back.

    Started with the API because that is what the announcement points at: the port in the
    record is the one these routes answer on.
    """
    try:
        config = get_ini_config()
    except Exception as exc:
        logger.warning("Could not read this install to announce it: %s", exc)
        return
    discovery.start(config, on_peer=_heard_from)


def _heard_from(peer) -> None:
    """File an install this one heard from, when managing devices is its job.

    The feature is read per announcement rather than once at startup, so switching it on
    from the Console does not need every other machine to restart before it is noticed.
    """
    try:
        config = get_ini_config()
        if not install_identity.has_feature(config, install_identity.DEVICES):
            return
        get_device_registry().record(
            peer.install_id,
            kind=device_registry.KIND_VPINFE,
            display_name=peer.display_name,
            features=peer.features,
            address=peer.address,
            port=peer.port,
        )
    except Exception:
        logger.debug("Could not record the install that announced itself", exc_info=True)


def record_self() -> None:
    """Put what this install currently calls itself into its own registry entry.

    Called again whenever the name changes, not only at startup. A registry entry is a
    copy of what an install reported, which for a remote device goes stale by design -
    but this install can say so the moment it is renamed, and every screen listing
    devices reads the registry rather than asking each one.
    """
    try:
        config = get_ini_config()
        get_device_registry().record(
            install_identity.install_id(config),
            kind=device_registry.KIND_VPINFE,
            display_name=install_identity.display_name(config),
            features=install_identity.features(config),
        )
    except Exception as exc:
        # A registry that cannot be written must not stop the API starting: the entry is
        # a label, and the install is identified with or without it.
        logger.warning("Could not record this install in its own registry: %s", exc)
        return
    # The announcement carries the same two facts, so it is refreshed with them rather
    # than left saying what this install used to be called until the next restart.
    discovery.refresh(config)


def _identity() -> dict:
    """Who is answering. A broken config must not take discovery down with it, so this
    degrades to the unidentified answer 2.x gave rather than raising."""
    try:
        config = get_ini_config()
        return {
            "install_id": install_identity.install_id(config),
            "display_name": install_identity.display_name(config),
            "features": install_identity.features(config),
        }
    except Exception as exc:
        logger.warning("Could not read this install's identity: %s", exc)
        return {"install_id": "", "display_name": "", "features": []}


def _services() -> dict:
    """Where this install's other servers are, for a client that is not on this machine.

    Only the asset server so far, and only its port: the host is wherever the caller
    reached this document, which is the one address known to be routable to here. A
    device needs this because artwork is served off a different port from the API, and
    nothing else tells it which - guessing 8000 is right until someone moves it.
    """
    try:
        return {"assets": {"port": NetworkConfig.from_config(get_ini_config()).theme_assets_port}}
    except Exception as exc:
        logger.warning("Could not read this install's service ports: %s", exc)
        return {}


def discovery_payload(prefix: str, api_version: str) -> dict:
    """The discovery document. Links are relative so they survive a reverse proxy;
    present-but-null means a known link this instance does not offer."""
    return {
        # `name` is the product, byte-identical everywhere; `install_id` is who this is.
        "name": "VPinFE",
        **_identity(),
        "api_version": api_version,
        "app_version": get_version(),
        "capabilities": capabilities.declared(),
        "services": _services(),
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
        return discovery_payload(prefix, api_version)

    @router.get("/health", summary="Liveness check", dependencies=[requires(scopes.INSTANCE_READ)])
    def health() -> models.Health:
        return {"status": "ok"}

    @router.get("/update", summary="Whether a newer build is published",
                dependencies=[requires(scopes.INSTANCE_READ)])
    async def update() -> models.UpdateCheck:
        """What this install could become, and whether it can get there itself.

        Served because a client cannot otherwise ask: the check lives under common/ and
        2.x calls it in-process, which any consumer over HTTP - this project's own hub
        included - has no way to do. `update_supported` is false for an install that
        cannot replace itself, and `support_reason` says why, so a caller offers the
        right thing rather than a button that fails.

        Reaches the network, so it runs off the loop. Never raises: not knowing whether
        an update exists is not a reason to fail a request, and `error` carries it.
        """
        from starlette.concurrency import run_in_threadpool

        from common.online.app_updater import check_for_updates
        try:
            return await run_in_threadpool(check_for_updates)
        except Exception as exc:
            logger.warning("Could not check for updates: %s", exc)
            return {"update_available": False, "error": str(exc),
                    "current_version": get_version(), "latest_version": None,
                    "update_supported": False, "support_reason": "check failed",
                    "triplet": None, "asset_name": None}

    @router.post("/update", summary="Take the published build", status_code=202,
                 dependencies=[requires(scopes.SYSTEM_ADMIN)])
    async def perform_update(
            background: BackgroundTasks,
            # Optional so a caller with nothing to say can post an empty body; the
            # defaults are what that means.
            payload: models.UpdateRequest | None = Body(default=None),
    ) -> models.UpdateStarted:
        """Stage the published build, then go down so the staged updater can apply it.

        Order matters: the download happens before anything is stopped, so a failed or
        unavailable update costs nobody their game. Only once there is a verified
        package does a running table get closed.

        `support_reason` is returned as the detail rather than a sentence, because the
        sentences a person reads belong to the surface showing them and restating them
        here would be a second copy to keep true.
        """
        from starlette.concurrency import run_in_threadpool

        from common.online.app_updater import (
            force_exit_after_handoff,
            get_install_context,
            launch_prepared_update,
            prepare_update,
        )

        wanted = payload or models.UpdateRequest()
        context = await run_in_threadpool(get_install_context)
        if not context["supported"]:
            raise FeatureUnavailableError("This install cannot replace itself",
                                          details={"support_reason": context["reason"]})

        playing = launch_state.current()
        if playing.launching and not wanted.stop_table:
            raise ConflictError("A table is running",
                                details={"game_name": playing.game_name})

        prepared = await run_in_threadpool(prepare_update)

        stopped_table = None
        if playing.launching:
            if device_client.local().request(
                    lifecycle.TABLE, lifecycle.STOP,
                    origin=lifecycle.Origin(lifecycle.SURFACE_API),
                    reason="making way for an update"):
                stopped_table = playing.game_name

        await run_in_threadpool(lambda: launch_prepared_update(prepared))
        force_exit_after_handoff()
        # After the response: the staged updater waits on this pid, and quitting inside
        # the handler would take the process down before the caller was told anything.
        background.add_task(_quit_for_update)
        return {"latest_version": prepared["latest_version"],
                "stopped_table": stopped_table}

    return router


def _quit_for_update() -> None:
    """Go down the ordinary way, so the services shut down and the windows close."""
    device_client.local().request(
        lifecycle.APP, lifecycle.STOP,
        origin=lifecycle.Origin(lifecycle.SURFACE_API),
        reason="an update is staged")
