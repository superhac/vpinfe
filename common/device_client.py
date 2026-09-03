"""What a hub asks of a device: its displays, its browser, its input, its lifecycle.

One interface whether that device is this process or another machine. Narrow on purpose -
this is the surface a hub reaches, which is what has to be authenticated once a device is
reachable over a network.

A remote device answers only the questions that have a route on its own API. The rest are
in-process by nature: a hub cannot enumerate another machine's screens by asking politely,
and pretending otherwise would put a plausible wrong answer where a caller expected one.
Those raise rather than returning an empty list, because "no screens" and "not something
this device can be asked" are different facts and one of them is a bug.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger("vpinfe.common.device_client")

# A probe runs once per device on a page load, so a machine that is off should cost a
# moment rather than the whole listing. Much shorter than the ordinary call timeout.
_PROBE_TIMEOUT = 3


@dataclass(frozen=True)
class Display:
    """One screen, flattened out of whatever enumerated it: a hub cannot receive an
    NSScreen."""

    id: str
    x: int
    y: int
    width: int
    height: int


class LocalDevice:
    """The device in this process. Imports are deferred so that importing this module
    does not pull the frontend in - a hub-only install has no frontend to pull."""

    def displays(self) -> list[Display]:
        """This machine's screens as macOS reports them. Empty elsewhere, where the
        caller's own enumeration is already right."""
        import sys

        if not sys.platform.startswith("darwin"):
            return []
        try:
            from frontend.chromium_manager import get_mac_screens

            return [Display(id=f"Screen {index}", x=screen.x, y=screen.y,
                            width=screen.width, height=screen.height)
                    for index, screen in enumerate(get_mac_screens())]
        except Exception:
            logger.debug("Could not enumerate this machine's screens", exc_info=True)
            return []

    def browser_path(self) -> str | None:
        """Which browser this device would open its windows with, or None."""
        try:
            from frontend.chromium_manager import get_chromium_path

            return get_chromium_path().path
        except Exception:
            return None

    def browser_options(self, **kwargs: Any) -> list[str]:
        """The flags this device would launch its browser with."""
        from frontend.chromium_manager import get_builtin_chromium_options

        return get_builtin_chromium_options(**kwargs)

    def parse_browser_options(self, raw: str) -> list[str]:
        from frontend.chromium_manager import parse_additional_chromium_options

        return parse_additional_chromium_options(raw)


    def bindings(self, config) -> dict[str, list[str]]:
        from frontend import input_api

        return input_api.get_bindings(config)

    def wants_confirmation(self, scope: str) -> bool:
        from frontend import lifecycle_host

        return lifecycle_host.wants_confirmation(scope)

    def request(self, scope: str, action: str, **kwargs: Any) -> bool:
        from frontend import lifecycle_host

        return lifecycle_host.request(scope, action, **kwargs)

    def update_check(self) -> dict[str, Any]:
        from common.online.app_updater import check_for_updates

        return check_for_updates()

    def play_state(self) -> dict[str, Any]:
        from common.host import launch_state

        return launch_state.current().as_dict()


    def probe(self) -> dict[str, Any]:
        """Always answering: this is the process being asked."""
        from common.app_version import get_version

        return {"state": ANSWERING, "what": f"VPinFE {get_version()}", "reason": ""}


class NotThisDeviceError(RuntimeError):
    """Asked of a remote device something only the machine itself can answer."""


# What a probe found. `unreachable` and `unknown` are different answers: one means the
# hub asked and got nothing, the other that there was nothing to ask - an entry with no
# port, which a device being switched off never causes and switching it on never fixes.
ANSWERING = "answering"
UNREACHABLE = "unreachable"
UNASKABLE = "unaskable"


def probe(client) -> dict[str, Any]:
    """Whether a device answers, and what is on the other end.

    One shape for both kinds, because a row shows one of them at a time: `state`, and a
    `what` written for a person - the product and version for an install, and the bare
    fact of answering for a phone, which is all VPX Mobile's file listing proves.
    """
    if client is None:
        return {"state": UNASKABLE, "what": "",
                "reason": "This device has not said which port it answers on."}
    try:
        return client.probe()
    except Exception as exc:  # noqa: BLE001 - not answering is an answer
        return {"state": UNREACHABLE, "what": "", "reason": str(exc)}


class RemoteDevice:
    """A device on another machine, reached over the API it announced itself from.

    Every call is a request that can time out, so a caller runs these off whatever loop
    it is on. Failures are the caller's to report: a hub that cannot reach a device has
    something to say about it, and swallowing that here would leave a screen claiming a
    device is fine because nothing asked it.
    """

    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")

    def _url(self, path: str) -> str:
        return f"{self.base_url}/api/v1{path}"

    def displays(self) -> list[Display]:
        raise NotThisDeviceError("A hub cannot enumerate another machine's screens")

    def browser_path(self) -> str | None:
        raise NotThisDeviceError("A hub cannot read another machine's browser")

    def browser_options(self, **kwargs: Any) -> list[str]:
        raise NotThisDeviceError("A hub cannot read another machine's browser options")

    def parse_browser_options(self, raw: str) -> list[str]:
        raise NotThisDeviceError("A hub cannot read another machine's browser options")

    def bindings(self, config) -> dict[str, list[str]]:
        raise NotThisDeviceError("A hub cannot read another machine's input bindings")

    def wants_confirmation(self, scope: str) -> bool:
        """False, because the question has already been put. A confirm belongs on the
        surface that asked, and that surface is not on this machine."""
        return False

    def request(self, scope: str, action: str, **kwargs: Any) -> bool:
        from common import http_client, lifecycle

        if (scope, action) != (lifecycle.TABLE, lifecycle.STOP):
            raise NotThisDeviceError(
                f"No route on a device for {action} the {scope}")
        answer = http_client.post_json(self._url("/play/stop")) or {}
        return bool(answer.get("stopped"))

    def update_check(self) -> dict[str, Any]:
        from common import http_client

        return dict(http_client.get_json(self._url("/update")) or {})

    def play_state(self) -> dict[str, Any]:
        from common import http_client

        return dict(http_client.get_json(self._url("/play/state")) or {})

    def perform_update(self, *, stop_table: bool = False) -> dict[str, Any]:
        from common import http_client

        return dict(http_client.post_json(
            self._url("/update"), {"stop_table": stop_table}) or {})

    def config_schema(self) -> list[dict[str, Any]]:
        """What that install says its settings are. Read from the device rather than
        assumed, so one running a newer build offers what it actually has."""
        from common import http_client

        return list((http_client.get_json(self._url("/config/schema"))
                     or {}).get("sections") or [])

    def config_values(self) -> dict[str, Any]:
        from common import http_client

        return dict((http_client.get_json(self._url("/config"))
                     or {}).get("values") or {})

    def put_config(self, changes: dict[str, Any]) -> dict[str, Any]:
        """Write to another machine's config. The capability model allows it and this
        is the first thing to exercise it."""
        from common import http_client

        return dict((http_client.put_json(self._url("/config"), changes)
                     or {}).get("values") or {})

    def probe(self) -> dict[str, Any]:
        """Discovery, which is the cheapest call that proves who answered.

        Short timeout on purpose: this runs once per device on a page load, and a
        machine that is off should cost a moment rather than the whole listing.
        """
        from common import http_client

        said = dict(http_client.get_json(self._url(""), timeout=_PROBE_TIMEOUT) or {})
        name = str(said.get("name") or "VPinFE")
        version = str(said.get("app_version") or "")
        return {"state": ANSWERING,
                "what": f"{name} {version}".strip(),
                "roles": list(said.get("roles") or []),
                "install_id": str(said.get("install_id") or ""),
                "display_name": str(said.get("display_name") or ""),
                "reason": ""}


class MobileDevice:
    """A phone running VPX Mobile, which is not VPinFE and never answers as one.

    It speaks the file transfer protocol the 2.x Mobile page sends over and nothing
    else, so the questions a hub can put to it are a much shorter list - and the ones it
    cannot answer raise rather than returning a shape that looks like an answer.
    """

    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")

    def __getattr__(self, name: str):
        def refuse(*_args, **_kwargs):
            raise NotThisDeviceError(
                f"A VPX Mobile device does not answer {name}")
        return refuse

    def probe(self) -> dict[str, Any]:
        """Its file listing, which is the only thing it offers that proves it is there.

        There is no version to report: the protocol carries no identity, so what a
        person gets told is the bare fact - something is answering VPX Mobile there.
        """
        from common import http_client

        http_client.get_json(f"{self.base_url}/files", timeout=_PROBE_TIMEOUT)
        return {"state": ANSWERING, "what": "VPX Mobile", "reason": ""}


_local = LocalDevice()


def local() -> LocalDevice:
    """The device in this process. A function, not the instance, so reaching a remote
    device later changes which device is asked and not how."""
    return _local


def for_device(device: dict[str, Any], local_device_id: str | None = None):
    """The client for one registry entry, local or remote.

    A device is this process when its id is the one this install answers to. Everything
    else needs both halves of an address - a device that announced itself from before
    ports were recorded has no port, and there is nothing to dial.
    """
    from common import device_registry

    device_id = str(device.get("device_id") or "")
    if local_device_id and device_id == local_device_id:
        return local()

    address = str(device.get("address") or "").strip()
    port = int(device.get("port") or 0)
    if not address or not port:
        return None
    # By kind, because these speak different protocols entirely: a phone runs VPX Mobile
    # and has never heard of /api/v1, so asking it as though it had would report every
    # phone as unreachable.
    if str(device.get("kind") or "") == device_registry.KIND_VPX_MOBILE:
        return MobileDevice(f"http://{address}:{port}")
    return RemoteDevice(f"http://{address}:{port}")
