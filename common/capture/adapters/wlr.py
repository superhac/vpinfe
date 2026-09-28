"""wlroots compositors: sway, and Hyprland, which VPinOS runs. Pictures through `grim`,
video through `wf-recorder`, both over wlr-screencopy."""

from __future__ import annotations

import glob
import json
import os
import socket
import struct
import subprocess
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from common.host import tools

from .. import geometry
from . import Output

# sway's IPC: this magic, then the payload's length and the message type, little-endian.
_MAGIC = b"i3-ipc"
_GET_OUTPUTS = 3

Connect = Callable[[str], socket.socket]


def _unix(path: str) -> socket.socket:
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.settimeout(tools.TIMEOUT)
    try:
        sock.connect(path)
    except OSError:
        sock.close()
        raise
    return sock


def _read(sock: socket.socket, count: int) -> bytes:
    held = b""
    while len(held) < count:
        got = sock.recv(count - len(held))
        if not got:
            raise ConnectionResetError
        held += got
    return held


def ask_sway(sock: socket.socket) -> Any:
    with sock:
        sock.sendall(_MAGIC + struct.pack("<II", 0, _GET_OUTPUTS))
        header = _read(sock, len(_MAGIC) + 8)
        if header[:len(_MAGIC)] != _MAGIC:
            raise ConnectionRefusedError
        length, _ = struct.unpack("<II", header[len(_MAGIC):])
        return json.loads(_read(sock, length))


def ask_hyprland(sock: socket.socket) -> Any:
    """Hyprland answers one request per connection and closes it."""
    with sock:
        sock.sendall(b"j/monitors")
        held = b""
        while got := sock.recv(65536):
            held += got
        return json.loads(held)


def hyprland_socket(env: Mapping[str, str]) -> str:
    """Under the runtime directory since Hyprland 0.40, under /tmp before it."""
    signature = str(env.get("HYPRLAND_INSTANCE_SIGNATURE") or "")
    places = [str(env.get("XDG_RUNTIME_DIR") or ""), "/tmp"]
    paths = [os.path.join(place, "hypr", signature, ".socket.sock")
             for place in places if place]
    return next((path for path in paths if os.path.exists(path)), paths[0])


def sway_outputs(said: Any) -> list[Output]:
    """`rect` is the layout's; `current_mode` is the buffer's, refresh in millihertz."""
    found = []
    for one in said if isinstance(said, list) else []:
        if not isinstance(one, dict) or not one.get("active", True):
            continue
        rect, mode = one.get("rect") or {}, one.get("current_mode") or {}
        found.append(Output(
            name=str(one.get("name") or ""),
            x=int(rect.get("x") or 0), y=int(rect.get("y") or 0),
            width=int(rect.get("width") or 0), height=int(rect.get("height") or 0),
            mode=(int(mode.get("width") or 0), int(mode.get("height") or 0)),
            refresh=int(mode.get("refresh") or 0) / 1000,
            transform=geometry.sway_transform(one.get("transform"))))
    return found


def hyprland_outputs(said: Any) -> list[Output]:
    """`width` and `height` are the mode's, before the transform and the scale."""
    found = []
    for one in said if isinstance(said, list) else []:
        if not isinstance(one, dict) or one.get("disabled"):
            continue
        transform = geometry.hyprland_transform(one.get("transform"))
        mode = (int(one.get("width") or 0), int(one.get("height") or 0))
        scale = float(one.get("scale") or 1) or 1.0
        width, height = transform.size(*mode)
        found.append(Output(
            name=str(one.get("name") or ""),
            x=int(one.get("x") or 0), y=int(one.get("y") or 0),
            width=round(width / scale), height=round(height / scale),
            mode=mode, refresh=float(one.get("refreshRate") or 0),
            transform=transform))
    return found


def render_node() -> str:
    found = sorted(glob.glob("/dev/dri/renderD*"))
    return found[0] if found else ""


# By FFmpeg and render node, for the life of the process.
_encodes: dict[tuple[str, str], bool] = {}


def vaapi_probe(ffmpeg: Path, node: str) -> list[str]:
    """One frame through `h264_vaapi`, to nowhere."""
    return [str(ffmpeg), "-hide_banner", "-loglevel", "error", "-vaapi_device", node,
            "-f", "lavfi", "-i", "color=c=black:s=256x256:d=0.1",
            "-vf", "format=nv12,hwupload", "-frames:v", "1", "-c:v", "h264_vaapi",
            "-f", "null", "-"]


def vaapi_node(ffmpeg: tools.Found, node: str | None = None,
               run: Callable[..., Any] = subprocess.run) -> str:
    """The render node that encodes H.264 in hardware, or "" where none does."""
    if ffmpeg.path is None or ffmpeg.probe is None or not ffmpeg.probe.has(
            tools.ENCODERS, "h264_vaapi"):
        return ""
    node = render_node() if node is None else node
    if not node:
        return ""
    key = (str(ffmpeg.path), node)
    if key not in _encodes:
        try:
            done = run(vaapi_probe(ffmpeg.path, node), capture_output=True,
                       stdin=subprocess.DEVNULL, timeout=tools.TIMEOUT, check=False)
            _encodes[key] = done.returncode == 0
        except (OSError, subprocess.TimeoutExpired):
            _encodes[key] = False
    return node if _encodes[key] else ""


class WlrAdapter:
    id = "wlr"

    def __init__(self, env: Mapping[str, str], connect: Connect = _unix) -> None:
        self.env = env
        self._connect = connect

    @staticmethod
    def applies(env: Mapping[str, str]) -> bool:
        return bool(env.get("WAYLAND_DISPLAY")) and bool(
            env.get("SWAYSOCK") or env.get("HYPRLAND_INSTANCE_SIGNATURE"))

    def requirements(self) -> tuple[tools.Tool, ...]:
        return (tools.FFMPEG, tools.GRIM, tools.WF_RECORDER)

    def outputs(self) -> list[Output]:
        """Raises OSError or ValueError where the compositor does not answer."""
        if self.env.get("SWAYSOCK"):
            return sway_outputs(ask_sway(self._connect(str(self.env["SWAYSOCK"]))))
        return hyprland_outputs(ask_hyprland(self._connect(hyprland_socket(self.env))))

    def at_once(self, ffmpeg: tools.Found) -> bool:
        return bool(self.hardware(ffmpeg))

    def hardware(self, ffmpeg: tools.Found) -> str:
        return vaapi_node(ffmpeg)

    def still(self, found: Mapping[str, tools.Found], output: Output,
              dest: Path) -> list[str]:
        return [str(found[tools.GRIM.id].path), "-o", output.name, str(dest)]

    def record(self, found: Mapping[str, tools.Found], output: Output, dest: Path,
               hardware: str) -> list[str]:
        """Every refresh copied, `-D`, where this wf-recorder has it: a static screen
        otherwise gives one frame and a stop that waits for the next forever. Near
        lossless, since the pipeline encodes it again."""
        recorder = found[tools.WF_RECORDER.id]
        every = recorder.probe is not None and (
            recorder.probe.has(tools.OPTIONS, "-D")
            or recorder.probe.has(tools.OPTIONS, "--no-damage"))
        codec = (["-c", "h264_vaapi", "-d", hardware, "-p", "qp=18"] if hardware
                 else ["-c", "libx264", "-p", "preset=ultrafast", "-p", "crf=18"])
        return [str(recorder.path), *(["-D"] if every else []), "-o", output.name,
                *codec, "-f", str(dest)]

    def still_turn(self, output: Output) -> geometry.Turn:
        """grim draws the output as the screen shows it."""
        return geometry.NONE

    def recording_turn(self, output: Output) -> geometry.Turn:
        """wf-recorder hands over the buffer before the output's transform."""
        return output.transform


def reset_for_tests() -> None:
    _encodes.clear()
