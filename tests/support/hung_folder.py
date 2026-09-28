"""A folder whose every look blocks, the way a stat on a dead network mount does."""

from __future__ import annotations

import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from unittest import mock

from common.games import locations


@contextmanager
def never_answering(path: str) -> Iterator[mock.MagicMock]:
    """Looks at `path` block until the block ends; every other path is looked at as usual.
    Waits on the way out for the blocked look to finish, so no question is left in flight
    for the next test."""
    release = threading.Event()
    real = locations._look

    def look(raw_path: str) -> locations.LocationState:
        if raw_path == path:
            release.wait()
        return real(raw_path)

    with mock.patch.object(locations, "_look", side_effect=look) as looked:
        try:
            yield looked
        finally:
            release.set()
            deadline = time.monotonic() + 5
            while path in locations._PROBES and time.monotonic() < deadline:
                time.sleep(0.01)
