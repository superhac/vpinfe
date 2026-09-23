"""A moment in time, drawn for whoever is reading it.

Records keep UTC with a `Z` (`common/timestamps.utc_now_iso`). A screen says how long ago,
with the exact local time one hover away.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from common import i18n
from common.i18n import t

# Digits and separators only, so the same in every language. The one with a month name
# in it is the language's own, which `i18n.date` writes from the catalog.
DATE_SHAPES = {"iso": "%Y-%m-%d", "mm/dd/yyyy": "%m/%d/%Y", "dd/mm/yyyy": "%d/%m/%Y",
               "dd.mm.yyyy": "%d.%m.%Y", "yyyy/mm/dd": "%Y/%m/%d"}

# Past this, "how long ago" stops answering anything and the date does.
RECENT = timedelta(days=30)


def parsed(stamp: Any) -> datetime | None:
    said = str(stamp or "").strip()
    if not said:
        return None
    try:
        at = datetime.fromisoformat(said.replace("Z", "+00:00"))
    except ValueError:
        return None
    return at if at.tzinfo else at.replace(tzinfo=UTC)


def local(stamp: Any) -> str:
    """A UTC stamp as local wall time, or "" where there is none.

    Returns the stamp unchanged when it will not parse: a value we cannot read is still
    the only answer there is, and blanking it would report a device as never seen.
    """
    at = parsed(stamp)
    if at is None:
        return str(stamp or "").strip()
    at = at.astimezone()
    return f"{day(at)} {clock(at)}"


def _setting(key: str, default: str) -> str:
    from common.config_access import cfg_get
    from common.paths import get_ini_config

    return str(cfg_get(get_ini_config(), "console", key, default) or default).strip().lower()


def day(at: datetime) -> str:
    shape = DATE_SHAPES.get(_setting("dates", "language"))
    return at.strftime(shape) if shape else i18n.date(at)


def clock(at: datetime) -> str:
    if _setting("times", "24h") == "12h":
        return t("date.clock_12", hour=at.hour % 12 or 12, minute=f"{at.minute:02d}",
                 period=t("date.pm" if at.hour >= 12 else "date.am"))
    return at.strftime("%H:%M")


def ago(stamp: Any, now: datetime | None = None, *, timed: bool = False) -> str:
    """How long ago, in the catalog's words. "" where there is no stamp.

    A stamp ahead of the clock answers with the time itself - nothing is seen in the
    future, so that is a clock worth showing rather than hiding behind "just now".
    `timed` answers with the time of day as well wherever it falls back to the date.
    """
    at = parsed(stamp)
    if at is None:
        return str(stamp or "").strip()
    seconds = ((now or datetime.now(UTC)) - at).total_seconds()
    if seconds < 0:
        return local(stamp)
    if _setting("relative_dates", "true") in ("false", "0", "no", "off"):
        return local(stamp) if timed else day(at.astimezone())
    if seconds < 60:
        return t("date.just_now")
    if seconds < 3600:
        return t("date.minutes_ago", count=int(seconds // 60))
    if seconds < 86400:
        return t("date.hours_ago", count=int(seconds // 3600))
    if seconds < RECENT.total_seconds():
        return t("date.days_ago", count=int(seconds // 86400))
    return local(stamp) if timed else day(at.astimezone())


def cell(field: str) -> dict[str, Any]:
    """Draw `field` from `<field>_ago`, hover `<field>_at`. `said` fills both."""
    return {":valueFormatter": f"params => (params.data || {{}}).{field}_ago || ''",
            "tooltipField": f"{field}_at"}


def said(row: dict[str, Any], field: str, now: datetime | None = None) -> dict[str, Any]:
    """The row with `<field>_ago` and `<field>_at` filled from its stamp, for `cell`."""
    stamp = row.get(field)
    return {**row, f"{field}_ago": ago(stamp, now), f"{field}_at": local(stamp)}
