import atexit
import sys
from pathlib import Path


def _isatty(stream) -> bool:
    try:
        return stream is not None and stream.isatty()
    except Exception:
        return False


class _TeeStream:
    def __init__(self, file, stream):
        self._file = file
        self._stream = stream if _isatty(stream) else None

    def write(self, data):
        if not data:
            return
        self._file.write(data)
        self._file.flush()
        if self._stream:
            self._stream.write(data)
            self._stream.flush()

    def flush(self):
        self._file.flush()
        if self._stream:
            self._stream.flush()

    def isatty(self):
        return _isatty(self._stream)


def setup_file_log(log_path: Path) -> None:
    """Always log to file and tee to console when attached."""
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_file = open(log_path, "a", encoding="utf-8")

    def _atexit() -> None:
        try:
            sys.stdout.write("\n")
            sys.stdout.flush()
        except Exception:
            pass

    atexit.register(_atexit)

    sys.stdout = _TeeStream(log_file, sys.__stdout__)
    sys.stderr = _TeeStream(log_file, sys.__stderr__)
