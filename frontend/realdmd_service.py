from __future__ import annotations

import logging
import threading
from pathlib import Path

from common.table_metadata import normalize_meta


logger = logging.getLogger("vpinfe.frontend.realdmd_service")


def get_frontend_dof_event_for_table(table) -> str:
    meta = normalize_meta(getattr(table, "metaConfig", {}))
    user = meta.get("User", {}) if isinstance(meta, dict) else {}
    if not isinstance(user, dict):
        return ""
    return str(user.get("FrontendDOFEvent", "") or "").strip()


def get_realdmd_image_for_table(table) -> Path | None:
    image_path = str(getattr(table, "realDMDImagePath", "") or "").strip()
    if not image_path:
        return None
    path = Path(image_path).expanduser()
    try:
        return path.resolve()
    except Exception:
        return path


class RealDmdUpdater:
    def __init__(self, iniconfig, window_name: str | None, show_image_func):
        self._iniconfig = iniconfig
        self._window_name = window_name or "unknown"
        self._show_image = show_image_func
        self._lock = threading.Lock()
        self._event = threading.Event()
        self._image_path: Path | None = None
        self._table_name = ""
        self._thread: threading.Thread | None = None

    def queue_image_update(self, table_name: str, image_path: Path | None) -> None:
        self._ensure_worker()
        with self._lock:
            self._table_name = table_name
            self._image_path = image_path
            self._event.set()

    def _ensure_worker(self) -> None:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._thread = threading.Thread(
                target=self._worker_loop,
                name=f"realdmd-worker-{self._window_name}",
                daemon=True,
            )
            self._thread.start()

    def _worker_loop(self) -> None:
        while True:
            self._event.wait()
            with self._lock:
                image_path = self._image_path
                table_name = self._table_name
                self._event.clear()

            try:
                image_sent = self._show_image(self._iniconfig, image_path)
                logger.debug(
                    "Async real DMD update for %s -> sent=%s image=%s",
                    table_name,
                    image_sent,
                    image_path,
                )
            except Exception:
                logger.exception(
                    "Async real DMD update failed for %s (image=%s)",
                    table_name,
                    image_path,
                )
