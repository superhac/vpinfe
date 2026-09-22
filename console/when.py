"""A moment in time, drawn for whoever is reading it.

Records keep UTC with a `Z` (`common/timestamps.utc_now_iso`); a screen shows local wall
time. This is the one place that crosses between them.
"""

from __future__ import annotations

from datetime import datetime

# Digits and separators only. A format with a month name in it would need the catalog,
# which `i18n.date` exists for.
SHOWN = "%Y-%m-%d %H:%M:%S"

# A grid column's formatter. Guarded by tests/console/test_a_time_on_screen_is_local.py.
CELL = (
    "params => {"
    " const said = params.value;"
    " if (!said) return '';"
    " const at = new Date(said);"
    " if (isNaN(at.getTime())) return said;"
    " const pad = n => String(n).padStart(2, '0');"
    " return at.getFullYear() + '-' + pad(at.getMonth() + 1) + '-' + pad(at.getDate())"
    "   + ' ' + pad(at.getHours()) + ':' + pad(at.getMinutes()) + ':' + pad(at.getSeconds());"
    " }"
)


def local(stamp: str) -> str:
    """A UTC stamp as local wall time, or "" where there is none.

    Returns the stamp unchanged when it will not parse: a value we cannot read is still
    the only answer there is, and blanking it would report a device as never seen.
    """
    said = str(stamp or "").strip()
    if not said:
        return ""
    try:
        parsed = datetime.fromisoformat(said.replace("Z", "+00:00"))
    except ValueError:
        return said
    return parsed.astimezone().strftime(SHOWN)
