"""Record Media for one game or table: which kinds, what becomes of the files already
there, and the Recording settings for this recording only. Then the recording as a job,
and a look at what it kept for a decision.

What a choice fills and replaces, and how long it takes, are the device's answer to
`POST /capture/plan`, asked again at each change rather than worked out here.
"""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import Callable, Sequence
from functools import partial
from typing import Any, Literal

from nicegui import ui

from common.capture import preflight
from common.capture.run import EXISTING, FILL, INTERRUPTED, REPLACED
from common.capture.session import AUDIO, KINDS
from common.failures import why
from common.games import asset_origin
from common.i18n import size, t
from common.media_specs import media_label_map
from console import (
    art,
    confirm,
    media_ownership,
    mediaview,
    offload,
    panel,
    recording,
    remembered,
    settings,
    undo,
    verbs,
)
from console import dialog as frame
from console.on_page import on_page

TICKS = "record.kinds"
# Sound is Media's Audio tick here, not a setting of its own.
TICKED_ELSEWHERE = frozenset({"sound"})
# Whose file is a person's own, where a count says how many of what goes are theirs.
YOURS = frozenset({"user", asset_origin.UNKNOWN, asset_origin.RECORDED})
# What a recording's file is, by its kind's family: the session writes these.
MADE_AS = {"video": ".mp4", "image": ".png", "audio": ".mp3"}
_POLL_S = 1.0
_POLLS = 3600
# A run of a library can take a night.
_RUN_POLL_S = 2.0
_RUN_POLLS = 43200


def order(kept: set[str] | None = None) -> list[str]:
    """Every kind a recording makes, window by window, then Audio; only the kinds the
    library keeps, where it says."""
    kinds = [kind for pair in KINDS.values() for kind in pair] + [AUDIO]
    return [kind for kind in kinds if not kept or kind in kept]


Target = tuple[str, str]


def targets(named: Sequence[Target]) -> dict[str, Any]:
    """The games and the tables of a plan's or a run's body, each `(game, table)` with
    "" for a game's own."""
    games = [game_id for game_id, table_id in named if not table_id]
    tables = [{"game": game_id, "table": table_id} for game_id, table_id in named if table_id]
    return {**({"games": games} if games else {}), **({"tables": tables} if tables else {})}


def target(game_id: str, table_id: str) -> dict[str, Any]:
    return targets([(game_id, table_id)])


def asked(named: Sequence[Target], existing: str, kinds: Sequence[str],
          chosen: dict[str, bool], changed: dict[str, Any]) -> dict[str, Any]:
    """The plan's and the run's body: the kinds ticked, and the settings changed here."""
    return {**targets(named), "existing": existing,
            "kinds": [kind for kind in kinds if chosen.get(kind)], "settings": dict(changed)}


def wanted(game_id: str, table_id: str, existing: str, kinds: Sequence[str],
           chosen: dict[str, bool], changed: dict[str, Any]) -> dict[str, Any]:
    return asked([(game_id, table_id)], existing, kinds, chosen, changed)


def confirmed(body: dict[str, Any], plan: dict[str, Any]) -> dict[str, Any]:
    """A run that deletes files carries the count its plan said it would."""
    replacing = int(plan.get("replacing") or 0)
    return {**body, "confirmed": {"count": replacing}} if replacing else body


def blocked(row: dict[str, Any] | None) -> str:
    """Why the device cannot record a plan row's kind, in words; "" where it can."""
    reason = (row or {}).get("reason")
    return preflight.words(reason) if reason else ""


def rows_of(kinds: Sequence[str], slots: dict[str, dict[str, Any]]
            ) -> list[tuple[tuple[str, ...], str]]:
    """The Media rows: each one's kinds and why they cannot be recorded. A window whose
    picture and video are stopped by the same thing is one row."""
    rows: list[tuple[tuple[str, ...], str]] = []
    for pair in [*KINDS.values(), (AUDIO,)]:
        here = [kind for kind in pair if kind in kinds]
        said = [blocked(slots.get(kind)) for kind in here]
        if len(here) == 2 and said[0] and said[0] == said[1]:
            rows.append((tuple(here), said[0]))
            continue
        rows += [((kind,), why_not) for kind, why_not in zip(here, said, strict=True)]
    return rows


def holds(row: dict[str, Any] | None) -> str:
    source = (row or {}).get("source")
    if source is None:
        return t("console.media_ownership.missing")
    if source in YOURS - {asset_origin.RECORDED}:
        return t("console.record.yours")
    return media_ownership.source_name(str(source))


def counted(row: dict[str, Any] | None) -> str:
    """How many of a kind's slots have no file and how many have one, over many."""
    missing, have = int((row or {}).get("missing") or 0), int((row or {}).get("have") or 0)
    parts = ([t("console.record.missing", count=missing)] if missing else []) \
        + ([t("console.record.have_one", count=have)] if have else [])
    if len(parts) == 2:
        return t("console.record.missing_have", missing=parts[0], have=parts[1])
    return parts[0] if parts else ""


def ticked(kinds: Sequence[str], slots: dict[str, dict[str, Any]],
           held: dict[str, bool], sound: bool) -> dict[str, bool]:
    """Which kinds start ticked: what this browser held, else every kind but Audio,
    which starts as the device's Sound. A kind the device cannot record never is."""
    return {kind: not blocked(slots.get(kind))
            and bool(held.get(kind, sound if kind == AUDIO else True)) for kind in kinds}


def remember(held: dict[str, bool], chosen: dict[str, bool],
             slots: dict[str, dict[str, Any]]) -> dict[str, bool]:
    """`held` with the answers given now. A dimmed row was not answered."""
    return {**held, **{kind: on for kind, on in chosen.items()
                       if not blocked(slots.get(kind))}}


def touches(plan: dict[str, Any]) -> str:
    """What the chosen Existing Files will do: how many it fills, and what it replaces or
    asks about."""
    if not plan.get("recording"):
        return t("console.record.nothing_to_record")
    fills, asks = int(plan.get("fills") or 0), int(plan.get("asks") or 0)
    replacing = int(plan.get("replacing") or 0)
    yours = sum(int(count) for source, count in
                (plan.get("replacing_by_source") or {}).items() if source in YOURS)
    filled = t("console.record.fills", count=fills) if fills \
        else t("console.record.fills_none")
    if asks:
        then = t("console.record.asks_about", count=asks)
    elif not replacing:
        then = t("console.record.replaces_none")
    elif not yours:
        then = t("console.record.replaces_downloaded", count=replacing)
    elif yours == replacing:
        then = t("console.record.replaces_yours", count=replacing)
    else:
        then = t("console.record.replaces_some_yours", count=replacing, yours=yours)
    return t("console.record.touches", fills=filled, then=then)


def _minutes(seconds: int) -> int:
    return max(1, round(seconds / 60))


def about(seconds: int) -> str:
    return t("console.record.about_minutes", count=_minutes(seconds))


def recording_for(seconds: int) -> str:
    return t("console.record.recording_for", count=_minutes(seconds))


def slots_of(plan: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Each kind's row: over every target, and for a plan of one, that target's own."""
    found = {str(row["kind"]): dict(row) for row in plan.get("kinds") or []}
    if len(plan.get("targets") or []) == 1:
        for row in plan["targets"][0].get("kinds") or []:
            found[str(row["kind"])] = {**found.get(str(row["kind"]), {}), **row}
    return found


def by_source(plan: dict[str, Any]) -> list[str]:
    """How many files a run would delete, counted by whose they are."""
    theirs: dict[str, int] = {}
    yours = 0
    for source, count in (plan.get("replacing_by_source") or {}).items():
        if source in YOURS:
            yours += int(count)
        else:
            name = media_ownership.source_name(str(source))
            theirs[name] = theirs.get(name, 0) + int(count)
    return [t("console.record.count_from", count=count, source=name)
            for name, count in theirs.items()] \
        + ([t("console.record.count_yours", count=yours)] if yours else [])


def going(plan: dict[str, Any]) -> list[str]:
    """Each file a recording would delete, and whose it is."""
    return [t("console.record.file_from", file=str(row.get("file") or ""),
              source=holds(row))
            for target in plan.get("targets") or [] for row in target.get("kinds") or []
            if row.get("does") == REPLACED and row.get("goes")]


def stopped(report: dict[str, Any], row: dict[str, Any] | None, running: bool) -> str:
    """Why Record cannot run now, in words; "" where it can."""
    if not report.get("available"):
        return preflight.words(report.get("reason") or {})
    return blocked(row) or (t("console.record.table_running") if running else "")


def device_default(option: dict[str, Any], device: Any, value: Any) -> str:
    """The line under a setting changed for this recording, naming the device's value;
    "" while it holds the device's."""
    if settings.value_for(option, value) == settings.value_for(option, device):
        return ""
    said = settings.value_words(option, settings.value_for(option, device)) \
        or str(option.get("blank") or "") \
        or (t("console.record.vpinfe_own") if recording.command_of(option) else "")
    return t("console.record.device_default", value=said)


class Settings:
    """The Recording settings as this recording holds them: the device's, and the
    values changed for it alone."""

    def __init__(self, options: list[dict[str, Any]], device: dict[str, Any]) -> None:
        self.options = options
        self.device = device
        self.changed: dict[str, Any] = {}

    def value(self, option: dict[str, Any]) -> Any:
        key = option["key"]
        return self.changed.get(key, self.device.get(key, option.get("default")))

    def set(self, option: dict[str, Any], value: Any) -> None:
        """A number left empty, or a value the same as the device's, is the device's."""
        key = option["key"]
        held = self.device.get(key, option.get("default"))
        if (value in ("", None) and option.get("type") == "int") \
                or settings.value_for(option, value) == settings.value_for(option, held):
            self.changed.pop(key, None)
        else:
            self.changed[key] = value

    def kept(self) -> None:
        """The changed values are now the device's."""
        self.device.update(self.changed)
        self.changed.clear()


def options_of(schema: list[dict[str, Any]]) -> list[dict[str, Any]]:
    section = next((block for block in schema
                    if str(block.get("name")) == recording.SECTION), {})
    return [option for option in section.get("options") or []
            if option["key"] not in TICKED_ELSEWHERE]


def setting_rows(held: Settings, report: dict[str, Any], changed: Callable[[], Any],
                 rerender: Callable[[], None],
                 browse: Callable[..., dict] | None = None) -> list[tuple[Any, Any]]:
    entries: list[tuple[Any, Any]] = []
    heading = ""
    offered = {recording.REPORT: report}
    for option in settings.by_group(held.options):
        group = str(option.get("group_label") or "")
        if group and group != heading:
            entries.append((panel.HEADING, group))
        heading = group
        device = held.device.get(option["key"], option.get("default"))
        shown: dict[str, Any] = {}

        def line(option: dict[str, Any] = option, device: Any = device,
                 shown: dict[str, Any] = shown) -> None:
            said = device_default(option, device, held.value(option))
            shown["line"] = panel.line(said)
            shown["line"].set_visibility(bool(said))

        async def save(value: Any, option: dict[str, Any] = option, device: Any = device,
                       shown: dict[str, Any] = shown) -> bool:
            held.set(option, value)
            said = device_default(option, device, held.value(option))
            if shown.get("line") is not None:
                shown["line"].set_text(said)
                shown["line"].set_visibility(bool(said))
            answer = changed()
            if inspect.isawaitable(answer):
                await answer
            return True

        # A number cleared shows what it goes back to.
        blank = settings.value_words(option, settings.value_for(option, device)) \
            if option.get("type") == "int" else str(option.get("blank") or "")
        entries.append((str(option.get("label") or option["key"]),
                        settings.control_for({**option, "blank": blank}, held.value(option),
                                             save, suggestions=offered, browse=browse)))
        entries.append((panel.ASIDE, line))
        if recording.command_of(option):
            recording.add_under(entries, option, held.value(option), save, rerender, offered)
    return entries


@on_page
async def ask(library: Any, named: Sequence[Target], title: str,
              state: dict[str, Any], then: Callable[[], Any], *,
              only: Sequence[str] | None = None) -> None:
    """The Record dialog for these games or tables, then the recording. `only` ticks
    those kinds and no others, leaving what this browser keeps for the rest alone."""
    kinds = order(set(library.kept_kinds().get("media") or ()) or None)
    try:
        report, schema, values, playing = await asyncio.gather(
            offload.io(library.capture_report), offload.io(library.config_schema),
            offload.io(library.config_values), offload.io(library.play_state))
        whole = await offload.io(library.plan_capture, {**targets(named), "kinds": kinds})
    except Exception as exc:  # noqa: BLE001 - said, and nothing was recorded
        ui.notify(t("console.record.could_not_read"), caption=why(exc), type="warning")
        return
    if not report.get("available"):
        ui.notify(preflight.words(report.get("reason") or {}), type="warning")
        return
    slots = slots_of(whole)
    device = dict((values or {}).get(recording.SECTION) or {})
    held = Settings(options_of(schema), device)
    remembered_ticks = dict(remembered.get(TICKS) or {})
    sound = bool(settings.value_for({"type": "bool"}, device.get("sound", False)))
    chosen = ticked(kinds, slots, {kind: kind in only for kind in kinds}
                    if only is not None else remembered_ticks, sound)
    running = bool((playing or {}).get("launching"))
    answer = await _dialog(library, list(named), title, kinds, slots, chosen, held,
                           report, running)
    if answer is None:
        return
    if only is None:
        remembered.put(TICKS, remember(remembered_ticks, chosen, slots))
    if len(named) == 1:
        await _start(library, answer, state, then)
    else:
        await _start_run(library, answer, state, then)


async def _dialog(library: Any, named: list[Target], title: str,
                  kinds: list[str], slots: dict[str, dict[str, Any]],
                  chosen: dict[str, bool], held: Settings, report: dict[str, Any],
                  running: bool) -> dict[str, Any] | None:
    labels = media_label_map()
    now: dict[str, Any] = {"existing": FILL, "plan": {}, "said": "", "asked": 0}
    shown: dict[str, Any] = {}
    many = len(named) > 1

    def request() -> dict[str, Any]:
        return asked(named, now["existing"], kinds, chosen, held.changed)

    def show() -> None:
        plan = now["plan"]
        if "touches" in shown:
            shown["touches"].set_text(now["said"])
            shown["estimate"].set_text(about(int(plan.get("estimate_seconds") or 0))
                                       if plan.get("recording") else "")
        go.set_enabled(bool(plan.get("recording")) and not running)
        keep.set_enabled(bool(held.changed))

    async def replan() -> None:
        now["asked"] += 1
        asked = now["asked"]
        body = request()
        try:
            plan = await offload.io(library.plan_capture, body) if body["kinds"] \
                else {"recording": [], "kinds": []}
            said = touches(plan)
        except Exception as exc:  # noqa: BLE001 - the refusal is what the line says
            plan, said = {}, why(exc)
        if asked != now["asked"]:
            return
        now["plan"], now["said"] = plan, said
        show()

    def tick(kind: str, on: bool) -> Any:
        chosen[kind] = on
        return replan()

    async def pick(event: Any) -> None:
        now["existing"] = str(event.value)
        await replan()

    def draw() -> None:
        body.clear()
        existing = {choice: t(f"console.record.existing.{choice}") for choice in EXISTING}
        entries: list[tuple[Any, Any]] = [
            (panel.HEADING, t("console.record.media")),
            (panel.FULL, lambda: _what(kinds, slots, chosen, labels, tick, many)),
            (t("console.record.existing"),
             panel.select(existing, now["existing"], pick,
                          describes={existing[choice]:
                                     t(f"console.record.existing.{choice}.description")
                                     for choice in EXISTING})),
            (panel.ASIDE, lambda: shown.update(touches=panel.line(""))),
            (t("console.record.estimate"),
             lambda: shown.update(estimate=ui.label("").classes("console-fact-value"))),
            *setting_rows(held, report, replan, draw, browse=library.folders),
        ]
        with body:
            panel.facts(ui, entries)
        show()

    @on_page
    async def save_defaults() -> None:
        try:
            await offload.io(library.put_config, {recording.SECTION: dict(held.changed)})
        except Exception as exc:  # noqa: BLE001 - the reason belongs on screen
            ui.notify(t("console.settings.could_not_save"), caption=why(exc),
                      type="negative")
            return
        held.kept()
        ui.notify(t("console.record.saved_defaults"), type="positive")
        draw()

    @on_page
    async def record() -> None:
        plan = now["plan"]
        replacing = int(plan.get("replacing") or 0)
        if replacing and not await confirm.ask(
                t("console.record.replace_ask", count=replacing),
                detail=t("console.record.replace_detail"),
                lines=by_source(plan) if many else going(plan),
                confirm=t("console.record.record_and_replace"), icon=verbs.RECORD):
            return
        box.submit(confirmed(request(), plan))

    with frame.opened(title, wide=True, persistent=True) as box:
        if running:
            with ui.element("div").classes("console-attention w-full"):
                ui.icon("error_outline").classes("console-attention-icon")
                ui.label(t("console.record.table_running")) \
                    .classes("console-attention-line")
        body = ui.column().classes("w-full gap-0 px-3")
        with frame.footer():
            keep = frame.aside(t("console.record.save_defaults"), save_defaults,
                               icon=verbs.SAVE)
            frame.cancel(lambda: box.submit(None))
            go = frame.answer(t("console.record.record"), record, icon=verbs.RECORD)
        go.set_enabled(False)
        keep.set_enabled(False)
        draw()
    await replan()
    answer: dict[str, Any] | None = await box
    return answer


def _what(kinds: list[str], slots: dict[str, dict[str, Any]], chosen: dict[str, bool],
          labels: dict[str, str], tick: Callable[[str, bool], Any], many: bool) -> None:
    """A tick per kind with what its slot holds now, or over many how many have none; a
    row the device cannot record, dimmed with why."""
    with ui.grid(columns="max-content minmax(0, 1fr)") \
            .classes("w-full items-center gap-x-4 gap-y-1"):
        for row_kinds, why_not in rows_of(kinds, slots):
            kind = row_kinds[0]
            box = ui.checkbox(labels.get(kind, kind), value=chosen.get(kind, False)) \
                .props("dense")
            if why_not:
                box.set_enabled(False)
                ui.label(why_not).classes("console-help")
                continue
            box.on_value_change(lambda event, kind=kind: tick(kind, bool(event.value)))
            ui.label(counted(slots.get(kind)) if many else holds(slots.get(kind))) \
                .classes("console-member-qualifier")


def capability(library: Any) -> dict[str, Any] | None:
    """Discovery's `capture`: whether this install records, and why not; None where it
    does not record at all."""
    return next((one for one in library.discovery().get("capabilities") or []
                 if one.get("name") == "capture"), None)


def menu_entry(library: Any, label: str, run: Callable[[], Any]) -> None:
    """Into the menu being built: `label`, refused with the device's reason where it
    records nothing, and left out where the install does not record."""
    able = capability(library)
    if able is None:
        return
    panel.menu_entry(label, run, refused="" if able.get("available")
                     else str(able.get("reason") or ""))


@on_page
async def _start(library: Any, body: dict[str, Any], state: dict[str, Any],
                 then: Callable[[], Any]) -> None:
    try:
        job = await offload.io(library.start_capture, body)
    except Exception as exc:  # noqa: BLE001 - said, and nothing was recorded
        ui.notify(t("console.record.could_not_start"), caption=why(exc), type="warning")
        return
    watch = state.get("watch_jobs")
    if callable(watch):
        watch()
    await finished(library, str(job.get("id") or ""), then)


async def ended_job(library: Any, job_id: str, *, every: float = _POLL_S,
                    polls: int = _POLLS) -> dict[str, Any]:
    """A recording's job once it ends: what it answered, or `error` where the job itself
    failed; {} where the job could not be read."""
    for _ in range(polls):
        await asyncio.sleep(every)
        try:
            found = await offload.io(library.capture_job, job_id)
        except Exception:  # noqa: BLE001 - the job line still reports it
            return {}
        if found.get("state") == "running":
            continue
        if found.get("state") == "failed":
            return {"error": str(found.get("error") or "")}
        return dict(found.get("result") or {})
    return {}


async def ended(library: Any, job_id: str) -> dict[str, Any]:
    """A recording's job once it ends: its table's outcome, with `error` where the job
    itself failed; {} where the job could not be read."""
    result = await ended_job(library, job_id)
    if not result or "error" in result:
        return result
    return dict((result.get("tables") or [{}])[0])


@on_page
async def _start_run(library: Any, body: dict[str, Any], state: dict[str, Any],
                     then: Callable[[], Any]) -> None:
    try:
        job = await offload.io(library.start_capture, body)
    except Exception as exc:  # noqa: BLE001 - said, and nothing was recorded
        ui.notify(t("console.record.could_not_start"), caption=why(exc), type="warning")
        return
    watch = state.get("watch_jobs")
    if callable(watch):
        watch()
    await follow_run(library, str(job.get("id") or ""), state, then)


@on_page
async def follow_run(library: Any, job_id: str, state: dict[str, Any],
                     then: Callable[[], Any]) -> None:
    """Wait for a run's job, however long, and say how it ended."""
    await say_run(library, await ended_job(library, job_id, every=_RUN_POLL_S,
                                           polls=_RUN_POLLS), state, then)


def waiting(run: dict[str, Any]) -> tuple[str, str]:
    """What the job line says of a run left waiting, and why on hover; ("", "") for one
    that is going, or none."""
    if run.get("state") != "paused":
        return "", ""
    reason = dict(run.get("reason") or {})
    at, of = int(run.get("done") or 0) + 1, int(run.get("of") or 0)
    if reason.get("key") == INTERRUPTED:
        return t("console.record.run_stopped", at=at, of=of), preflight.words(reason)
    return (t("console.record.run_paused", at=at, of=of),
            preflight.words(reason) if reason else "")


def run_failures(tables: Sequence[dict[str, Any]]) -> str:
    """Why a run's games or kinds failed, each reason once: with the kinds it stopped, or
    how many games it stopped where they failed whole."""
    labels = media_label_map()
    kinds: dict[str, list[str]] = {}
    games: dict[str, int] = {}
    for one in tables:
        if one.get("state") == "failed" and one.get("reason"):
            said = failed_because(one)
            games[said] = games.get(said, 0) + 1
        for kind in one.get("failed") or []:
            label = labels.get(str(kind.get("kind") or ""), str(kind.get("kind") or ""))
            stopped = kinds.setdefault(failed_because(kind), [])
            if label not in stopped:
                stopped.append(label)
    return "; ".join(
        [t("console.record.failed_kinds", kinds=", ".join(names), reason=said)
         for said, names in kinds.items()]
        + [t("console.record.failed_games", reason=said, count=count)
           for said, count in games.items()])


def run_outcome(result: dict[str, Any]) -> tuple[str, Level, str]:
    """What a run of many says when its job ends: the words, the notice type, and a
    caption with why anything failed, or why it paused."""
    tables = list(result.get("tables") or [])
    ending = dict(result.get("run") or {})
    if ending.get("state") == "paused":
        reason = ending.get("reason")
        return (t("console.record.run_paused", at=int(ending.get("done") or 0) + 1,
                  of=int(ending.get("of") or 0)), "warning",
                preflight.words(reason) if reason else "")
    recorded = sum(1 for one in tables if one.get("state") == "recorded")
    failed = sum(1 for one in tables if one.get("state") == "failed")
    waiting = sum(len(one.get("proposed") or []) for one in tables)
    caption = run_failures(tables)
    if not recorded:
        if failed:
            return t("console.record.could_not_record"), "negative", caption
        return t("console.record.nothing_to_record"), "info", ""
    said = t("console.record.run_recorded", count=recorded)
    if failed:
        said = t("console.record.recorded_failed", recorded=said, failed=failed)
    if waiting:
        said = t("console.record.run_waiting", said=said, count=waiting)
    return said, "warning" if caption else "positive", caption


@on_page
async def say_run(library: Any, result: dict[str, Any], state: dict[str, Any],
                  then: Callable[[], Any]) -> None:
    """The end of a run of many: one notice, with Review where it ended leaving
    recordings for a decision, else Show where anything was placed."""
    if not result:
        return
    if "error" in result:
        ui.notify(t("console.record.could_not_record"), caption=str(result["error"]),
                  type="negative")
        return
    said, level, caption = run_outcome(result)
    tables = list(result.get("tables") or [])
    placed = any(one.get("placed") for one in tables)
    waiting = [] if (result.get("run") or {}).get("state") == "paused" else [
        str(one.get("id") or "") for table in tables for one in table.get("proposed") or []]
    show = state.get("show_recorded")
    if waiting:
        undo.act(said, t("console.record.review"), lambda: review(library, then, waiting),
                 warn=level != "positive", caption=caption)
    elif placed and callable(show):
        undo.act(said, t("console.page.show"), show, warn=level != "positive",
                 caption=caption)
    else:
        ui.notify(said, type=level, caption=caption, multi_line=bool(caption))
    if placed:
        await _call(then)


@on_page
async def finished(library: Any, job_id: str, then: Callable[[], Any]) -> dict[str, Any]:
    """Wait for a recording's job and say what it did. Answers the table's outcome, {}
    where the job failed."""
    ran = await ended(library, job_id)
    await say(library, ran, then)
    return {} if "error" in ran else ran


@on_page
async def say(library: Any, ran: dict[str, Any], then: Callable[[], Any]) -> None:
    """The end of one table's recording: the notice, the panel read again where files were
    placed, and the review of what was kept for a decision."""
    if not ran:
        return
    if "error" in ran:
        ui.notify(t("console.record.could_not_record"), caption=str(ran["error"]),
                  type="negative")
        return
    said, level, caption = outcome(ran)
    ui.notify(said, type=level, caption=caption, multi_line=bool(caption))
    if ran.get("placed"):
        await _call(then)
    proposed = [str(one.get("id") or "") for one in ran.get("proposed") or []]
    if proposed:
        await review(library, then, proposed)


async def _call(then: Callable[[], Any]) -> None:
    answer = then()
    if inspect.isawaitable(answer):
        await answer


def failed_because(one: dict[str, Any]) -> str:
    """Why one kind failed, with what the program said where it said something."""
    reason = dict(one.get("reason") or {})
    said = preflight.words(reason)
    detail = str(reason.get("detail") or "")
    return t("console.record.said_detail", said=said, detail=detail) if detail else said


def failures(failed: Sequence[dict[str, Any]]) -> str:
    """Why kinds failed, each reason once with the kinds it stopped."""
    labels = media_label_map()
    stopped: dict[str, list[str]] = {}
    for one in failed:
        kind = str(one.get("kind") or "")
        stopped.setdefault(failed_because(one), []).append(labels.get(kind, kind))
    return "; ".join(t("console.record.failed_kinds", kinds=", ".join(kinds), reason=said)
                     for said, kinds in stopped.items())


Level = Literal["positive", "negative", "warning", "info"]


def outcome(ran: dict[str, Any]) -> tuple[str, Level, str]:
    """What one table's recording says when it ends: the words, the notice type, and a
    caption with why anything failed."""
    reason = dict(ran.get("reason") or {})
    failed = list(ran.get("failed") or [])
    made = len(ran.get("placed") or []) + len(ran.get("proposed") or [])
    if ran.get("state") == "skipped":
        return preflight.words(reason), "info", ""
    if ran.get("state") == "closed":
        return preflight.words(reason), "warning", ""
    if not made and reason:
        detail = str(reason.get("detail") or "")
        return (t("console.record.could_not_record"), "negative",
                t("console.record.said_detail", said=preflight.words(reason), detail=detail)
                if detail else preflight.words(reason))
    if not made:
        return t("console.record.could_not_record"), "negative", failures(failed)
    recorded = t("console.record.recorded", count=made)
    if failed:
        return (t("console.record.recorded_failed", recorded=recorded, failed=len(failed)),
                "warning", failures(failed))
    return recorded, "positive", ""


def grouped(rows: Sequence[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    """Recordings waiting, a game at a time and a table apart from its game, in the
    order the first of each was kept; on each, window by window."""
    pages: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in rows:
        pages.setdefault((str(row.get("game_id") or ""), str(row.get("table_id") or "")),
                         []).append(row)
    rank = {kind: at for at, kind in enumerate(order())}
    return [sorted(page, key=lambda row: rank.get(str(row.get("kind") or ""), len(rank)))
            for page in pages.values()]


SKIP, NEXT, DONE = "skip", "next", "done"


def onward(at: int, of: int, settled: bool) -> str:
    """The way on from a review's game: Done from the last, Next once every file on it
    is decided, and Skip before that."""
    if at >= of - 1:
        return DONE
    return NEXT if settled else SKIP


@on_page
async def review(library: Any, then: Callable[[], Any],
                 proposed: Sequence[str] | None = None) -> None:
    """The recordings kept for a decision, a game at a time, each beside the file its
    slot holds now; `proposed` narrows them to those. `then` runs once the review closes
    where any was used."""
    try:
        listing = await offload.io(library.capture_proposals)
    except Exception as exc:  # noqa: BLE001 - they still wait on the device
        ui.notify(t("console.record.could_not_read_waiting"), caption=why(exc),
                  type="warning")
        return
    pages = grouped([row for row in listing.get("proposals") or []
                     if proposed is None or row.get("id") in proposed])
    if not pages:
        return
    many = len(pages) > 1
    now: dict[str, Any] = {"at": 0, "decided": set(), "used": False}

    def decided(proposal_id: str, use: bool) -> None:
        now["decided"].add(proposal_id)
        now["used"] = now["used"] or use
        foot()

    def foot() -> None:
        way = onward(now["at"], len(pages),
                     all(row.get("id") in now["decided"] for row in pages[now["at"]]))
        stop.set_visibility(way != DONE)
        skip.set_visibility(way == SKIP)
        ahead.set_visibility(way == NEXT)
        done.set_visibility(way == DONE)

    def draw() -> None:
        page = pages[now["at"]]
        title.set_text(t("console.record.review_title", name=str(page[0].get("name") or "")))
        if many:
            bar.set_value((now["at"] + 1) / len(pages))
            place.set_text(t("console.record.review_at", at=now["at"] + 1, of=len(pages)))
        body.clear()
        with body:
            for row in page:
                proposal(library, row, partial(decided, str(row.get("id") or "")))
        foot()

    def on() -> None:
        now["at"] += 1
        draw()
        ui.run_javascript(f"document.getElementById('c{body.id}')?.scrollTo(0, 0)")

    with frame.opened("", wide=True, persistent=True,
                      classes="console-dialog--series" if many else "") as box:
        title = ui.label("").classes("console-dialog-title")
        if many:
            with ui.row().classes("w-full items-center gap-3 no-wrap px-3 pb-2"):
                bar = ui.linear_progress(value=0, show_value=False).props("rounded") \
                    .classes("grow")
                place = ui.label("").classes("console-help whitespace-nowrap shrink-0")
        body = ui.column().classes("w-full gap-2 px-3 no-wrap console-series-body")
        with frame.footer():
            stop = frame.quiet(t("console.record.stop"), lambda: box.submit(True),
                               icon=verbs.STOP)
            skip = frame.quiet(t("console.record.skip"), on, icon=verbs.SKIP)
            ahead = frame.answer(t("word.next"), on, icon=verbs.NEXT)
            done = frame.answer(t("word.done"), lambda: box.submit(True), icon=verbs.DONE)
        draw()
    await box
    if now["used"]:
        await _call(then)


def deleted(displaced: Sequence[str], replaces: dict[str, Any] | None) -> list[str]:
    """Every file placing a recording deletes: those its name displaces at its tier, and
    the file serving the slot where that goes too."""
    going = list(displaced)
    path = str((replaces or {}).get("path") or "")
    if path and (replaces or {}).get("goes") and path not in going:
        going.append(path)
    return going


def proposal(library: Any, row: dict[str, Any], decided: Callable[[bool], Any], *,
             titled: bool = True) -> None:
    """One recording beside the file it would take the place of, with Use This and
    Discard. `decided` hears which, once it is done."""
    kind, game_id = str(row.get("kind") or ""), str(row.get("game_id") or "")
    table_id = str(row.get("table_id") or "")
    label = media_label_map().get(kind, kind)
    replaces = row.get("replaces") or None
    if titled:
        panel.facts(ui, [(panel.HEADING, label)])
    with ui.row().classes("w-full gap-3 no-wrap items-start"):
        if replaces:
            with ui.column().classes("gap-0 flex-1 min-w-0"):
                with ui.element("div").classes("console-slot-art"):
                    mediaview.preview(art.media(game_id, kind, table_id, size=art.PANEL),
                                      kind, label)
                panel.line(t("console.record.now", source=holds(replaces)),
                           hint=str(replaces.get("path") or ""))
        with ui.column().classes("gap-0 flex-1 min-w-0"):
            with ui.element("div").classes("console-slot-art"):
                mediaview.preview(str(row.get("url") or ""), kind, label)
            ui.label(t("console.record.just_recorded", size=size(int(row.get("size") or 0)))) \
                .classes("console-help")
    strip = ui.row().classes("items-center gap-2 w-full console-slot-actions")

    def settled(word: str, level: str) -> None:
        strip.clear()
        with strip:
            panel.state(word, level)()

    @on_page
    async def use() -> None:
        try:
            going = deleted(await offload.io(library.displaced_by, game_id, table_id, kind,
                                             str(row.get("file") or "")), replaces)
        except Exception as exc:  # noqa: BLE001 - nothing is placed unasked
            ui.notify(t("console.mediasource.could_not_check_slot"), caption=why(exc),
                      type="negative")
            return
        if going and not await confirm.replace(label, going):
            return
        try:
            await offload.io(library.use_proposal, str(row["id"]), True)
        except Exception as exc:  # noqa: BLE001 - it still waits on the device
            ui.notify(t("console.record.could_not_use"), caption=why(exc), type="negative")
            return
        settled(t("console.record.used"), "on")
        await _call(lambda: decided(True))

    @on_page
    async def discard() -> None:
        try:
            await offload.io(library.use_proposal, str(row["id"]), False)
        except Exception as exc:  # noqa: BLE001 - it still waits on the device
            ui.notify(t("console.record.could_not_discard"), caption=why(exc),
                      type="negative")
            return
        settled(t("console.record.discarded"), "off")
        await _call(lambda: decided(False))

    with strip:
        panel.action(t("console.record.use_this"), use, icon=verbs.ACCEPT,
                     hint=t("console.record.use_this.help"))()
        panel.action(t("console.record.discard"), discard, icon=verbs.DISCARD,
                     hint=t("console.record.discard.help"))()
