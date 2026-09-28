"""What VPinPlay's players have rated a table, in the shape themes read, and the two
requests an account makes outside a game's sync: whether a candidate id is free, and the
empty send that claims one.

Ratings are answered from VPinPlay's table list, never asked of the service per table. The
shape is the one published themes already read by name, and does not change.
"""

from __future__ import annotations

import threading
from datetime import UTC, datetime
from typing import Any
from urllib.parse import quote

import requests

from . import sync

AVAILABLE_TIMEOUT = 10


def _number(value: Any, fallback: Any = None) -> Any:
    if isinstance(value, bool) or value is None or value == "":
        return fallback
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def _as_text(value: Any) -> str:
    """What a year that is not a number falls back to.

    A string is kept as it came - "1995-06" and "unknown" are both things a catalog has
    said. Anything else is not a year in any reading, and passing it through would leave
    a field that is documented as a number or a string holding neither.
    """
    return value if isinstance(value, str) else ""


def _whole(value: Any) -> int | None:
    """A year as a whole number where it is one.

    The browser produced this and JavaScript has one number type, so 1995 came out of it
    as 1995. Python would send 1995.0 to anything reading the answer over REST, which is
    a different value to a reader that cares.
    """
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value


def normalize(vps_id: str, payload: Any) -> dict | None:
    """The answer, in the shape a theme already reads.

    Every field is coerced rather than trusted: this is somebody else's server, and a
    theme reading `rating.ratingCount.toFixed()` should not be the thing that discovers
    it sent a string.
    """
    if not isinstance(payload, dict):
        return None
    vps = payload.get("vpsdb")
    vps = vps if isinstance(vps, dict) else {}
    year = _whole(_number(vps.get("year"), _as_text(vps.get("year"))))
    count = _number(payload.get("ratingCount"))
    return {
        "vpsId": str(payload.get("vpsId") or vps_id or "").strip(),
        "cumulativeRating": _number(payload.get("cumulativeRating")),
        "ratingCount": 0 if count is None else max(0, int(count)),
        "vpsdb": {
            "name": vps.get("name") if isinstance(vps.get("name"), str) else "",
            "authors": vps.get("authors") if isinstance(vps.get("authors"), list) else [],
            "manufacturer": (vps.get("manufacturer")
                             if isinstance(vps.get("manufacturer"), str) else ""),
            "year": year,
        },
        "fetchedAt": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    }


def from_row(row: dict, read_at: str = "") -> dict | None:
    """One table's answer from a row of VPinPlay's list. A table nobody has rated has no
    rating, where the list says 0."""
    vps_id = str(row.get("vps_id") or "").strip()
    if not vps_id:
        return None
    count = row.get("ratings")
    found = normalize(vps_id, {
        "vpsId": vps_id,
        "cumulativeRating": row.get("average") if count else None,
        "ratingCount": count,
        "vpsdb": {"name": row.get("name"), "authors": row.get("authors"),
                  "manufacturer": row.get("manufacturer"), "year": row.get("year")},
    })
    if found is not None and read_at:
        found["fetchedAt"] = read_at
    return found


class Ratings:
    """Every table's answer from the latest list, by VPS id."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._by_id: dict[str, dict] = {}

    def load(self, rows: Any, read_at: str = "") -> None:
        found = {}
        for row in rows if isinstance(rows, list) else []:
            one = from_row(row, read_at) if isinstance(row, dict) else None
            if one is not None:
                found[one["vpsId"]] = one
        with self._lock:
            self._by_id = found

    def answer(self, vps_id: str) -> dict | None:
        with self._lock:
            held = self._by_id.get(str(vps_id or "").strip())
        return None if held is None else {**held, "vpsdb": dict(held["vpsdb"])}


def check_available(sync_endpoint: str, user_id: str) -> bool:
    """Whether `user_id` is free to choose. Raises `requests.RequestException` where
    VPinPlay could not be asked, which a caller must not read as taken."""
    root = sync_endpoint.removesuffix("/sync")
    url = f"{root}/users/{quote(user_id, safe='')}/available"
    response = requests.get(url, timeout=AVAILABLE_TIMEOUT)
    response.raise_for_status()
    body = response.json()
    return bool(body.get("available")) if isinstance(body, dict) else False


def register(sync_endpoint: str, user_id: str, initials: str, key: str,
             program_version: str) -> dict:
    """Claim `user_id`: an empty send, which VPinPlay reads as registering the pair
    rather than filing any table."""
    payload = sync.envelope(user_id, initials, key, [], program_version, sync.now())
    return sync.send(sync_endpoint, payload, sync.GAME_TIMEOUT)
