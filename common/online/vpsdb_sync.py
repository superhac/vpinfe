"""Keeping the local VPSdb copy current, and knowing when it is due.

Everything that reads the catalog reads a file: matching, the release list, what a kind
is offered from, whether a link is a download. `load_vpsdb` opens `vpsdb.json` and
returns it, so all of those are exactly as fresh as the last download - and until this
existed the only thing that downloaded was a Manager UI page nobody has to open.

The check is cheap and the download is not: `lastUpdate.json` is one line, and the
catalog is about 7 MB. So the schedule governs how often the *question* is asked; the
answer only costs bandwidth when it has changed.
"""

from __future__ import annotations

import logging
import threading
from datetime import timedelta

from common import timestamps
from common.config_access import cfg_get

logger = logging.getLogger("vpinfe.common.vpsdb_sync")

SECTION = "vpsdb"
NEVER = "never"

# How long an answer stays good. `never` is absent rather than zero: it is not a very
# long interval, it is a decision not to ask.
EVERY = {
    "daily": timedelta(days=1),
    "weekly": timedelta(weeks=1),
    "monthly": timedelta(days=30),
}


def schedule(config) -> str:
    return (cfg_get(config, SECTION, "refresh", "daily") or "daily").strip().lower()


def checked_at(config) -> str:
    """When the catalog was last asked, ISO 8601 UTC, or "" if it never has been."""
    return (cfg_get(config, SECTION, "checked", "") or "").strip()


def due(config, now: float | None = None) -> bool:
    """Whether a check is owed.

    Never checked counts as due whatever the schedule, short of `never`: a fresh install
    holding no catalog at all should not wait a day to fetch one.
    """
    wanted = schedule(config)
    if wanted == NEVER or wanted not in EVERY:
        return False
    was = timestamps.iso_to_epoch(checked_at(config))
    if was is None:
        return True
    moment = timestamps.iso_to_epoch(timestamps.utc_now_iso()) if now is None else now
    return (moment or 0) - was >= EVERY[wanted].total_seconds()


def stamp(config) -> None:
    """Record that the question was asked. Written whether or not anything came back:
    a catalog that cannot be reached must not be re-asked on every draw.

    Saved here, not left to the caller. `cfg_set` only touches the parser - the cache
    beside this does its own `save()` for the same reason, and a stamp that lived in
    memory made every start look like a first start.
    """
    from common.config_access import cfg_set

    cfg_set(config, SECTION, "checked", timestamps.utc_now_iso())
    save = getattr(config, "save", None)
    if callable(save):
        save()


def sync(config, force: bool = False) -> dict:
    """Ask the catalog whether it has changed, and take it if it has.

    Returns what happened rather than a bool, because "checked and it was already
    current" and "not due yet" are different answers and a surface says them
    differently.
    """
    from common.games.game_service import ensure_vpsdb_downloaded

    if not force and not due(config):
        return {"checked": False, "reason": "not due", "at": checked_at(config)}
    before = (cfg_get(config, SECTION, "last", "") or "").strip()
    ok = ensure_vpsdb_downloaded()
    stamp(config)
    after = (cfg_get(config, SECTION, "last", "") or "").strip()
    if not ok:
        logger.warning("VPSdb sync could not read the catalog")
    return {"checked": True, "ok": bool(ok), "changed": bool(after and after != before),
            "version": after, "at": checked_at(config)}


# How often the runner wakes to ask whether a check is due. Not the schedule - an install
# left running for a week has to notice its daily check coming round, and a process
# that only checked at startup would never fire on the machine that never restarts.
_WAKE_SECONDS = 60 * 60


def start_watch(config, shutdown: threading.Event | None = None) -> threading.Thread:
    """Keep the catalog current in the background, for as long as this process runs.

    A daemon thread rather than a job: nothing is waiting on it, it has no progress
    worth reporting, and it must never hold up a shutdown. A failure is logged and the
    next wake tries again, because the catalog being unreachable is a normal Tuesday.
    """
    stop = shutdown or threading.Event()

    def run() -> None:
        while not stop.is_set():
            try:
                if due(config):
                    result = sync(config)
                    if result.get("changed"):
                        logger.info("VPSdb updated to %s", result.get("version") or "?")
            except Exception:
                logger.warning("VPSdb check failed; will try again", exc_info=True)
            stop.wait(_WAKE_SECONDS)

    thread = threading.Thread(target=run, name="vpsdb-sync", daemon=True)
    thread.start()
    return thread
