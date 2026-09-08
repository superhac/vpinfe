"""What this install has written down.

A scrolling viewport with a control bar above it, not a grid. A log is one tall column
you read down, and paging it into rows of columns is the shape that made the old Logs
page hard to scan.

The records arrive already assembled: `read_log` folds a traceback's continuation lines
into the record that caused them, so a level filter cannot drop the half carrying the
reason.

**Two views over the same records.** Stream answers *what happened just now*; Digest
answers *what is wrong with this machine* by collapsing repeats - a machine can log one
mistake four thousand times, and a list of four thousand rows hides that it is one.

Streaming is a timer on this page rather than a transport of its own. The Console is
server-rendered and already holds a live socket to the browser, so the tail pushes over
the one that is there.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from nicegui import run, ui

from console import devices as devices_page
from console import panel

logger = logging.getLogger("vpinfe.console.logs")

# The cadence everything else on this shell ticks at.
EVERY_SECONDS = 2.0

# Enough to see what led to something without turning the page into the whole file. The
# API caps it at the same number.
RECORDS = 500

LEVELS = ("", "DEBUG", "INFO", "WARNING", "ERROR")


def build(library, state: dict[str, Any], redraw: Callable[[], None]) -> None:
    """The control bar, and the viewport under it."""
    held: dict[str, Any] = {
        "level": state.get("log_level", ""),
        "contains": state.get("log_contains", ""),
        "source": state.get("log_source", ""),
        "wrap": state.get("log_wrap", True),
        "digest": state.get("log_digest", False),
        "follow": state.get("log_follow", True),
        "records": [],
        "sources": [],
        "path": "",
    }

    with ui.column().classes("w-full grow min-h-0 gap-2"):
        bar = ui.row().classes("items-center gap-2 w-full no-wrap px-3 pt-2")
        # `min-h-0` on both, or the viewport grows to its content and the page scrolls
        # instead of the log.
        # `console-log` is the treatment the device panel already reads a log with -
        # monospaced, so timestamps and levels line up down the column, and the message
        # under its own header rather than beside it, which is the only shape a
        # traceback fits in.
        viewport = ui.column().classes(
            "w-full grow min-h-0 overflow-auto gap-0 console-log")

    async def load() -> None:
        try:
            found = await run.io_bound(library.logs, RECORDS, held["level"],
                                       held["contains"], held["source"])
        except Exception as exc:  # noqa: BLE001 - this page says why, never 500s
            held["records"], held["error"] = [], str(exc)
        else:
            held["error"] = ""
            held["records"] = list(found.get("records") or [])
            held["sources"] = list(found.get("sources") or [])
            held["path"] = str(found.get("path") or "")
        _draw_bar(bar, held, load, state)
        await _draw(viewport, held)

    ui.timer(0.01, load, once=True)
    # Only while following, and only on the live file: a rotated log does not change,
    # so re-reading it is a request that can only return what it just returned.
    ui.timer(EVERY_SECONDS,
             lambda: load() if held["follow"] and not held["source"] else None)


def _draw_bar(bar, held: dict[str, Any], reload: Callable[[], Any],
              state: dict[str, Any]) -> None:
    bar.clear()
    with bar:
        def remember(key: str, value: Any) -> None:
            held[key] = value
            state[f"log_{key}"] = value

        ui.select({"": "Stream", "digest": "Digest"},
                  value="digest" if held["digest"] else "") \
            .props("dense outlined").classes("w-32") \
            .on_value_change(lambda e: (remember("digest", bool(e.value)), reload()))

        if len(held["sources"]) > 1:
            # Named separately rather than spanned: a rotation boundary is where an
            # install restarted, and reading across one silently would hide that.
            ui.select({name: ("Current" if i == 0 else name)
                       for i, name in enumerate(held["sources"])},
                      value=held["source"] or held["sources"][0]) \
                .props("dense outlined").classes("w-40") \
                .on_value_change(lambda e: (remember("source",
                                                     "" if e.value == held["sources"][0]
                                                     else e.value), reload()))

        ui.select({one: (one.title() if one else "All levels") for one in LEVELS},
                  value=held["level"]).props("dense outlined").classes("w-36") \
            .on_value_change(lambda e: (remember("level", e.value or ""), reload()))

        ui.input(placeholder="Find", value=held["contains"]) \
            .props("dense outlined clearable").classes("grow min-w-0") \
            .on("keydown.enter", lambda e: (remember("contains",
                                                     e.sender.value or ""), reload()))

        wrap = ui.button(icon="wrap_text",
                         on_click=lambda: (remember("wrap", not held["wrap"]),
                                           reload())) \
            .props("flat dense round size=sm")
        wrap.tooltip("Wrap long lines" if not held["wrap"] else "Stop wrapping")
        if held["wrap"]:
            wrap.props(add="color=primary")

        if not held["source"]:
            follow = ui.button(icon="play_arrow" if held["follow"] else "pause",
                               on_click=lambda: (remember("follow",
                                                          not held["follow"]),
                                                 reload())) \
                .props("flat dense round size=sm")
            follow.tooltip("Following. Click to stop." if held["follow"]
                           else "Not following. Click to follow.")
            if held["follow"]:
                follow.props(add="color=primary")
        else:
            # A rotated file does not change, so following it is a control that would
            # do nothing. Refresh is what makes sense there.
            ui.button(icon="refresh", on_click=lambda: reload()) \
                .props("flat dense round size=sm").tooltip("Read it again")

        if held["path"]:
            ui.label(held["path"]).classes("console-help truncate max-w-xs") \
                .tooltip("Where this file is, for reading the rest of it")


async def _draw(viewport, held: dict[str, Any]) -> None:
    # Only when already at the bottom. A tail that yanks you away from the line you are
    # reading is worse than no tail at all.
    at_bottom = True
    try:
        at_bottom = bool(await ui.run_javascript(
            f'(() => {{ const e = getElement({viewport.id}); '
            f'return !e || e.scrollHeight - e.scrollTop - e.clientHeight < 40; }})()',
            timeout=1.0))
    except Exception:  # noqa: BLE001 - a scroll probe must never take the page down
        at_bottom = True

    viewport.clear()
    with viewport:
        if held.get("error"):
            panel.facts(ui, [panel.intro(f"Could not read the log: {held['error']}")])
            return
        if not held["records"]:
            panel.facts(ui, [panel.intro(
                "Nothing matches." if held["level"] or held["contains"]
                else "This install has written nothing yet.")])
            return
        if held["digest"]:
            _digest(held["records"])
        else:
            _stream(held["records"], held["wrap"])

    if at_bottom and not held["digest"]:
        ui.run_javascript(
            f'(() => {{ const e = getElement({viewport.id}); '
            f'if (e) e.scrollTop = e.scrollHeight; }})()')


def _stream(records: list[dict[str, Any]], wrap: bool) -> None:
    """Through the same renderer the device panel uses, so one install's log and
    another's do not read as two different things."""
    for record in records:
        with ui.row().classes("items-baseline gap-2 w-full no-wrap console-log-row"):
            ui.label(str(record.get("when") or "")).classes("console-log-when")
            level = str(record.get("level") or "")
            ui.label(level).classes(
                "console-log-level " + devices_page.LOG_LEVELS.get(
                    level, "console-log-plain"))
            ui.label(str(record.get("logger") or "")).classes("console-log-source")
        # The one thing the shared treatment does not decide: wrapping is a choice on
        # this page, and a stack trace is unreadable either way without it.
        ui.label(str(record.get("message") or "")).classes("console-log-message") \
            .style("" if wrap else "white-space:pre; overflow-x:auto")


def _digest(records: list[dict[str, Any]]) -> None:
    """The same records, collapsed by what they are rather than listed by when.

    Grouped on the logger plus the message's first line: a traceback varies below that
    line and repeats above it, so grouping on the whole message would count one mistake
    as several.
    """
    grouped: dict[tuple[str, str], dict[str, Any]] = {}
    for record in records:
        message = str(record.get("message") or "")
        key = (str(record.get("logger") or ""), message.split("\n", 1)[0])
        found = grouped.setdefault(key, {"count": 0, "first": record.get("when", ""),
                                         "last": "", "level": record.get("level", ""),
                                         "message": message})
        found["count"] += 1
        found["last"] = record.get("when", "")
        # The worst level any of them arrived at: one warning among a hundred infos is
        # what somebody is looking for.
        if _rank(record.get("level")) > _rank(found["level"]):
            found["level"] = record.get("level")

    ordered = sorted(grouped.items(),
                     key=lambda item: (-_rank(item[1]["level"]), -item[1]["count"]))
    ui.label(f"{len(ordered)} distinct in {len(records)} records") \
        .classes("console-help px-3 pb-1")
    for (source, first_line), found in ordered:
        tone = devices_page.LOG_LEVELS.get(str(found["level"] or ""),
                                           "console-log-plain")
        with ui.row().classes("items-baseline gap-3 w-full no-wrap console-log-row"):
            ui.label(f"{found['count']}x").classes(f"shrink-0 {tone}") \
                .style("min-width:4ch; text-align:right")
            with ui.column().classes("gap-0 grow min-w-0"):
                ui.label(first_line).classes(f"truncate {tone}")
                ui.label(f"{source} - first {found['first']}, last {found['last']}") \
                    .classes("console-log-source")


def _rank(level: Any) -> int:
    return {"DEBUG": 0, "INFO": 1, "WARNING": 2,
            "ERROR": 3, "CRITICAL": 4}.get(str(level or "").upper(), 1)
