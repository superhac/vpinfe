"""What this machine is doing, over the wire.

Live readings only. The static facts about a machine - its host, its OS, the browser it
runs - are a device's to report, and answering them here as well would be two homes for
one thing.

Reading takes a sample, so a caller polling this is what fills the session's history.
Nothing samples on a timer of its own: a machine nobody is looking at does not need a
record of having been idle.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Query

from common.host import metrics

from . import scopes
from .auth import requires

logger = logging.getLogger("vpinfe.httpapi.metrics")

router = APIRouter(prefix="/metrics", tags=["metrics"])


def _watched() -> list[str]:
    """The paths worth reporting free space for: where the library lives, and where
    VPinFE keeps its own files. Two rather than every mount, because those are the two
    that fill up and stop something working."""
    from common.config_access import SettingsConfig
    from common.paths import CONFIG_DIR, get_ini_config

    found = []
    try:
        settings = SettingsConfig.from_config(get_ini_config())
        if settings.game_root_dir.strip():
            found.append(settings.game_root_dir.strip())
    except Exception:  # noqa: BLE001 - an unreadable config is not a metrics failure
        logger.debug("Could not read the library path for metrics", exc_info=True)
    found.append(str(CONFIG_DIR))
    # Ordered, de-duplicated: a library kept inside the config directory is one path.
    return list(dict.fromkeys(found))


@router.get("/gpu", summary="What the graphics cards are doing",
            dependencies=[requires(scopes.SYSTEM_READ)])
def read_gpu() -> dict[str, Any]:
    """Its own call because it shells out to nvtop. A page not showing GPUs should not
    pay for one on every tick, and where nvtop is missing this says so rather than
    answering as though the machine has no cards."""
    found = metrics.gpu()
    return {**found, "supported": metrics.gpu_supported(),
            "fields": [{"key": key, "label": label}
                       for key, label in metrics.GPU_FIELDS]}


@router.get("", summary="What this machine is doing now",
            dependencies=[requires(scopes.SYSTEM_READ)])
def read(history_seconds: float = Query(0, ge=0)) -> dict[str, Any]:
    """The current reading, and as much of this session as was asked for.

    `history_seconds` of 0 means none rather than all: a caller showing a number wants
    one sample, and sending an hour of them to draw a single figure is a page load spent
    on data nobody drew.
    """
    now = metrics.sample(_watched())
    return {"now": now,
            "history": metrics.history(history_seconds) if history_seconds else [],
            "kept_seconds": metrics.HISTORY}
