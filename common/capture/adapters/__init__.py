"""How this session's screens are reached, and which screen each window is on."""

from __future__ import annotations

import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol

from common.config_access import cfg_get
from common.host import tools

from ..geometry import Turn

PLAYFIELD = "playfield"
BACKGLASS = "backglass"
SCOREVIEW = "scoreview"
TOPPER = "topper"
WINDOWS = (PLAYFIELD, BACKGLASS, SCOREVIEW, TOPPER)

# The section each window's screen is set in. The topper has no window yet.
SCREEN_SECTIONS = {PLAYFIELD: "windows.playfield", BACKGLASS: "windows.backglass",
                   SCOREVIEW: "windows.score_view"}

NO_SCREEN = "capture.screen.none"
NOT_FOUND = "capture.screen.not_found"
NOT_YET = "capture.unsupported.not_yet"
NO_WAY = "capture.unsupported.no_way"
NO_SESSION = "capture.unsupported.no_session"


@dataclass(frozen=True)
class Output:
    """One of the compositor's outputs. `x`, `y`, `width` and `height` are where the
    desktop lays it out; `mode` is its own pixels before `transform`, which turns them
    into what the screen shows."""

    name: str
    x: int
    y: int
    width: int
    height: int
    mode: tuple[int, int]
    refresh: float
    transform: Turn

    @property
    def surface(self) -> str:
        return "portrait" if self.height > self.width else "landscape"


@dataclass(frozen=True)
class Screen:
    window: str
    output: Output | None = None
    # A catalog key, where there is no output.
    reason: str = ""


@dataclass(frozen=True)
class Unsupported:
    """A session nothing here can record, and why, as a catalog key and its values."""

    id: str
    reason: str
    params: Mapping[str, str] = field(default_factory=dict)


class Adapter(Protocol):
    id: str

    def requirements(self) -> tuple[tools.Tool, ...]: ...

    def outputs(self) -> list[Output]: ...

    def at_once(self, ffmpeg: tools.Found) -> bool: ...


def resolve(env: Mapping[str, str] | None = None,
            system: str | None = None) -> Adapter | Unsupported:
    """The adapter for this session, or why there is none. The first that applies."""
    from .wlr import WlrAdapter

    env = os.environ if env is None else env
    system = tools.here() if system is None else system
    if system == tools.WINDOWS:
        return Unsupported("ddagrab", NOT_YET, {"desktop": "Windows"})
    if system == tools.DARWIN:
        return Unsupported("avfoundation", NOT_YET, {"desktop": "macOS"})
    if env.get("WAYLAND_DISPLAY"):
        if WlrAdapter.applies(env):
            return WlrAdapter(env)
        desktops = str(env.get("XDG_CURRENT_DESKTOP") or "").upper().split(":")
        if "KDE" in desktops:
            return Unsupported("portal", NOT_YET, {"desktop": "KDE Plasma"})
        if "GNOME" in desktops:
            return Unsupported("portal", NOT_YET, {"desktop": "GNOME"})
        return Unsupported("wayland", NO_WAY)
    if env.get("DISPLAY"):
        return Unsupported("x11grab", NOT_YET, {"desktop": "X11"})
    return Unsupported("none", NO_SESSION)


def _matches(output: Output, monitor: Any) -> bool:
    return (int(monitor.x), int(monitor.y), int(monitor.width), int(monitor.height)) \
        == (output.x, output.y, output.width, output.height)


def screen_of(window: str, outputs: Sequence[Output], config: Any,
              monitors: Sequence[Any]) -> Screen:
    """Which output shows `window`. `screen_id` indexes the display model's monitors, not
    the compositor's outputs."""
    section = SCREEN_SECTIONS.get(window)
    raw = str(cfg_get(config, section, "screen_id") or "").strip() if section else ""
    if not raw:
        return Screen(window, reason=NO_SCREEN)
    try:
        monitor = monitors[int(raw)]
    except (ValueError, IndexError):
        return Screen(window, reason=NOT_FOUND)
    name = str(getattr(monitor, "name", "") or "")
    found = next((one for one in outputs if name and one.name == name), None) \
        or next((one for one in outputs if _matches(one, monitor)), None)
    return Screen(window, found) if found else Screen(window, reason=NOT_FOUND)
