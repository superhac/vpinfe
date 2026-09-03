"""Views: a named set of columns, a sort and a filter over one grid.

Two kinds. **Built-ins are constants** - read-only, and nothing about them survives a
reload, which is what makes going back to one a reliable way out rather than a
convention. **Custom views** are the user's.

A built-in may filter, on one condition: its name has to be what somebody would predict
the filter from. "Gaps" showing only what is missing is the view doing what it says; a
filter a reader cannot derive from the name is a grid that lost rows. The funnel shows
what is applied either way, and picking another view clears it.

Physical layout - width, order, pinning - is the grid's, not a view's. See
`grid._LAYOUT_FIELDS`.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from common.games.ids import new_id

logger = logging.getLogger("vpinfe.hubui.views")

# Where the user's own views live, beside the layout the grid saves for itself.
VIEWS_SUFFIX = ".views"


@dataclass(frozen=True)
class View:
    """`columns` is the visible fields; `sort` and `filters` are AG Grid's own models,
    stored as given so applying one is a handoff rather than a translation."""

    id: str
    name: str
    builtin: bool = False
    columns: tuple[str, ...] = ()
    sort: tuple[dict[str, Any], ...] = ()
    filters: dict[str, Any] = field(default_factory=dict)
    # A built-in's own words for what it is for. A view the user saved has none: they
    # named it, which is their description of it.
    help: str = ""


def mint_id() -> str:
    """A new custom view's id.

    Minted rather than derived from the name, which is what it used to be. An id that is
    a slug of the name changes when the name does, and anything keyed to it - geometry,
    most of all - is orphaned by a rename. The name is a label; this is the identity.
    """
    return f"view:{new_id()}"


@dataclass(frozen=True)
class Preset:
    """A built-in that wants more than columns. Grids declaring only columns pass a
    plain list and never meet this."""

    columns: tuple[str, ...] = ()
    sort: tuple[dict[str, Any], ...] = ()
    filters: dict[str, Any] = field(default_factory=dict)
    # What the view is for: the job somebody opens it to do. Not a restatement of the
    # filter - a reader can see which rows are here; what they cannot see is why this
    # was worth building a view for.
    help: str = ""


def builtins(presets: dict[str, list[str] | Preset]) -> list[View]:
    """The read-only starting points a grid declares."""
    return [View(id=f"builtin:{name}", name=name, builtin=True,
                 columns=tuple(preset.columns if isinstance(preset, Preset) else preset),
                 sort=tuple(preset.sort) if isinstance(preset, Preset) else (),
                 filters=dict(preset.filters) if isinstance(preset, Preset) else {},
                 help=preset.help if isinstance(preset, Preset) else "")
            for name, preset in presets.items()]


def to_record(view: View) -> dict[str, Any]:
    return {"id": view.id, "name": view.name, "builtin": view.builtin,
            "columns": list(view.columns), "sort": list(view.sort),
            "filters": view.filters}


def from_record(record: dict[str, Any]) -> View:
    """Tolerant of a record from an older build - refusing one would lose the user's
    work over a missing key."""
    return View(id=str(record.get("id") or ""),
                name=str(record.get("name") or "Untitled"),
                builtin=bool(record.get("builtin")),
                columns=tuple(str(c) for c in (record.get("columns") or [])),
                sort=tuple(record.get("sort") or []),
                filters=dict(record.get("filters") or {}))


def stored(library: Any, scope: str) -> tuple[list[View], str]:
    """The user's views for this grid, and which view was last showing."""
    try:
        value = library.preferences(scope + VIEWS_SUFFIX) or {}
    except Exception:
        logger.warning("hub ui: could not read views for %s", scope, exc_info=True)
        return [], ""
    return ([from_record(r) for r in (value.get("views") or [])],
            str(value.get("active") or ""))


def remember(library: Any, scope: str, views: list[View], active: str) -> None:
    """Write the user's views back. Built-ins are never among them."""
    try:
        library.put_preferences(scope + VIEWS_SUFFIX, {
            "views": [to_record(v) for v in views if not v.builtin],
            "active": active,
        })
    except Exception:
        logger.warning("hub ui: could not save views for %s", scope, exc_info=True)


def differs(view: View, columns: tuple[str, ...], sort: tuple[dict, ...],
            filters: dict[str, Any]) -> bool:
    """Whether the screen has drifted from the selected view. Column *order* is not
    compared: dragging one is layout, which the grid keeps for itself."""
    return (set(view.columns) != set(columns)
            or _sort_key(view.sort) != _sort_key(sort)
            or (view.filters or {}) != (filters or {}))


def _sort_key(sort: Any) -> list[tuple[str, str]]:
    """Sort reduced to what a user chose. AG Grid's state carries an entry per column,
    most of them null; comparing those raw reports a difference for every one."""
    ordered = sorted((entry for entry in (sort or []) if entry.get("sort")),
                     key=lambda entry: entry.get("sortIndex") or 0)
    return [(str(entry.get("colId")), str(entry.get("sort"))) for entry in ordered]
