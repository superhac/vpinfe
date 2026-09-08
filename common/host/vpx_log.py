"""Finding VPX's own log file, and optionally clearing it before a session."""

from __future__ import annotations

import logging
import os
from pathlib import Path


def _wanted(value) -> bool:
    """A launcher's stored value, which a hand-edited file may hold as a string."""
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in ("1", "true", "yes", "on")


logger = logging.getLogger("vpinfe.common.host.vpx_log")

VPINBALL_LOG_FILENAME = "vpinball.log"


def resolve_vpinball_log_path(vpx_ini_path: str) -> Path | None:
    vpx_ini_path = (vpx_ini_path or "").strip()
    if not vpx_ini_path:
        return None
    return Path(os.path.expanduser(vpx_ini_path)).parent / VPINBALL_LOG_FILENAME


def delete_vpinball_log_on_start_if_configured(delete_on_start, ini_path: str) -> Path | None:
    """Clear Visual Pinball's log before a launch, if the launcher asks for it.

    Takes the two values rather than a settings object: which launcher is about to run
    decides both of them now, and a launcher is not a config section.
    """
    if not _wanted(delete_on_start):
        return None

    log_path = resolve_vpinball_log_path(ini_path)
    if log_path is None:
        logger.warning("Skipping VPinball log delete: this launcher names no ini file")
        return None

    try:
        log_path.unlink()
    except FileNotFoundError:
        logger.info("VPinball log already missing before launch: %s", log_path)
    except Exception:
        logger.exception("Failed to delete VPinball log before launch: %s", log_path)
    else:
        logger.info("Deleted VPinball log before launch: %s", log_path)

    return log_path
