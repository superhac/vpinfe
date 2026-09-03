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


class NotThisDeviceError(RuntimeError):
    """Asked of a remote device something only the machine itself can answer."""


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
    device_id = str(device.get("device_id") or "")
    if local_device_id and device_id == local_device_id:
        return local()

    address = str(device.get("address") or "").strip()
    port = int(device.get("port") or 0)
    if not address or not port:
        return None
    return RemoteDevice(f"http://{address}:{port}")
