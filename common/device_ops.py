"""The devices this install knows about, and what it can ask them.

A device is another machine: a second VPinFE install, or a phone running VPX Mobile. The
registry is a copy of what each one reported, which goes stale by design - so reachability
is asked rather than stored, and what a phone is carrying is asked of the phone.
"""

from __future__ import annotations

from typing import Any

from common import device_client, device_registry, discovery, install_identity, service_errors
from common.device_registry import get_device_registry
from common.i18n import t
from common.paths import get_ini_config


def _resource(device) -> dict:
    return device.as_dict() | {"links": {"self": f"/api/v1/devices/{device.device_id}"}}


def device_or_refuse(device_id: str):
    found = get_device_registry().get(device_id)
    if found is None:
        raise service_errors.NotFoundError(
            t("error.devices.no_device_device_id", device_id=(device_id)))
    return found


def mobile_or_refuse(device_id: str):
    """The device a phone operation is about, refusing anything that is not a phone.

    An install carries its own library and its own API; asking one what folders it holds
    over a protocol only VPX Mobile speaks would be a question it cannot answer.
    """
    found = device_or_refuse(device_id)
    if found.kind != device_registry.KIND_VPX_MOBILE:
        raise service_errors.RefusedError(
            t("error.devices.vpinfe_install_not_device",
              value=(found.display_name or device_id)))
    if not found.address or not found.port:
        raise service_errors.RefusedError(
            t("error.devices.no_address_send", value=(found.display_name or device_id)))
    return found


def listing() -> dict[str, Any]:
    devices = get_device_registry().devices()
    return {"count": len(devices), "devices": [_resource(one) for one in devices]}


def resource(device_id: str) -> dict[str, Any]:
    return _resource(device_or_refuse(device_id))


def discovered() -> dict[str, Any]:
    """What mDNS has heard, as it stands.

    Not the registry: these are announcements, so nothing here has been recorded or
    decided about. It is what a picker offers and a person confirms.
    """
    found = discovery.peers()
    return {"count": len(found),
            "installs": [{"install_id": peer.install_id,
                          "display_name": peer.display_name,
                          "features": list(peer.features),
                          "address": peer.address, "port": peer.port,
                          "url": peer.url} for peer in found]}


def announce(device_id: str, kind: str, display_name: str, features,
             port: int, *, declared_address: str = "",
             heard_from: str = "") -> dict[str, Any]:
    """Idempotent by `device_id`: announcing twice is one device, heard from twice.

    Which address is kept depends on who is talking. An install announcing itself gets
    `heard_from` - the socket's address - never one it named: a device behind a router does
    not know how it is reached, and a caller that could name its own address could name
    someone else's. A phone is the other case: it is not the one calling, a person is
    registering it, so `declared_address` is the only address there is.

    A phone with no `device_id` is new, and its id is minted here. That is the only way to
    add a device that cannot identify itself, and it is why several phones can coexist:
    each gets its own id rather than one derived from an address they would both change.
    """
    device_id = (device_id or "").strip()
    is_mobile = kind == device_registry.KIND_VPX_MOBILE

    if not device_id:
        if not is_mobile:
            raise service_errors.RefusedError(
                t("error.devices.device_needs_device_id"))
        device_id = device_registry.mint_device_id()

    if is_mobile:
        address = (declared_address or "").strip()
        if not address:
            raise service_errors.RefusedError(t("error.devices.mobile_device_needs"))
    else:
        address = heard_from or ""

    device = get_device_registry().record(
        device_id,
        kind=kind,
        display_name=(display_name or "").strip(),
        features=tuple(features),
        address=address,
        # Declared, unlike the address: the socket says where a request came from, never
        # what that machine listens on. A device that does not say stays at 0 - what it
        # was told is read, and nobody is dialled.
        port=port,
    )
    if device is None:
        raise service_errors.RefusedError(t("error.devices.device_needs_device_id"))
    return _resource(device)


def probe_one(device) -> dict[str, Any]:
    """Dial one device, and record it as reachable if it answered.

    One at a time and off the caller's loop: a machine that is off costs its own short
    timeout and nobody else's answer.
    """
    registry = get_device_registry()
    local_id = install_identity.install_id(get_ini_config())
    client = device_client.for_device(device.as_dict(), local_id)
    found = device_client.probe(client)
    if found.get("state") == device_client.ANSWERING:
        registry.record_reachable(device.device_id)
    return {"device_id": device.device_id, **found}


def all_devices() -> list:
    return get_device_registry().devices()


def forget(device_id: str) -> None:
    """Forgetting one that is still running only means it announces itself again."""
    if not get_device_registry().forget(device_id):
        raise service_errors.NotFoundError(
            t("error.devices.no_device_device_id", device_id=(device_id)))
