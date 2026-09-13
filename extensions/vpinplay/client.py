"""Asking VPinPlay what its players have rated a table.

One call, and it is the only thing this reaches outside for. The shape returned is the
shape themes already read, because they read it today - twelve published ones call for
it by name, and an import that changed the shape would break them all to no purpose.
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime

logger = logging.getLogger(__name__)

# Long enough for a slow answer, short enough that the wheel is not held by one. Core
# calls this off the wheel's thread, so this bounds a background wait rather than a
# player's.
TIMEOUT_SECONDS = 8


def rating_url(endpoint: str, vps_id: str) -> str:
    base = str(endpoint or "").strip().rstrip("/")
    wanted = str(vps_id or "").strip()
    if not base or not wanted:
        return ""
    return f"{base}/api/v1/tables/{urllib.parse.quote(wanted)}/cumulative-rating"


def _number(value, fallback=None):
    if isinstance(value, bool) or value is None or value == "":
        return fallback
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def _as_text(value) -> str:
    """What a year that is not a number falls back to.

    A string is kept as it came - "1995-06" and "unknown" are both things a catalog has
    said. Anything else is not a year in any reading, and passing it through would leave
    a field that is documented as a number or a string holding neither.
    """
    return value if isinstance(value, str) else ""


def _whole(value):
    """A year as a whole number where it is one.

    The browser produced this and JavaScript has one number type, so 1995 came out of it
    as 1995. Python would send 1995.0 to anything reading the answer over REST, which is
    a different value to a reader that cares.
    """
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value


def normalize(vps_id: str, payload) -> dict | None:
    """The answer, in the shape a theme already reads.

    Every field is coerced rather than trusted: this is somebody else's server, and a
    theme reading `rating.ratingCount.toFixed()` should not be the thing that discovers
    it sent a string.
    """
    if not isinstance(payload, dict):
        return None
    catalog = payload.get("vpsdb")
    catalog = catalog if isinstance(catalog, dict) else {}
    year = _whole(_number(catalog.get("year"), _as_text(catalog.get("year"))))
    count = _number(payload.get("ratingCount"))
    return {
        "vpsId": str(payload.get("vpsId") or vps_id or "").strip(),
        "cumulativeRating": _number(payload.get("cumulativeRating")),
        "ratingCount": 0 if count is None else max(0, int(count)),
        "vpsdb": {
            "name": catalog.get("name") if isinstance(catalog.get("name"), str) else "",
            "authors": catalog.get("authors") if isinstance(catalog.get("authors"), list) else [],
            "manufacturer": (catalog.get("manufacturer")
                             if isinstance(catalog.get("manufacturer"), str) else ""),
            "year": year,
        },
        "fetchedAt": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    }


def fetch(endpoint: str, vps_id: str) -> dict | None:
    """What its players have said about one table, or None.

    None for every way of not knowing - no endpoint, no catalog id, a table it has never
    heard of, a server that is down. A caller showing a rating cannot act on the
    difference, and treating "down" as an error would make a connector's bad day into
    something the player sees.
    """
    url = rating_url(endpoint, vps_id)
    if not url:
        return None
    try:
        with urllib.request.urlopen(url, timeout=TIMEOUT_SECONDS) as answer:
            payload = json.loads(answer.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, ValueError, OSError) as exc:
        logger.debug("No rating for %s: %s", vps_id, exc)
        return None
    return normalize(vps_id, payload)
