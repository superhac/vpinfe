"""A region still being drawn: `aria-busy` on it at once, a spinner once it has taken a
while, and neither after the work ends, however it ends.

The spinner goes in with the mark. How long it stays hidden is the stylesheet's
(`.console-busy`), not a timer here.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Iterator
from contextlib import contextmanager
from typing import Any

from nicegui import ui


def _hold(region: ui.element) -> ui.element:
    region.props("aria-busy=true")
    with region:
        shown = ui.row().classes("w-full justify-center py-8 console-busy") \
            .props("aria-hidden=true")
        with shown:
            ui.spinner(size="lg").classes("text-primary")
    return shown


def _let_go(region: ui.element, shown: ui.element) -> None:
    if not shown.is_deleted:
        shown.delete()
    region.props(remove="aria-busy")


@contextmanager
def held(region: ui.element) -> Iterator[None]:
    """`region` busy while the block runs, and not after it - returned, raised or
    cancelled."""
    shown = _hold(region)
    try:
        yield
    finally:
        _let_go(region, shown)


def fill(region: ui.element, work: Callable[[], Awaitable[Any]]) -> None:
    """`work` run once the browser has the page, with `region` busy from now until it
    ends.

    The one way to defer a region's first draw. A one-shot `ui.timer` anywhere else in
    the Console fails `tests/invariants/test_a_region_filled_later_says_so.py`.
    """
    shown = _hold(region)

    async def run() -> None:
        try:
            await work()
        finally:
            _let_go(region, shown)

    ui.timer(0.01, run, once=True)
