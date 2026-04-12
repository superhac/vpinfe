from __future__ import annotations

import logging
import sys
from pathlib import Path


DEFAULT_LOG_FILE_NAME = "vpinfe.log"
DEFAULT_LOG_LEVEL = "INFO"
_CONFIGURED = False
_FILE_LOG_INITIALIZED = False
_THIRD_PARTY_LOGGERS = (
    "websockets",
    "websockets.client",
    "websockets.server",
    "uvicorn",
    "uvicorn.error",
    "uvicorn.access",
    "python_multipart",
    "python_multipart.multipart",
    "multipart",
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


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


def _normalize_third_party_loggers() -> None:
    for name in _THIRD_PARTY_LOGGERS:
        logger = logging.getLogger(name)
        logger.handlers.clear()
        logger.setLevel(logging.WARNING)
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

    root_logger = logging.getLogger()
    root_logger.setLevel(_resolve_level(log_level))

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
        root_logger.addHandler(console_handler)

    if file_enabled:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(
            log_path,
            mode="w" if not _FILE_LOG_INITIALIZED else "a",
            encoding="utf-8",
        )
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)
        _FILE_LOG_INITIALIZED = True

    _normalize_third_party_loggers()

    _CONFIGURED = True
    return log_path


def is_configured() -> bool:
    return _CONFIGURED
