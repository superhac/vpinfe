"""PinMAME's own answer about a ROM set, from the library VPX ships.

Borrowed, never bundled: the library is located from the launcher the user
already configured, which ties it to the right install on the machine that
launches - the play host. A machine without VPX simply reports the audit
unavailable, through the same availability predicate as everything else.

The lookup runs in a subprocess (see pinmame_worker) and the answer is cached
against the roms folder's mtime, because loading the library costs real time
and a folder that has not changed gives the same audit.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
from pathlib import Path

logger = logging.getLogger("vpinfe.common.host.pinmame_catalog")

ENV_OVERRIDE = "VPINFE_LIBPINMAME"
WORKER_TIMEOUT_SECONDS = 20.0

_cache: dict[tuple, dict] = {}


def _candidate_dirs(vpx_bin_path: str) -> list[Path]:
    """Where the library plausibly lives, derived from the configured launcher."""
    binary = Path(vpx_bin_path)
    vpx_dir = binary.parent
    dirs = [vpx_dir, vpx_dir / "libs", vpx_dir / "plugins" / "pinmame"]
    # macOS app bundle: .../Contents/MacOS/<binary> with Frameworks beside MacOS.
    if vpx_dir.name == "MacOS" and vpx_dir.parent.name == "Contents":
        dirs.insert(0, vpx_dir.parent / "Frameworks")
        dirs.append(vpx_dir.parent / "PlugIns" / "pinmame")
    return dirs


def find_library(vpx_bin_path: str) -> Path | None:
    """The shipped libpinmame, or None. Never raises."""
    override = os.environ.get(ENV_OVERRIDE, "").strip()
    if override:
        path = Path(override)
        return path if path.is_file() else None
    if not (vpx_bin_path or "").strip():
        return None

    patterns = ("libpinmame*.dylib", "libpinmame*.so*", "libpinmame*.dll",
                "pinmame*.dll")
    for directory in _candidate_dirs(vpx_bin_path):
        try:
            for pattern in patterns:
                hits = sorted(directory.glob(pattern))
                if hits:
                    return hits[0]
        except OSError:
            continue
    return None


def availability(vpx_bin_path: str) -> tuple[bool, str | None]:
    """For discovery: can this instance audit ROM sets at all?"""
    if not (vpx_bin_path or "").strip():
        return False, ("No launcher configured, so there is no VPX install "
                       "to borrow libpinmame from.")
    if find_library(vpx_bin_path) is None:
        return False, "libpinmame not found in the configured VPX install."
    return True, None


def _roms_dir_stamp(roms_dir: str) -> float:
    try:
        return os.stat(roms_dir).st_mtime
    except OSError:
        return 0.0


def lookup(vpx_bin_path: str, roms_dir: str, set_name: str) -> dict | None:
    """The catalog entry and audit for one set, or None when the audit cannot run.

    None means "no answer", never "no rom" - the caller falls back to what it
    knew without the library.
    """
    set_name = (set_name or "").strip()
    if not set_name:
        return None
    library = find_library(vpx_bin_path)
    if library is None:
        return None

    key = (str(library), roms_dir, set_name, _roms_dir_stamp(roms_dir))
    if key in _cache:
        return _cache[key]

    try:
        proc = subprocess.run(
            [sys.executable, "-m", "common.host.pinmame_worker",
             str(library), roms_dir, set_name],
            capture_output=True, text=True, timeout=WORKER_TIMEOUT_SECONDS,
            cwd=str(Path(__file__).resolve().parents[2]),
        )
        payload = json.loads(proc.stdout.strip() or "{}")
    except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError) as exc:
        logger.warning("PinMAME catalog worker failed: %s", exc)
        return None

    if "error" in payload:
        logger.warning("PinMAME catalog worker: %s", payload["error"])
        return None
    entry = payload.get(set_name)
    if entry is not None:
        _cache[key] = entry
    return entry


def clear_cache() -> None:
    """For tests."""
    _cache.clear()
