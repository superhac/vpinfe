from __future__ import annotations

import logging
import re
import sys
from pathlib import Path


DEFAULT_LOG_FILE_NAME = "vpinfe.log"
DEFAULT_LOG_LEVEL = "INFO"
_CONFIGURED = False
_FILE_LOG_INITIALIZED = False
_THIRD_PARTY_LOGGERS = (
    "asyncio",
    "multipart",
    "PIL",
    "PIL.Image",
    "PIL.PngImagePlugin",
    "python_multipart",
    "python_multipart.multipart",
    "urllib3",
    "urllib3.connectionpool",
    "uvicorn",
    "uvicorn.error",
    "uvicorn.access",
    "websockets",
    "websockets.client",
    "websockets.server",
)


def _coerce_bool(value, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if str(value).strip() == "":
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _resolve_level(value: str | None) -> int:
    if not value:
        return logging.INFO
    return getattr(logging, str(value).strip().upper(), logging.INFO)


def _parse_level_and_flags(value: str | None) -> tuple[int, bool]:
    if not value:
        return logging.INFO, False

    include_third_party = False
    level_token = None
    tokens = [token.strip().lower() for token in re.split(r"[|,]", str(value)) if token.strip()]

    for token in tokens:
        if token == "thirdparty":
            include_third_party = True
            continue
        level_token = token

    return _resolve_level(level_token), include_third_party


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


def _is_third_party_logger(logger_name: str) -> bool:
    for name in _THIRD_PARTY_LOGGERS:
        if logger_name == name or logger_name.startswith(f"{name}."):
            return True
    return False


class _ThirdPartyFilter(logging.Filter):
    def __init__(self, include_third_party: bool):
        super().__init__()
        self.include_third_party = include_third_party

    def filter(self, record: logging.LogRecord) -> bool:
        if not _is_third_party_logger(record.name):
            return True
        if self.include_third_party:
            return True
        return record.levelno >= logging.WARNING


def _normalize_third_party_loggers() -> None:
    for name in _THIRD_PARTY_LOGGERS:
        logger = logging.getLogger(name)
        logger.handlers.clear()
        logger.setLevel(logging.NOTSET)
        logger.propagate = True


def configure_logging(config_dir: Path, ini_config=None, enable_file: bool = True) -> Path:
    global _CONFIGURED, _FILE_LOG_INITIALIZED

    config_dir = Path(config_dir)
    config_dir.mkdir(parents=True, exist_ok=True)

    log_level = DEFAULT_LOG_LEVEL
    console_enabled = True
    file_enabled = enable_file
    log_path = config_dir / DEFAULT_LOG_FILE_NAME

    if ini_config is not None:
        logger_cfg = ini_config.config["Logger"]
        log_level = logger_cfg.get("level", DEFAULT_LOG_LEVEL)
        console_enabled = _coerce_bool(logger_cfg.get("console"), True)

    resolved_level, include_third_party = _parse_level_and_flags(log_level)

    root_logger = logging.getLogger()
    root_logger.setLevel(resolved_level)

    for handler in list(root_logger.handlers):
        root_logger.removeHandler(handler)
        try:
            handler.close()
        except Exception:
            pass

    formatter = logging.Formatter(
        fmt="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    if console_enabled:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(formatter)
        console_handler.addFilter(_ThirdPartyFilter(include_third_party))
        root_logger.addHandler(console_handler)

    if file_enabled:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(
            log_path,
            mode="w" if not _FILE_LOG_INITIALIZED else "a",
            encoding="utf-8",
        )
        file_handler.setFormatter(formatter)
        file_handler.addFilter(_ThirdPartyFilter(include_third_party))
        root_logger.addHandler(file_handler)
        _FILE_LOG_INITIALIZED = True

    _normalize_third_party_loggers()

    _CONFIGURED = True
    return log_path


def is_configured() -> bool:
    return _CONFIGURED
