"""One way to write a moment in time: ISO 8601, UTC, seconds precision.

    2026-07-30T15:00:18Z

Chosen because it says what it is. An epoch integer is unreadable in a file someone
opens by hand, sorts correctly only as a number, and carries no timezone at all - and
the .info travels with its folder, so "local time" stops meaning anything the moment a
library moves to another machine.

Truncated ISO sorts lexicographically in chronological order, so a stored string is
still directly usable as a sort key.

Still epoch, and not ours alone to change: `User.LastRun` and the VPinPlay runtime store
behind it. Both are specced keys that reach the VPinPlay API verbatim, so converting them
is a migration plus an agreement with that service - see INFO-SCHEMA.local.md. epoch_to_iso
is here to read what they wrote.
"""

from __future__ import annotations

from datetime import UTC, datetime


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def epoch_to_iso(value) -> str:
    """An epoch integer as ISO, or "" if it is not one. For reading fields written
    before this was the standard."""
    try:
        stamp = datetime.fromtimestamp(int(value), UTC)
    except (TypeError, ValueError, OSError, OverflowError):
        return ""
    return stamp.isoformat(timespec="seconds").replace("+00:00", "Z")
