from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable


ProgressCallback = Callable[[int, int, str], None]
LogCallback = Callable[[str], None]


@dataclass
class JobReporter:
    logger: logging.Logger
    progress_cb: ProgressCallback | None = None
    log_cb: LogCallback | None = None

    def log(self, message: str) -> None:
        self.logger.info(message)
        if self.log_cb:
            self.log_cb(message)

    def progress(self, current: int, total: int, message: str) -> None:
        if not self.progress_cb:
            return
        try:
            self.progress_cb(current, total, message)
        except Exception:
            self.logger.debug("Progress callback failed", exc_info=True)
