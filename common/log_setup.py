"""One logger tree, configured once, written to a file that cannot grow forever."""

from __future__ import annotations

import logging
import logging.handlers
import os
import re
import sys
from pathlib import Path

DEFAULT_LOG_FILE_NAME = "vpinfe.log"
DEFAULT_LOG_LEVEL = "INFO"
# Rotate rather than grow without bound: a cab can run for days, and the Logs page
# reads the whole file. Keeping backups also means restarting to reproduce a problem
# no longer destroys the log of the run that showed it.
LOG_MAX_BYTES = 2 * 1024 * 1024
LOG_BACKUP_COUNT = 3
_CONFIGURED = False
_FILE_LOG_INITIALIZED = False
_INCLUDE_THIRD_PARTY = False
_INCLUDE_WINDOWS = False
_THIRD_PARTY_LOGGERS = (
    "asyncio",
    "multipart",
    "nicegui",
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


def _parse_level_and_flags(value: str | None) -> tuple[int, bool, bool]:
    if not value:
        return logging.INFO, False, False

    include_third_party = False
    include_windows = False
    level_token = None
    tokens = [token.strip().lower() for token in re.split(r"[|,]", str(value)) if token.strip()]

    for token in tokens:
        if token == "thirdparty":
            include_third_party = True
            continue
        if token == "windows":
            include_windows = True
            continue
        level_token = token

    return _resolve_level(level_token), include_third_party, include_windows


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


class _WindowsFilter(logging.Filter):
    def __init__(self, include_windows: bool):
        super().__init__()
        self.include_windows = include_windows

    def filter(self, record: logging.LogRecord) -> bool:
        if "windows" not in record.name:
            return True
        if self.include_windows:
            return True
        return record.levelno >= logging.WARNING


def _normalize_third_party_loggers() -> None:
    for name in _THIRD_PARTY_LOGGERS:
        logger = logging.getLogger(name)
        logger.handlers.clear()
        logger.setLevel(logging.NOTSET)
        logger.propagate = True


def configure_logging(config_dir: Path, ini_config=None, enable_file: bool = True) -> Path:
    global _CONFIGURED, _FILE_LOG_INITIALIZED, _INCLUDE_THIRD_PARTY, _INCLUDE_WINDOWS

    config_dir = Path(config_dir)
    config_dir.mkdir(parents=True, exist_ok=True)

    log_level = DEFAULT_LOG_LEVEL
    terminal_enabled = True
    file_enabled = enable_file
    log_path = config_dir / DEFAULT_LOG_FILE_NAME

    if ini_config is not None:
        from common.config_access import cfg_get

        log_level = cfg_get(ini_config, "logger", "level", DEFAULT_LOG_LEVEL)
        # Through cfg_get rather than off the section directly: the key was `console`
        # before the web UI took that word, and logging is configured early enough that
        # it cannot assume the file has been migrated yet.
        terminal_enabled = _coerce_bool(
            cfg_get(ini_config, "logger", "terminal") or None, True)

    resolved_level, include_third_party, include_windows = _parse_level_and_flags(log_level)
    _INCLUDE_THIRD_PARTY = include_third_party
    _INCLUDE_WINDOWS = include_windows

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

    if terminal_enabled:
        terminal_handler = logging.StreamHandler(sys.stdout)
        terminal_handler.setFormatter(formatter)
        terminal_handler.addFilter(_ThirdPartyFilter(include_third_party))
        terminal_handler.addFilter(_WindowsFilter(include_windows))
        root_logger.addHandler(terminal_handler)

    if file_enabled:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.handlers.RotatingFileHandler(
            log_path,
            maxBytes=LOG_MAX_BYTES,
            backupCount=LOG_BACKUP_COUNT,
            encoding="utf-8",
        )
        if not _FILE_LOG_INITIALIZED and log_path.exists() and log_path.stat().st_size:
            # Start each run in a fresh file, with the previous run kept as a backup.
            file_handler.doRollover()
        file_handler.setFormatter(formatter)
        file_handler.addFilter(_ThirdPartyFilter(include_third_party))
        file_handler.addFilter(_WindowsFilter(include_windows))
        root_logger.addHandler(file_handler)
        _FILE_LOG_INITIALIZED = True

    _normalize_third_party_loggers()

    _CONFIGURED = True
    return log_path


def is_configured() -> bool:
    return _CONFIGURED


def include_thirdparty_logs() -> bool:
    return _INCLUDE_THIRD_PARTY


def include_windows_logs() -> bool:
    return _INCLUDE_WINDOWS


def log_file() -> Path | None:
    """Where the log is being written, asked of the handler doing it.

    Rebuilding the path from the config dir would name a file nothing is writing to on
    an install started with file logging off, and would go stale the moment the handler
    rolls over to a name of its own choosing.
    """
    for handler in logging.getLogger().handlers:
        written = getattr(handler, "baseFilename", "")
        if written:
            return Path(written)
    return None


# `%(asctime)s %(levelname)s [%(name)s] %(message)s`, which is what a record starts with.
# Anything not matching is a continuation - a traceback is a dozen of them - and belongs
# to the record above it rather than being a line in its own right.
_RECORD = re.compile(r"^(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d) (\w+) \[([^\]]*)\] (.*)$")

# How far back to read. A rotated log is 2MB and nobody reads it whole through a UI; a
# tail is what the question "what just happened" actually wants.
TAIL_BYTES = 512 * 1024


def read_log(limit: int = 200, level: str = "", contains: str = "") -> list[dict]:
    """The most recent records, oldest first.

    Records rather than lines. A traceback is one thing that happened, and splitting it
    into fourteen rows both buries the message that caused it and makes a level filter
    drop the half that carries the reason.
    """
    path = log_file()
    if path is None or not path.exists():
        return []
    try:
        with open(path, "rb") as handle:
            handle.seek(0, os.SEEK_END)
            handle.seek(max(0, handle.tell() - TAIL_BYTES))
            text = handle.read().decode("utf-8", "replace")
    except OSError:
        return []

    records: list[dict] = []
    for line in text.splitlines():
        found = _RECORD.match(line)
        if found is None:
            # Dropped rather than kept when it is the first thing in the window: it is
            # the tail of a record whose head was cut off by the seek.
            if records:
                records[-1]["message"] += "\n" + line
            continue
        when, name, source, message = found.groups()
        records.append({"when": when, "level": name, "logger": source,
                        "message": message})

    wanted = (level or "").strip().upper()
    if wanted:
        records = [r for r in records if r["level"] == wanted]
    needle = (contains or "").strip().lower()
    if needle:
        records = [r for r in records
                   if needle in r["message"].lower() or needle in r["logger"].lower()]
    return records[-max(1, int(limit)):]
