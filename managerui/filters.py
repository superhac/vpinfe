from __future__ import annotations

from collections.abc import Iterable
from typing import Any


ALL_VALUE = "All"


def _as_list(value: Any) -> list:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple | set):
        return list(value)
    return [value]


def build_table_filter_options(rows: Iterable[dict]) -> dict[str, list[str]]:
    manufacturers = set()
    years = set()
    themes = set()
    table_types = set()

    for row in rows:
        manufacturer = row.get("manufacturer", "")
        if manufacturer:
            manufacturers.add(str(manufacturer))

        year = row.get("year", "")
        if year:
            years.add(str(year))

        for theme in _as_list(row.get("themes", [])):
            if theme:
                themes.add(str(theme))

        table_type = row.get("type", "")
        if table_type:
            table_types.add(str(table_type))

    return {
        "manufacturers": [ALL_VALUE] + sorted(manufacturers),
        "years": [ALL_VALUE] + sorted(years),
        "themes": [ALL_VALUE] + sorted(themes),
        "table_types": [ALL_VALUE] + sorted(table_types),
    }


def apply_table_filters(
    rows: Iterable[dict],
    filter_state: dict[str, Any],
    *,
    search_fields: tuple[str, ...] = ("name",),
    extra_predicates: Iterable | None = None,
) -> list[dict]:
    result = list(rows)

    search_term = str(filter_state.get("search", "") or "").lower().strip()
    if search_term:
        result = [
            row for row in result
            if any(search_term in str(row.get(field, "") or "").lower() for field in search_fields)
        ]

    manufacturer = filter_state.get("manufacturer", ALL_VALUE)
    if manufacturer != ALL_VALUE:
        result = [row for row in result if row.get("manufacturer") == manufacturer]

    year = filter_state.get("year", ALL_VALUE)
    if year != ALL_VALUE:
        result = [row for row in result if str(row.get("year", "")) == str(year)]

    theme = filter_state.get("theme", ALL_VALUE)
    if theme != ALL_VALUE:
        result = [
            row for row in result
            if theme in _as_list(row.get("themes", []))
        ]

    table_type = filter_state.get("table_type", ALL_VALUE)
    if table_type != ALL_VALUE:
        result = [row for row in result if row.get("type") == table_type]

    for predicate in extra_predicates or ():
        result = [row for row in result if predicate(row)]

    result.sort(key=lambda row: str(row.get("name") or "").lower())
    return result
