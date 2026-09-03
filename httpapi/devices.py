"""The devices a hub knows about.

A device announces itself; the hub records what it said and when it last said it. That is
the whole of it - there is no routing, no aggregation and no picking one to launch on,
because all three need decisions *across* devices that nothing has made yet.

What it buys now is attribution: an event carries the `install_id` it happened on
(PAR-55), and for a VPinFE install that value is its `device_id`, so the registry is
what turns it into a name someone recognizes.

The registry is a cache of what each install last reported about itself. It goes stale by
design - the install owns its own name and roles, and this is a copy.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Body, Request, Response

from common import device_client, device_registry, install_identity
from common.device_registry import get_device_registry
from common.paths import get_ini_config

from . import models, scopes
from .auth import requires
from .errors import InvalidRequestError, NotFoundError

logger = logging.getLogger("vpinfe.httpapi.devices")

router = APIRouter(prefix="/devices", tags=["devices"])


def _resource(device) -> dict:
    return device.as_dict() | {"links": {"self": f"/api/v1/devices/{device.device_id}"}}


@router.get("", summary="The devices this hub knows",
            dependencies=[requires(scopes.DEVICES_READ)])
def list_devices() -> models.DeviceList:
    devices = get_device_registry().devices()
    return {"count": len(devices), "devices": [_resource(p) for p in devices]}


@router.get("/{device_id}", summary="One device",
            dependencies=[requires(scopes.DEVICES_READ)])
def get_device(device_id: str) -> models.DeviceResource:
    device = get_device_registry().get(device_id)
    if device is None:
        raise NotFoundError(f"No device with device id {device_id}")
    return _resource(device)


@router.put("", summary="Announce a device to this hub", status_code=200,
            dependencies=[requires(scopes.DEVICES_WRITE)])
def announce(request: Request,
             payload: models.DeviceAnnouncement = Body(...)) -> models.DeviceResource:
    """Idempotent by `device_id`: announcing twice is one device, heard from twice.

    Where the address comes from depends on who is talking. An install announcing
    itself gets the socket's address, never the body's: a device behind a router does
    not know how the hub reaches it, and a caller that could name its own address could
    name someone else's. A `vpx_mobile` entry is the other case - the phone is not the
    one calling, a person is registering it, so its address can only be declared. The
    socket there belongs to whoever filled in the form.

    A `vpx_mobile` entry with no `device_id` is new, and the hub mints one. That is the
    only way to add a device that cannot identify itself, and it is why several phones
    can coexist: each gets its own id rather than one derived from an address they would
    both change.
    """
    registry = get_device_registry()
    device_id = payload.device_id.strip()
    is_mobile = payload.kind == device_registry.KIND_VPX_MOBILE

    if not device_id:
        if not is_mobile:
            raise InvalidRequestError("A device needs a device id")
        device_id = device_registry.mint_device_id()

    if is_mobile:
        address = payload.address.strip()
        if not address:
            raise InvalidRequestError("A vpx_mobile device needs an address")
    else:
        client = getattr(request, "client", None)
        address = getattr(client, "host", "") or ""

    device = registry.record(
        device_id,
        kind=payload.kind,
        display_name=payload.display_name.strip(),
        roles=tuple(payload.roles),
        address=address,
        # Declared, unlike the address: the socket says where a request came from, never
        # what that machine listens on. A device that does not say stays at 0, which is
        # what it has always been - a hub reads what it was told and dials nobody.
        port=payload.port,
    )
    if device is None:
        raise InvalidRequestError("A device needs a device id")
    return _resource(device)


@router.post("/probe", summary="Ask every device whether it is there",
             dependencies=[requires(scopes.DEVICES_WRITE)])
async def probe_devices() -> models.DeviceProbeList:
    """Dial each device and report what answered, recording the ones that did.

    A write, because it advances each answering device's `last_reachable` - the pull
    half of that timestamp, where an announcement is the push half. Both prove the same
    thing; a hub can ask any time, and an install only says so at startup.

    One device at a time, off the loop. A machine that is off costs its own short
    timeout and nobody else's answer.
    """
    from starlette.concurrency import run_in_threadpool

    registry = get_device_registry()
    local_id = install_identity.install_id(get_ini_config())
    results = []
    for device in registry.devices():
        entry = device.as_dict()
        client = device_client.for_device(entry, local_id)
        found = await run_in_threadpool(device_client.probe, client)
        if found.get("state") == device_client.ANSWERING:
            await run_in_threadpool(registry.record_reachable, device.device_id)
        results.append({"device_id": device.device_id, **found})
    return {"probes": results}


@router.delete("/{device_id}", summary="Forget a device", status_code=204,
               dependencies=[requires(scopes.DEVICES_WRITE)])
def forget(device_id: str):
    """Forgetting one that is still running only means it announces itself again."""
    if not get_device_registry().forget(device_id):
        raise NotFoundError(f"No device with device id {device_id}")
    return Response(status_code=204)
