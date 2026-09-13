"""What this machine is doing right now, and what it has been doing this session.

The live half only. Host, OS, build flavour and the browser a device runs are static
facts and live with the device that reports them - a reading and a fact answer different
questions, and putting both here would be one surface doing two jobs.

**History is a ring in memory and goes with the process.** It answers "is something
climbing?", which is the question a single number cannot, and it costs nothing. Anything
surviving a restart is a storage decision that has not been made, and inventing one here
would be answering it by accident.

`psutil` is optional. Where it is missing the readings say so rather than reporting zero:
a machine that cannot be measured and a machine that is idle are different, and a graph
of zeros is a lie that looks like data.
"""

from __future__ import annotations

import json
import logging
import os
import platform
import shutil
import subprocess
import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:  # optional, and an install without it still runs
    import psutil
except Exception:  # noqa: BLE001 - any import failure means "not measurable"
    psutil = None

logger = logging.getLogger("vpinfe.common.host.metrics")

# Roughly an hour at the 2s cadence a page reads on, which is as far back as a question
# like "did that scan do this?" reaches. Bounded because it is memory, and unbounded
# history in a process that runs for weeks is a leak with a nice name.
HISTORY = 1800


@dataclass
class _Ring:
    """One session's samples, oldest first."""

    points: deque = field(default_factory=lambda: deque(maxlen=HISTORY))

    def add(self, sample: dict[str, Any]) -> None:
        self.points.append(sample)

    def since(self, seconds: float = 0.0) -> list[dict[str, Any]]:
        if not seconds:
            return list(self.points)
        cutoff = time.time() - seconds
        return [one for one in self.points if one["at"] >= cutoff]


_ring = _Ring()


def measurable() -> tuple[bool, str]:
    """Whether this machine can be read at all, and why not when it cannot.

    Offered disabled with the reason rather than hidden: a page that simply omits the
    readings leaves somebody wondering whether the machine is fine or the page is broken.
    """
    if psutil is None:
        return False, ("psutil is not installed, so this machine cannot report its "
                       "processor or memory.")
    return True, ""


def read(paths=()) -> dict[str, Any]:
    """One reading. Cheap enough to call on a timer.

    `cpu_percent` is asked without an interval, so it is the load since the previous
    call rather than a blocking sample - which is what makes this safe on a 2s timer and
    why the first reading after startup is not meaningful.
    """
    ok, reason = measurable()
    sample: dict[str, Any] = {
        "at": time.time(),
        "measurable": ok,
        "reason": reason,
        "cpu_percent": None,
        "memory_total": None,
        "memory_used": None,
        "memory_percent": None,
        "load": None,
        "disks": _disks(paths or []),
    }
    if not ok:
        return sample

    sample["cpu_percent"] = psutil.cpu_percent(interval=None)
    memory = psutil.virtual_memory()
    sample["memory_total"] = memory.total
    sample["memory_used"] = memory.total - memory.available
    sample["memory_percent"] = memory.percent
    # Not on Windows, and not an error there - it is a number that platform does not
    # have rather than one we failed to read.
    try:
        sample["load"] = [round(one, 2) for one in os.getloadavg()]
    except (OSError, AttributeError):
        sample["load"] = None
    return sample


# What nvtop reports per card, and what to call each on screen. Declared rather than
# rendered from raw keys: `mem_util` is not a label, and a surface guessing at one is a
# surface that renames a field the day nvtop does.
GPU_FIELDS: tuple[tuple[str, str], ...] = (
    ("gpu_util", "Utilization"),
    ("mem_util", "Memory"),
    ("temp", "Temperature"),
    ("fan_speed", "Fan"),
    ("power_draw", "Power"),
    ("gpu_clock", "GPU clock"),
    ("mem_clock", "Memory clock"),
)


def gpu_supported() -> bool:
    """Where asking is even meaningful. nvtop is a Linux and macOS tool, and offering
    the switch on Windows would be offering something that can only ever fail."""
    return platform.system() in {"Linux", "Darwin"}


def gpu() -> dict[str, Any]:
    """Every card nvtop can see, or the reason there are none.

    Behind its own call rather than folded into `read`: it shells out, and a page that
    is not showing GPUs should not pay for one every two seconds. Offered disabled with
    the reason where nvtop is missing - decision 15's rule, and "no GPU section" and
    "nvtop is not installed" are different answers.
    """
    if not gpu_supported():
        return {"available": False,
                "reason": f"nvtop does not run on {platform.system()}.", "gpus": []}
    found = shutil.which("nvtop")
    if not found:
        return {"available": False, "reason": "nvtop is not installed.", "gpus": []}

    try:
        done = subprocess.run([found, "-s"], capture_output=True, text=True,
                              timeout=3, check=False)
    except subprocess.TimeoutExpired:
        return {"available": False, "reason": "nvtop timed out.", "gpus": []}
    except Exception as exc:  # noqa: BLE001 - a probe must not take the page with it
        return {"available": False, "reason": f"nvtop failed: {exc}", "gpus": []}

    text = (done.stdout or "").strip()
    if done.returncode != 0 or not text:
        said = (done.stderr or text or "nvtop returned nothing.").strip()
        return {"available": False, "reason": said, "gpus": []}

    try:
        cards = json.loads(text)
    except json.JSONDecodeError as exc:
        return {"available": False, "reason": f"Could not read nvtop: {exc}", "gpus": []}
    if not isinstance(cards, list) or not cards:
        return {"available": False, "reason": "nvtop reported no cards.", "gpus": []}

    # Per card, not aggregated. Two cards averaged is a number describing neither, and a
    # machine with a second card is exactly the machine somebody is looking at this for.
    found_cards = [
        {"id": index, "name": card.get("device_name") or f"GPU {index}",
         **{key: card.get(key) for key, _label in GPU_FIELDS}}
        for index, card in enumerate(cards, start=1) if isinstance(card, dict)]
    if not found_cards:
        return {"available": False, "reason": "nvtop reported nothing usable.",
                "gpus": []}
    return {"available": True, "reason": "", "gpus": found_cards}


def _disks(paths) -> list[dict[str, Any]]:
    """One row per *volume*, not per path.

    Two watched paths on one disk are one answer, and printing it twice says the same
    thing twice - which the rest of this project's UI rules call a badge on every row.
    Keyed on the device id the filesystem reports, so it is the same volume rather than
    the same prefix.
    """
    found: list[dict[str, Any]] = []
    seen: dict[Any, dict[str, Any]] = {}
    for path in paths:
        entry = _disk(path)
        key = entry.pop("device", None)
        if key is not None and key in seen:
            # Named on the row that is already there, so somebody looking for the
            # config directory finds it rather than concluding it is not watched.
            seen[key]["also"].append(entry["path"])
            continue
        entry["also"] = []
        found.append(entry)
        if key is not None:
            seen[key] = entry
    return found


def _disk(path: str) -> dict[str, Any]:
    """One monitored path. Per path rather than per filesystem: a person watches the
    place their tables live, and which device that is on is not the question."""
    entry: dict[str, Any] = {"path": str(path), "total": None, "used": None,
                             "free": None, "percent": None, "error": "", "device": None}
    try:
        found = Path(path).expanduser()
        total, used, free = shutil.disk_usage(found)
        entry["device"] = found.stat().st_dev
    except Exception as exc:  # noqa: BLE001 - a share that has gone is the case this reports
        entry["error"] = str(exc)
        return entry
    entry.update({"total": total, "used": used, "free": free,
                  "percent": (used / total * 100) if total else 0.0})
    return entry


def sample(paths=()) -> dict[str, Any]:
    """Read once and keep it. What a page calls on its timer."""
    found = read(paths)
    if found["measurable"]:
        _ring.add({k: v for k, v in found.items()
                   if k in ("at", "cpu_percent", "memory_percent")})
    return found


def history(seconds: float = 0.0) -> list[dict[str, Any]]:
    """What has been kept this session, oldest first."""
    return _ring.since(seconds)


def reset_for_tests() -> None:
    _ring.points.clear()
