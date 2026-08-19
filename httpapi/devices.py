"""The devices a hub knows about.

A device announces itself; the hub records what it said and when it last said it. That is
the whole of it - there is no routing, no aggregation and no picking one to launch on,
because all three need decisions *across* devices that nothing has made yet.

What it buys now is attribution: an event carries the `install_id` it happened on
(PAR-55), and a registry is what turns that id into a name someone recognizes.

The registry is a cache of what each install last reported about itself. It goes stale by
design - the install owns its own name and roles, and this is a copy.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Body, Request, Response

from common.device_registry import get_device_registry

from . import models, scopes
from .auth import requires
from .errors import InvalidRequestError, NotFoundError

logger = logging.getLogger("vpinfe.httpapi.devices")

router = APIRouter(prefix="/devices", tags=["devices"])


def _resource(device) -> dict:
    return device.as_dict() | {"links": {"self": f"/api/v1/devices/{device.install_id}"}}


@router.get("", summary="The devices this hub knows",
            dependencies=[requires(scopes.DEVICES_READ)])
def list_devices() -> models.DeviceList:
    devices = get_device_registry().devices()
    return {"count": len(devices), "devices": [_resource(p) for p in devices]}


@router.get("/{install_id}", summary="One device",
            dependencies=[requires(scopes.DEVICES_READ)])
def get_device(install_id: str) -> models.DeviceResource:
    device = get_device_registry().get(install_id)
    if device is None:
        raise NotFoundError(f"No device with install id {install_id}")
    return _resource(device)


@router.put("", summary="Announce a device to this hub", status_code=200,
            dependencies=[requires(scopes.DEVICES_WRITE)])
def announce(request: Request,
             payload: models.DeviceAnnouncement = Body(...)) -> models.DeviceResource:
    """Idempotent: announcing twice is one device, heard from twice.

    The address is taken from the socket rather than the body. A device behind a
    router does not know how the hub reaches it, and a body that said would be a
    claim rather than an observation.
    """
    install_id = payload.install_id.strip()
    if not install_id:
        raise InvalidRequestError("A device needs an install id")

    client = getattr(request, "client", None)
    device = get_device_registry().record(
        install_id,
        display_name=payload.display_name.strip(),
        roles=tuple(payload.roles),
        address=getattr(client, "host", "") or "",
    )
    if device is None:
        raise InvalidRequestError("A device needs an install id")
    return _resource(device)


@router.delete("/{install_id}", summary="Forget a device", status_code=204,
               dependencies=[requires(scopes.DEVICES_WRITE)])
def forget(install_id: str):
    """Forgetting one that is still running only means it announces itself again."""
    if not get_device_registry().forget(install_id):
        raise NotFoundError(f"No device with install id {install_id}")
    return Response(status_code=204)
