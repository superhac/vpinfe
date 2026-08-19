"""What a hub asks of a device: its displays, its browser, its input, its lifecycle.

One interface whether that device is this process or another machine; only the local
resolution exists today. Narrow on purpose - this is the surface a hub reaches, which
is what has to be authenticated once a device is reachable over a network.
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


_local = LocalDevice()


def local() -> LocalDevice:
    """The device in this process. A function, not the instance, so reaching a remote
    device later changes which device is asked and not how."""
    return _local
