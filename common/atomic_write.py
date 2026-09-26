"""Writing a file so a reader never sees half of one."""

from __future__ import annotations

import contextlib
import os
import tempfile
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import IO


@contextlib.contextmanager
def naming_folder(path: str | Path) -> Iterator[None]:
    """An OSError raised inside that names a file in `path`'s folder, other than `path`
    itself, names the folder instead.

    Wrap only what touches the file staged beside `path`: a failure on another real file
    in the folder, one being unlinked say, would lose that file's name.
    """
    target = os.path.abspath(path)
    folder = os.path.dirname(target)
    try:
        yield
    except OSError as exc:
        if isinstance(exc.filename, (str, bytes, os.PathLike)):
            named = os.path.abspath(os.fsdecode(exc.filename))
            if named != target and os.path.dirname(named) == folder:
                exc.filename = folder
        raise


def write_atomic(path: str | Path, write: Callable[[IO[str]], None]) -> None:
    """Write a file so a reader sees the old one or the new one, never half of one.

    open(path, "w") truncates before writing, and the id backfill rewrites every .info in
    one burst at first launch - the worst moment to be interrupted. `write` is handed the
    open handle.
    """
    directory = os.path.dirname(path) or "."
    with naming_folder(path):
        # Underscores, not the BACKUP_MARKER hyphen: must not read as a restore point.
        handle_fd, tmp = tempfile.mkstemp(dir=directory, prefix=".vpinfe_write_",
                                          suffix=".tmp")
        try:
            with os.fdopen(handle_fd, "w", encoding="utf-8") as handle:
                write(handle)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp, path)
        except BaseException:
            with contextlib.suppress(OSError):
                os.unlink(tmp)
            raise
