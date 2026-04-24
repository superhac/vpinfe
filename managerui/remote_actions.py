from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RemoteAction:
    label: str
    command: str
    icon: str | None = None
    color_class: str = "text-cyan-400"
    enabled: bool = True


SYSTEM_CONTROLS = (
    RemoteAction("Restart VPinFE", "Restart VPinFE", "restart_alt", "text-green-400"),
    RemoteAction("Reboot", "Reboot", "replay", "text-orange-400"),
    RemoteAction("Shutdown", "Shutdown", "power_off", "text-red-400"),
    RemoteAction("Help", "Help", "help", "text-purple-400", False),
    RemoteAction("Update", "Update", "system_update", "text-yellow-400", False),
    RemoteAction("Settings", "Settings", "settings", "text-blue-400", False),
    RemoteAction("Info", "Info", "info", "text-cyan-400", False),
)

PINMAME_SERVICE_CONTROLS = tuple(
    RemoteAction(f"S{i}", f"Service {i}") for i in range(1, 9)
)
