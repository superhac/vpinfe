"""Where an extension meets the API: the gate, and who is blamed when one throws.

An extension declares the actions it gates its own routes on; core mints the scope from
its name and attaches it here. Nothing an extension can write reaches a route without a
gate, because the extension does not attach one.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Request

from common import extensions
from common.i18n import t

from . import scopes
from .auth import requires
from .errors import FeatureUnavailableError

logger = logging.getLogger("vpinfe.httpapi.extensions")

PREFIX = "/ext"

router = APIRouter(prefix="/extensions", tags=["extensions"])


@router.get("", summary="What this install has loaded",
            dependencies=[requires(scopes.INSTANCE_READ)])
def list_extensions() -> dict:
    """Every extension this install looked at, running or not."""
    return {"extensions": [record.as_dict() for record in extensions.records()]}


def _running(name: str):
    """Refuse on an extension's own routes while it is not running.

    Its scopes are revoked as well, so this is not the only thing in the way. It is the
    one that says which extension and why, which a 403 would not.
    """
    async def check() -> None:
        record = extensions.registry().get(name)
        if record is None or not record.running:
            reason = record.reason if record is not None else "It is not installed"
            display = record.display_name if record is not None else name
            raise FeatureUnavailableError(t("error.extensions.the_extension_is_not",
                    display=(display), value=(reason or 'no reason recorded')))

    return Depends(check)


def mount(api) -> None:
    """Mount every router an extension registered, gated on the scope it declared.

    Once, at startup, whatever becomes of the extension after. A disabled one keeps its
    paths and refuses on them, where a 404 would read as a typo.
    """
    for record, ext_router, scope in extensions.mounted():
        manifest = record.manifest
        unknown = sorted(one for one in (manifest.scopes if manifest else ())
                         if not scopes.is_known(one))
        if unknown:
            extensions.refuse(record.name,
                              f"Asks for scopes that do not exist: {', '.join(unknown)}")
        for route in getattr(ext_router, "routes", []):
            # On each route rather than on the inclusion: the startup check that refuses
            # an ungated route reads what a route itself declares, and a gate it cannot
            # see is one nothing would notice the loss of.
            route.dependencies.extend([_running(record.name), requires(scope)])
        api.include_router(ext_router, prefix=f"{PREFIX}/{record.name}")
        logger.debug("Mounted %s/%s gated on %s", PREFIX, record.name, scope)


def blame(request: Request) -> None:
    """Disable the extension a failing request belonged to, if it belonged to one.

    Called from the envelope's unhandled-error handler. An extension raising an ApiError
    is answering rather than failing, and never arrives there.
    """
    path = request.url.path
    marker = f"{PREFIX}/"
    if marker not in path:
        return
    name = path.split(marker, 1)[1].split("/", 1)[0]
    if extensions.registry().get(name) is not None:
        extensions.disable(name, f"Unhandled error serving {path}")
