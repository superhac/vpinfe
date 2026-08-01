"""Showing a table's art on a real DMD panel.

Nothing here draws anything itself - it resolves which image a table should
show and hands it to libdmdutil on a worker thread, because the panel is slow
enough that the wheel would stutter waiting for it.
"""

from __future__ import annotations

import logging
import threading
from pathlib import Path

from common.config_access import MediaConfig

logger = logging.getLogger("vpinfe.common.host.realdmd")


def get_realdmd_image_for_game(game, iniconfig=None) -> Path | None:
    priority = "color"
    if iniconfig is not None:
        priority = MediaConfig.from_config(iniconfig).realdmd_media_priority

    standard_path = str(getattr(game, "realDMDImagePath", "") or "").strip()
    color_path = str(getattr(game, "realDMDColorImagePath", "") or "").strip()
    candidates = (
        (standard_path, color_path)
        if priority == "standard"
        else (color_path, standard_path)
    )
    image_path = next((candidate for candidate in candidates if candidate), "")
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
        self._game_name = ""
        self._thread: threading.Thread | None = None

    def queue_image_update(self, game_name: str, image_path: Path | None) -> None:
        self._ensure_worker()
        with self._lock:
            self._game_name = game_name
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
            self._process_pending()

    def _process_pending(self) -> None:
        with self._lock:
            image_path = self._image_path
            game_name = self._game_name
            self._event.clear()

        try:
            image_sent = self._show_image(self._iniconfig, image_path)
            logger.debug(
                "Async real DMD update for %s -> sent=%s image=%s",
                game_name,
                image_sent,
                image_path,
            )
        except Exception:
            logger.exception(
                "Async real DMD update failed for %s (image=%s)",
                game_name,
                image_path,
            )
