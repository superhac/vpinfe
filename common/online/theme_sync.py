"""Reading the theme sources again when the schedule says so."""

from __future__ import annotations

import logging
import threading

from common import timestamps
from common.config_access import cfg_get, cfg_set
from common.config_store import ConfigStore
from common.online.vpsdb_sync import EVERY

logger = logging.getLogger("vpinfe.common.online.theme_sync")

SECTION = "themes"
_WAKE_SECONDS = 60 * 60


def checked_at(config: ConfigStore) -> str:
    return (cfg_get(config, SECTION, "last_read", "") or "").strip()


def due(config: ConfigStore, now: float | None = None) -> bool:
    wanted = (cfg_get(config, SECTION, "refresh", "daily") or "daily").strip().lower()
    if wanted not in EVERY:
        return False
    was = timestamps.iso_to_epoch(checked_at(config))
    if was is None:
        return True
    moment = timestamps.iso_to_epoch(timestamps.utc_now_iso()) if now is None else now
    return (moment or 0) - was >= EVERY[wanted].total_seconds()


def stamp(config: ConfigStore) -> None:
    cfg_set(config, SECTION, "last_read", timestamps.utc_now_iso())
    save = getattr(config, "save", None)
    if callable(save):
        save()


def start_watch(config: ConfigStore, shutdown: threading.Event | None = None) -> threading.Thread:
    """Read the sources whenever a read is due, for as long as this process runs."""
    stop = shutdown or threading.Event()

    def run() -> None:
        from common.online import theme_ops

        while not stop.is_set():
            try:
                if due(config):
                    theme_ops.listing(refresh=True)
            except Exception:
                logger.warning("Theme sources could not be read; will try again",
                               exc_info=True)
            stop.wait(_WAKE_SECONDS)

    thread = threading.Thread(target=run, name="theme-sync", daemon=True)
    thread.start()
    return thread
