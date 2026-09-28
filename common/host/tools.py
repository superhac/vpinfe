"""The Tools registry: programs on this device that VPinFE runs but neither ships nor plays
tables with.

Each Tool is discovered first. Its setting is the override, for where discovery finds
nothing or picks the wrong one, and a setting whose program does not run is passed over
rather than trusted.

Every program is run as argv, never through a shell, with a timeout and nothing on stdin.
A probe only ever passes an argument that makes the program describe itself and exit.
"""

from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
import sys
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any

from common.i18n import t
from common.launcher_path import resolve_launcher_path

from . import vpinos

logger = logging.getLogger("vpinfe.common.host.tools")

LINUX = "linux"
DARWIN = "darwin"
WINDOWS = "windows"
# A key in `Tool.hint` only: VPinOS is Linux everywhere else.
VPINOS = vpinos.ID

# Long enough for a first run the operating system scans before starting it.
TIMEOUT = 10


class State(StrEnum):
    FOUND = "found"
    MISSING = "missing"
    UNUSABLE = "unusable"
    NOT_HERE = "not_here"


# Who can put it right: a person, or nobody. VPinFE itself, with consent, is `auto`.
FIX_USER = "user"
FIX_NONE = "none"

TIMED_OUT = "tools.unusable.timed_out"
DID_NOT_START = "tools.unusable.did_not_start"
FAILED = "tools.unusable.failed"


@dataclass(frozen=True)
class Probe:
    works: bool
    # For a person to read. Nothing is gated on it.
    version: str = ""
    # What it can do, by kind: `can["encoders"]` holds the names of ffmpeg's encoders.
    can: Mapping[str, frozenset[str]] = field(default_factory=dict)
    # A catalog key, where it does not work.
    reason: str = ""

    def has(self, kind: str, name: str) -> bool:
        return name in self.can.get(kind, frozenset())


@dataclass(frozen=True)
class Tool:
    id: str
    option: str
    # Its product name, for a sentence. Not translated.
    name: str
    # Executables to look for, by platform, most wanted first. No entry: not here.
    names: Mapping[str, tuple[str, ...]]
    probe: Callable[[Path], Probe]
    # A catalog key by platform, taking `tool`, `setting` and `section`.
    hint: Mapping[str, str]
    # Folders of its own to look in beyond PATH, by platform. `${VAR}` is expanded.
    places: Mapping[str, tuple[str, ...]] = field(default_factory=dict)

    @property
    def section(self) -> str:
        return self.option.split(".", 1)[0]

    @property
    def key(self) -> str:
        return self.option.split(".", 1)[1]


@dataclass(frozen=True)
class Found:
    tool: Tool
    state: State
    path: Path | None = None
    probe: Probe | None = None
    # From the setting, as against discovered.
    set_here: bool = False


def here() -> str:
    if sys.platform.startswith("win"):
        return WINDOWS
    if sys.platform == "darwin":
        return DARWIN
    return LINUX


# Where a program is installed that a frontend or a service started with a short PATH
# does not look.
_PLACES: dict[str, tuple[str, ...]] = {
    DARWIN: ("/opt/homebrew/bin", "/usr/local/bin"),
    LINUX: ("/usr/local/bin",),
}


def resolve(tool: Tool, configured: str | None = None) -> Found:
    """The program this device would run as `tool`. `configured` stands in for the
    setting's value."""
    names = tool.names.get(here(), ())
    if not names:
        return Found(tool, State.NOT_HERE)
    setting = (_configured(tool) if configured is None else configured).strip()
    refused: list[Found] = []
    if setting and (path := _executable(setting)) is not None:
        found = Found(tool, State.FOUND, path, probed(tool, path), set_here=True)
        if found.probe is not None and found.probe.works:
            return found
        refused.append(found)
    for path in _candidates(tool, names):
        found = Found(tool, State.FOUND, path, probed(tool, path))
        if found.probe is not None and found.probe.works:
            return found
        refused.append(found)
    if refused:
        first = refused[0]
        return Found(tool, State.UNUSABLE, first.path, first.probe, first.set_here)
    return Found(tool, State.MISSING)


def _configured(tool: Tool) -> str:
    from common.paths import get_ini_config

    return str(get_ini_config().value(tool.section, tool.key) or "")


def _executable(value: str) -> Path | None:
    found = shutil.which(str(resolve_launcher_path(value)))
    return Path(found) if found else None


def _candidates(tool: Tool, names: tuple[str, ...]) -> list[Path]:
    """Every copy of each name, on PATH and then in the places PATH misses. The order of
    `names` wins over where a copy is."""
    places = [os.path.expandvars(place) for place in
              (*tool.places.get(here(), ()), *_PLACES.get(here(), ()))]
    seen: set[str] = set()
    out: list[Path] = []
    for name in names:
        for where in (None, *places):
            found = shutil.which(name, path=where)
            if found and (real := os.path.realpath(found)) not in seen:
                seen.add(real)
                out.append(Path(found))
    return out


# By tool, path and the file's identity, so a program replaced in place is asked again.
# Only what worked is kept: a failure can be something around the file that gets fixed.
_probes: dict[tuple[str, str, int, int], Probe] = {}


def probed(tool: Tool, path: Path) -> Probe:
    try:
        held = path.stat()
    except OSError:
        return Probe(False, reason=DID_NOT_START)
    key = (tool.id, str(path), held.st_mtime_ns, held.st_size)
    if (known := _probes.get(key)) is not None:
        return known
    answer = tool.probe(path)
    if answer.works:
        _probes[key] = answer
    else:
        logger.info("%s at %s is not usable: %s", tool.name, path, answer.reason)
    return answer


class _FailedError(Exception):
    """It ran, and exited with something other than 0."""


def ask(path: Path, *args: str) -> str:
    """What it printed on both streams. Raises `_FailedError`, `OSError` where it cannot
    start and `subprocess.TimeoutExpired` where it does not finish."""
    done = subprocess.run(
        [str(path), *args], capture_output=True, text=True, errors="replace",
        stdin=subprocess.DEVNULL, timeout=TIMEOUT, check=False,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if done.returncode != 0:
        raise _FailedError(done.returncode)
    return (done.stdout or "") + (done.stderr or "")


def probing(asks: Callable[[Path], Probe]) -> Callable[[Path], Probe]:
    """`asks` as a probe: what `ask` raises is an answer, not an exception."""
    def probe(path: Path) -> Probe:
        try:
            return asks(path)
        except subprocess.TimeoutExpired:
            return Probe(False, reason=TIMED_OUT)
        except OSError:
            return Probe(False, reason=DID_NOT_START)
        except _FailedError:
            return Probe(False, reason=FAILED)
    return probe


_VERSION = re.compile(r"\d+\.\d+(?:\.\d+)*")


def version_in(said: str) -> str:
    """The first dotted number on the first line that says anything, or ""."""
    first = next((line for line in said.splitlines() if line.strip()), "")
    found = _VERSION.search(first)
    return found.group(0) if found else ""


# --- RAR --------------------------------------------------------------------------

# By a word in the program's name, the rarfile backend it is: rarfile names each by the
# prefix of its `<PREFIX>_TOOL` and `<PREFIX>_CONFIG`. `7zz` before `7z`, which it holds.
_RAR_BACKENDS = (("unrar", "UNRAR"), ("unar", "UNAR"), ("7zz", "SEVENZIP2"),
                 ("7z", "SEVENZIP"), ("bsdtar", "BSDTAR"))


def rar_backend(path: Path) -> str:
    """Which rarfile backend a RAR tool is. A name it does not know is taken as unrar."""
    stem = path.stem.lower()
    return next((backend for word, backend in _RAR_BACKENDS if word in stem), "UNRAR")


@probing
def _rar(path: Path) -> Probe:
    """The check rarfile itself runs before it uses one."""
    try:
        import rarfile
    except ImportError:
        return Probe(False, reason=DID_NOT_START)
    check = getattr(rarfile, f"{rar_backend(path)}_CONFIG")["check_cmd"][1:]
    return Probe(True, version_in(ask(path, *check)))


_RAR_NAMES = ("unrar", "unar", "7z", "7zz", "bsdtar")

RAR = Tool(
    id="rar",
    option="tools.rar_path",
    name="unar",
    names={LINUX: _RAR_NAMES, DARWIN: _RAR_NAMES, WINDOWS: ("unrar", "7z")},
    probe=_rar,
    hint={LINUX: "tools.rar.hint.linux", VPINOS: "tools.hint.vpinos",
          DARWIN: "tools.rar.hint.darwin", WINDOWS: "tools.rar.hint.windows"},
    places={WINDOWS: ("${ProgramFiles}/WinRAR", "${ProgramFiles}/7-Zip")},
)


# --- recording ----------------------------------------------------------------------

ENCODERS = "encoders"
INPUTS = "inputs"
OPTIONS = "options"

# ` V....D libx264   libx264 H.264 ...`: what it encodes, five flags, then the name.
_ENCODER = re.compile(r"^ [VAS][A-Z.]{5} +([\w-]+) ", re.MULTILINE)
# ` D  avfoundation   AVFoundation input device`: D where it can be read from.
_INPUT_DEVICE = re.compile(r"^ D[E. ] +(\w+) ", re.MULTILINE)


@probing
def _ffmpeg(path: Path) -> Probe:
    version = version_in(ask(path, "-hide_banner", "-version"))
    return Probe(True, version, {
        ENCODERS: frozenset(_ENCODER.findall(ask(path, "-hide_banner", "-encoders"))),
        INPUTS: frozenset(_INPUT_DEVICE.findall(ask(path, "-hide_banner", "-devices"))),
    })


# An option as a program's help lists it: `-o`, `--no-damage`.
_OPTION = re.compile(r"(?<![\w-])(--?[A-Za-z][\w-]*)")


def _described(help_flag: str) -> Callable[[Path], Probe]:
    """A probe that reads what a program can do off the options its help lists."""
    @probing
    def probe(path: Path) -> Probe:
        options = frozenset(_OPTION.findall(ask(path, help_flag)))
        if not options:
            raise _FailedError(0)
        version = version_in(ask(path, "--version")) if "--version" in options else ""
        return Probe(True, version, {OPTIONS: options})
    return probe


_ON_LINUX_ONLY = {LINUX: "tools.hint.linux", VPINOS: "tools.hint.vpinos"}

FFMPEG = Tool(
    id="ffmpeg",
    option="tools.ffmpeg_path",
    name="FFmpeg",
    names={LINUX: ("ffmpeg",), DARWIN: ("ffmpeg",), WINDOWS: ("ffmpeg",)},
    probe=_ffmpeg,
    hint={**_ON_LINUX_ONLY, DARWIN: "tools.ffmpeg.hint.darwin",
          WINDOWS: "tools.ffmpeg.hint.windows"},
)

GRIM = Tool(
    id="grim",
    option="tools.grim_path",
    name="grim",
    names={LINUX: ("grim",)},
    probe=_described("-h"),
    hint=_ON_LINUX_ONLY,
)

WF_RECORDER = Tool(
    id="wf_recorder",
    option="tools.wf_recorder_path",
    name="wf-recorder",
    names={LINUX: ("wf-recorder",)},
    probe=_described("-h"),
    hint=_ON_LINUX_ONLY,
)

TOOLS: tuple[Tool, ...] = (RAR, FFMPEG, GRIM, WF_RECORDER)


# --- what a person reads ------------------------------------------------------------

def remedy(tool: Tool) -> dict[str, Any]:
    """The fix for a missing or unusable one, as a catalog key with its parameters, and
    the setting that points at one instead. `words` renders it."""
    key = tool.hint.get(VPINOS, "") if vpinos.detected() else ""
    return {"key": key or tool.hint.get(here(), ""), "params": {"tool": tool.name},
            "setting": tool.option}


def words(said: Mapping[str, Any]) -> str:
    """A remedy or a reason in this install's language."""
    setting = str(said.get("setting") or "")
    extra = {"setting": t(f"config.{setting}.label"),
             "section": t("console.section.settings")} if setting else {}
    return t(str(said.get("key") or ""), **dict(said.get("params") or {}), **extra)


def hint(tool: Tool) -> str:
    return words(remedy(tool))


def row(found: Found) -> dict[str, Any]:
    """One Tool as the API and the capture preflight report it."""
    tool = found.tool
    stuck = found.state in (State.MISSING, State.UNUSABLE)
    reason = found.probe.reason if found.probe is not None else ""
    return {
        "id": tool.id,
        "name": tool.name,
        "setting": tool.option,
        "state": found.state.value,
        "path": str(found.path or ""),
        "version": found.probe.version if found.probe is not None else "",
        "set_here": found.set_here,
        "reason": ({"key": reason, "params": {}}
                   if found.state is State.UNUSABLE and reason else None),
        "fix": FIX_USER if stuck else FIX_NONE,
        "remedy": remedy(tool) if stuck else None,
    }


def report() -> list[dict[str, Any]]:
    return [row(resolve(tool)) for tool in TOOLS]
