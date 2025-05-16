# logger.py
import logging
import sys
import io

_logger = None
_logger_name = "AppLogger"

def ensure_utf8_stdout():
    if sys.stdout.encoding.lower() != "utf-8":
        return io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    return sys.stdout

def create_formatter():
    return logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

def _create_console_handler(level, formatter):
    """Returns a StreamHandler to UTF-8 stdout with the given level and formatter."""
    handler = logging.StreamHandler(ensure_utf8_stdout())
    handler.setLevel(level)
    handler.setFormatter(formatter)
    return handler

def _create_file_handler(level, formatter, filename):
    """Return a FileHandler with UTF-8 encoding, given level, formatter, and filename."""
    handler = logging.FileHandler(filename, encoding='utf-8')
    handler.setLevel(level)
    handler.setFormatter(formatter)
    return handler

def init_logger(name="AppLogger"):
    global _logger, _logger_name
    _logger_name = name
    _logger = logging.getLogger(_logger_name)
    _logger.setLevel(logging.INFO)  # Safe default
    _logger.addHandler(_create_console_handler(logging.INFO, create_formatter()))
    _logger.propagate = False  # Prevent double logging
    return _logger

def update_logger_config(config):
    global _logger, _logger_name
    if _logger is None:
        raise RuntimeError("Logger not initialized. Call init_logger() first.")

    # Clear old handlers
    _logger.handlers.clear()

    DEFAULT_CONFIG = {
        "level": "INFO",
        "file": None,
        "console": True,
    }

    cfg = DEFAULT_CONFIG.copy()
    if config:
        cfg.update(config)

    logger = logging.getLogger(_logger_name)

    if not logger.handlers:
        level_name = cfg["level"].upper()
        level = getattr(logging, level_name, logging.DEBUG)
        logger.setLevel(level)

        if cfg["console"]:
            _logger.addHandler(_create_console_handler(level, create_formatter()))

        if cfg["file"]:
            logger.addHandler(_create_file_handler(level, create_formatter(), cfg["file"]))

        logger.propagate = False
        logger.debug(f"Logger config updated with level={level_name}, output={', '.join(filter(None, ['console' if cfg['console'] else '', f'file={cfg['file']}' if cfg['file'] else '']))}")

    _logger = logger
    return _logger


def get_logger():
    if _logger is None:
        raise RuntimeError("Logger not initialized. Call init_logger() first.")
    return _logger
