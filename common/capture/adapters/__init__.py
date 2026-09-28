"""How this session's screens are reached, and which screen each window is on."""

from __future__ import annotations

import os
import signal
import subprocess
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
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
SCREEN_PERMISSION = "capture.permission.screen"
SOUND_NOT_YET = "capture.sound.not_yet"
SOUND_LOOPBACK = "capture.sound.needs_loopback"


@dataclass(frozen=True)
class Output:
    """One of the compositor's outputs. `x`, `y`, `width` and `height` are where the
    desktop lays it out; `mode` is its own pixels before `transform`, which turns them
    into what the screen shows. `index` is the capture API's own number for it."""

    name: str
    x: int
    y: int
    width: int
    height: int
    mode: tuple[int, int]
    refresh: float
    transform: Turn
    index: int = 0

    @property
    def surface(self) -> str:
        return "portrait" if self.height > self.width else "landscape"


@dataclass(frozen=True)
class Screen:
    window: str
    output: Output | None = None
    # A catalog key and its values beside the window's, where there is no output.
    reason: str = ""
    params: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class Window:
    """A window the desktop has, and the output it is on. `app_id` is Wayland's, or
    X11's class."""

    app_id: str
    title: str
    output: str


@dataclass(frozen=True)
class Unsupported:
    """A session nothing here can record, and why, as a catalog key and its values."""

    id: str
    reason: str
    params: Mapping[str, str] = field(default_factory=dict)


@dataclass
class Recording:
    """A recorder running. `started` is the monotonic clock when it was started."""

    window: str
    path: Path
    process: Any
    started: float

    def stop(self, timeout: float = 5.0) -> None:
        """Asked to finish, so the recorder writes the end of its file: `q` on a stdin
        `spawn` left open, as FFmpeg reads it, or else SIGINT, as Ctrl-C. Killed if it has
        not gone in `timeout`."""
        pipe = getattr(self.process, "stdin", None)
        if self.process.poll() is None:
            if pipe is not None:
                try:
                    pipe.write(b"q")
                    pipe.flush()
                except (OSError, ValueError):
                    pass
            else:
                self.process.send_signal(signal.SIGINT)
        try:
            self.process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait(timeout=timeout)
        finally:
            if pipe is not None:
                try:
                    pipe.close()
                except OSError:
                    pass


def spawn(popen: Callable[..., Any], argv: list[str], **streams: Any) -> Any:
    """A recorder, started so `Recording.stop` can end it."""
    stdin = subprocess.PIPE if tools.here() == tools.WINDOWS else subprocess.DEVNULL
    return popen(argv, stdin=stdin, creationflags=tools.NO_WINDOW,
                 **{"stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL, **streams})


class Adapter(Protocol):
    @property
    def id(self) -> str: ...

    # The Tool that takes a picture of a screen, and the one that records it.
    @property
    def picture_tool(self) -> tools.Tool: ...

    @property
    def video_tool(self) -> tools.Tool: ...

    def requirements(self) -> tuple[tools.Tool, ...]: ...

    def grabs(self, ffmpeg: tools.Found) -> bool:
        """Whether this FFmpeg can read this desktop's screens where it has to."""
        ...

    def refused(self) -> str:
        """A catalog key where the desktop does not let VPinFE record its screens."""
        ...

    def no_sound(self) -> tuple[str, Mapping[str, str]] | None:
        """Why sound is never recorded here, as a catalog key and its values."""
        ...

    def outputs(self) -> list[Output]: ...

    def windows(self) -> list[Window]: ...

    def at_once(self, ffmpeg: tools.Found) -> bool: ...

    def hardware(self, ffmpeg: tools.Found) -> str: ...

    def still(self, found: Mapping[str, tools.Found], output: Output,
              dest: Path) -> list[str]: ...

    def still_turn(self, output: Output) -> Turn: ...

    def recording_turn(self, output: Output) -> Turn: ...


def resolve(env: Mapping[str, str] | None = None,
            system: str | None = None) -> Adapter | Unsupported:
    """The adapter for this session, or why there is none. The first that applies."""
    from .ffmpeg import MacAdapter, WindowsAdapter, X11Adapter
    from .wlr import WlrAdapter

    env = os.environ if env is None else env
    system = tools.here() if system is None else system
    if system == tools.WINDOWS:
        return WindowsAdapter()
    if system == tools.DARWIN:
        return MacAdapter()
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
        return X11Adapter(env)
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
