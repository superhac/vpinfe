from __future__ import annotations

import logging
import os
from pathlib import Path

from common.config_access import SettingsConfig


logger = logging.getLogger("vpinfe.common.vpx_log")

VPINBALL_LOG_FILENAME = "vpinball.log"


def resolve_vpinball_log_path(vpx_ini_path: str) -> Path | None:
    vpx_ini_path = (vpx_ini_path or "").strip()
    if not vpx_ini_path:
        return None
    return Path(os.path.expanduser(vpx_ini_path)).parent / VPINBALL_LOG_FILENAME


def delete_vpinball_log_on_start_if_configured(settings: SettingsConfig) -> Path | None:
    if not settings.vpx_log_delete_on_start:
        return None

    log_path = resolve_vpinball_log_path(settings.vpx_ini_path)
    if log_path is None:
        logger.warning("Skipping VPinball log delete: Settings.vpxinipath is not set")
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
