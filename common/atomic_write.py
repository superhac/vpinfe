"""Writing a file so a reader never sees half of one."""

from __future__ import annotations

import contextlib
import os
import tempfile


def write_atomic(path, write) -> None:
    """Write a file so a reader sees the old one or the new one, never half of one.

    open(path, "w") truncates before writing, and the id backfill rewrites every .info in
    one burst at first launch - the worst moment to be interrupted. `write` is handed the
    open handle.
    """
    directory = os.path.dirname(path) or "."
    # Underscores, not the BACKUP_MARKER hyphen: must not read as a restore point.
    handle_fd, tmp = tempfile.mkstemp(dir=directory, prefix=".vpinfe_write_", suffix=".tmp")
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
