"""What this machine is doing, and what it has been doing this session.

The live half. A machine's host, OS and browser are facts rather than readings and they
belong to the device that reports them - the Devices workbench answers *is that machine
healthy*, and this answers *what is this one doing, and what has it been doing*.

Reading is what fills the history, so leaving this page open is what builds the record.
Nothing samples in the background: a machine nobody is watching does not need a log of
having been idle.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from nicegui import run, ui

from console import panel

logger = logging.getLogger("vpinfe.console.metrics")

# The cadence the job line already uses, so a page with both on it ticks once rather
# than twice out of step.
EVERY_SECONDS = 2.0

# How far back the graphs reach. Ten minutes answers "did that scan do this?" without
# turning a sparkline into a smear.
WINDOW_SECONDS = 600

# Where a reading stops being ordinary. Two thresholds rather than a gradient: a color
# that changes continuously says something is changing, which is not the question.
WARN, BAD = 75.0, 90.0


def build(library, state: dict[str, Any], redraw: Callable[[], None]) -> None:
    """Drawn once, then updated in place.

    Clearing and rebuilding on every tick was the first attempt and it is wrong: the
    graphics switch is a control somebody reaches for, and a control replaced under
    their finger every two seconds cannot be clicked. Only the values move.
    """
    held: dict[str, Any] = {"gpu": None, "watch_gpu": bool(state.get("metrics_gpu"))}

    with ui.column().classes("w-full gap-3"):
        note = ui.label("").classes("console-help")
        note.set_visibility(False)
        with ui.row().classes("w-full gap-4 no-wrap items-stretch") as readings:
            cpu = _reading_card("Processor")
            memory = _reading_card("Memory")
        disks_title = ui.label("Free space").classes("console-group mt-2")
        disks = ui.element("div").classes("console-card w-full")
        ui.label("Graphics").classes("console-group mt-2")
        with ui.element("div").classes("console-card w-full"):
            with ui.row().classes("items-center gap-3 w-full no-wrap"):
                ui.label("Watch the graphics cards") \
                    .classes("console-setting grow min-w-0")
                # Through the shared control, which is where "on is green" is decided.
                # Drawn by hand here it was the default color, so the one switch on this
                # page did not agree with every other switch in the Console.
                panel.switch(held["watch_gpu"], lambda event: on_switch(event))()
            cards = ui.column().classes("w-full gap-0")

    def on_switch(event: Any) -> None:
        held["watch_gpu"] = bool(event.value)
        state["metrics_gpu"] = held["watch_gpu"]
        held["gpu"] = None
        _draw_cards(cards, held)

    def show(said: str) -> None:
        note.text = said
        note.set_visibility(bool(said))
        for element in (readings, disks_title, disks):
            element.set_visibility(not said)

    async def tick() -> None:
        try:
            found = await run.io_bound(library.metrics, WINDOW_SECONDS)
        except Exception as exc:  # noqa: BLE001 - this page says why, never 500s
            show(f"Could not read this machine: {exc}")
            return
        now = found.get("now") or {}
        if not now.get("measurable"):
            # Offered with the reason rather than hidden: a page that simply omits the
            # readings leaves somebody unsure whether the machine is fine or this is.
            show(str(now.get("reason") or "This machine cannot report its readings."))
            return
        show("")
        history = found.get("history") or []
        _fill(cpu, now.get("cpu_percent"),
              [one.get("cpu_percent") for one in history],
              _load_said(now.get("load")))
        _fill(memory, now.get("memory_percent"),
              [one.get("memory_percent") for one in history],
              _bytes_said(now.get("memory_used"), now.get("memory_total")))
        _fill_disks(disks, now.get("disks") or [])
        if held["watch_gpu"]:
            try:
                held["gpu"] = await run.io_bound(library.gpu_metrics)
            except Exception as exc:  # noqa: BLE001
                held["gpu"] = {"available": False, "reason": str(exc), "gpus": []}
            _draw_cards(cards, held)

    ui.timer(0.01, tick, once=True)
    ui.timer(EVERY_SECONDS, tick)
    _draw_cards(cards, held)


def _reading_card(title: str) -> dict[str, Any]:
    """The frame for one reading, kept so the tick can move the number rather than
    build the card again."""
    with ui.element("div").classes("console-card grow min-w-0"):
        ui.label(title).classes("console-card-title")
        value = ui.label("-").classes("console-kpi")
        spark = ui.row().classes("items-end gap-px w-full no-wrap").style("height:28px")
        said = ui.label("").classes("text-xs opacity-60")
    return {"value": value, "spark": spark, "said": said}


def _fill(card: dict[str, Any], value: Any, series: list[Any], said: str) -> None:
    card["value"].text = "-" if value is None else f"{value:.0f}%"
    card["value"].style(f"color: {_tone(value)}")
    card["said"].text = said
    _spark(card["spark"], [one for one in series if one is not None])


def _fill_disks(target, disks: list[dict[str, Any]]) -> None:
    target.clear()
    with target:
        for disk in disks:
            _disk_row(disk)


def _draw_cards(target, held: dict[str, Any]) -> None:
    """What the switch reveals. Its own function so the switch above it is built once
    and never replaced under somebody's finger."""
    target.clear()
    with target:
        if not held["watch_gpu"]:
            ui.label("Off. Reading them runs nvtop, so it is asked for rather than "
                     "assumed.").classes("console-help")
            return
        found = held.get("gpu")
        if found is None:
            ui.label("Reading them...").classes("console-help")
            return
        if not found.get("available"):
            # "This machine has no graphics section" and "the tool that reads one is
            # not installed" are different answers, and only the second can be acted on.
            ui.label(str(found.get("reason") or "")).classes("console-help")
            return
        for card in found.get("gpus") or []:
            _card(card, found.get("fields") or [])






def _card(card: dict[str, Any], fields: list[dict[str, Any]]) -> None:
    """One card, per card rather than averaged. Two cards averaged is a number that
    describes neither, and a second card is why somebody opened this."""
    ui.label(str(card.get("name") or "GPU")).classes("console-setting mt-2")
    with ui.row().classes("items-center gap-2 w-full flex-wrap"):
        for field in fields:
            value = card.get(field["key"])
            if value in (None, ""):
                continue
            with ui.element("div").classes("console-member-chip console-tier "
                                           "console-tier--off"):
                ui.label(f"{field['label']} {value}")



def _disk_row(disk: dict[str, Any]) -> None:
    with ui.row().classes("items-center gap-3 w-full no-wrap py-1"):
        with ui.column().classes("gap-0 grow min-w-0"):
            ui.label(disk.get("path", "")).classes("console-setting truncate")
            for also in disk.get("also") or []:
                # Same volume, so the same numbers. Named rather than left out, or
                # somebody looking for it concludes it is not watched.
                ui.label(also).classes("console-help truncate")
        if disk.get("error"):
            # A share that has gone away is exactly what this reports, and saying
            # nothing would show it as a path with no numbers.
            ui.label("cannot be read").classes("text-xs").style(f"color: {_tone(100)}")
            return
        with ui.element("div").classes("w-40 shrink-0"):
            _bar((disk.get("percent") or 0) / 100, _tone(disk.get("percent")))
        # The bar fills as the disk fills, so the words say full too. A bar reading
        # "used" beside a number reading "free" is two directions in one row.
        ui.label(f"{(disk.get('percent') or 0):.0f}% full - "
                 f"{_size(disk.get('free'))} free") \
            .classes("text-xs opacity-60 shrink-0")


def _spark(target, series: list[float]) -> None:
    """The shape of the last few minutes, drawn as bars rather than a line.

    A number says where it is; this says whether it got there. Nothing at all until
    there are two points - one bar is a shape that implies a trend it cannot have.
    """
    target.clear()
    if len(series) < 2:
        with target:
            ui.label("collecting").classes("text-xs opacity-40")
        return
    # Every other point at most, so a ten-minute window is a readable width rather than
    # three hundred hairlines.
    step = max(1, len(series) // 60)
    shown = series[::step][-60:]
    with target:
        for one in shown:
            ui.element("div").style(
                f"flex:1 1 0; min-width:1px; height:{max(2, min(100, one)):.0f}%;"
                f" background:{_tone(one)}; opacity:0.55; border-radius:1px")


def _bar(fraction: float, color: str) -> None:
    with ui.element("div").classes("console-bar w-full"):
        ui.element("div").style(
            f"width:{max(0.0, min(1.0, fraction)) * 100:.0f}%; background:{color}")


def _tone(value: Any) -> str:
    """The declared tokens, not the obvious names: this tree has `--warm` and `--danger`,
    and `--warning`/`--negative` are not declared - a var() naming one is invisible."""
    if value is None:
        return "var(--ink-3)"
    if value >= BAD:
        return "var(--danger)"
    if value >= WARN:
        return "var(--warm)"
    return "var(--accent)"


def _size(value: Any) -> str:
    if value is None:
        return "-"
    size = float(value)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


def _bytes_said(used: Any, total: Any) -> str:
    if used is None or total is None:
        return ""
    return f"{_size(used)} of {_size(total)}"


def _load_said(load: Any) -> str:
    """Load average, where the platform has one. Windows does not, and that is a number
    it does not have rather than one we failed to read."""
    if not load:
        return ""
    return "load " + ", ".join(f"{one:g}" for one in load)
