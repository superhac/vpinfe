
"""What core draws when somebody presses an action an extension offers.

The extension describes what to ask and what to call; this is the one place it is drawn.
Nothing about the treatment comes from the extension, so every action looks like the
Console rather than like whoever wrote it, and it keeps working if that extension later
runs somewhere else.

How many steps there are is read off what the extension answers, never declared. No
fields means press it and it happens. Fields mean fill them in first. A `confirm` means a
step showing what would happen before it runs. So an action that is nothing but a verb
costs a person one press, and the guided one is the same contract with more of it filled
in.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

from nicegui import run, ui

from common.i18n import t
from console import offload, panel, verbs
from console.api import ApiClient

# How often to ask a running job how it is doing. A job here is minutes of copying, so a
# tighter loop would be a question asked hundreds of times for the same answer.
POLL_SECONDS = 1.0


def _controls(fields: list[dict], values: dict[str, Any]) -> None:
    """Draw what the task asked for, in the Console's own grammar."""
    # Each control writes its own key, so the key is bound by a call rather than
    # captured off the loop variable.
    def changed(key: str, cast: Callable[[Any], Any]) -> Callable[[Any], None]:
        def write(event: Any) -> None:
            values[key] = cast(event.value)
        return write

    def typed(key: str) -> Callable[[str], None]:
        def write(text: str) -> None:
            values[key] = text
        return write

    entries: list[tuple[Any, Any]] = []
    for field in fields:
        key = str(field.get("key") or "")
        if not key:
            continue
        values.setdefault(key, field.get("value"))
        kind = str(field.get("type") or "string")
        label = str(field.get("label") or key)
        if kind == "multi":
            choices = {str(one[0]): str(one[1]) for one in field.get("choices") or []}
            entries.append((label, panel.multi_select(
                choices, list(values.get(key) or []),
                changed(key, lambda value: list(value or [])))))
        elif kind == "select":
            choices = {str(one[0]): str(one[1]) for one in field.get("choices") or []}
            entries.append((label, panel.select(
                choices, str(values.get(key) or ""),
                changed(key, lambda value: str(value or "")))))
        elif kind == "switch":
            entries.append((label, panel.switch(
                bool(values.get(key)), changed(key, bool))))
        else:
            entries.append((label, panel.field(
                str(values.get(key) or ""), typed(key))))
        if field.get("help"):
            entries.append((panel.ASIDE, _aside(str(field["help"]))))
    panel.facts(ui, entries)


def _aside(text: str) -> Any:
    def draw() -> None:
        ui.label(text).classes("console-help")
    return draw


async def open_action(extension: str, action: dict) -> None:
    """Run one action: ask what it asks, in as many steps as it asks it, then do it.

    The extension decides what to ask next from what it has been given so far, and says
    so by answering with another step. Core keeps everything answered and hands the whole
    lot back each time, along with the step being left, so a step is a question rather
    than a session - nothing is held between requests that could be stale by the time it
    is used, and going Back and forward again asks the same questions in the same order
    rather than jumping over the ones already answered.

    It stops asking when it answers with a summary instead of fields. That is the same
    rule as everywhere else here: the shape is read off the answer, never declared.
    """
    client = ApiClient()
    base = f"/ext/{extension}{action.get('base') or ''}"
    values: dict[str, Any] = {}
    history: list[dict] = []

    step = await offload.io(client.ext_get, base)

    with ui.dialog().props("persistent") as dialog, \
            ui.card().classes("console-import-card"):
        heading = ui.label("").classes("console-confirm-title")
        body = ui.column().classes("w-full gap-0 console-import-body")
        buttons = ui.row().classes("justify-end gap-2 w-full pt-2")

        def draw(found: dict) -> None:
            heading.text = str(found.get("title") or action.get("label") or "")
            body.clear()
            buttons.clear()
            summary = found.get("summary")
            with body:
                if found.get("help"):
                    ui.label(str(found["help"])).classes("console-help mb-2")
                if summary:
                    _summary(summary)
                _controls(list(found.get("fields") or []), values)
                _lines(list(found.get("notes") or []),
                       t("console.ext_action.worth_knowing") if summary else "")
                if summary and not found.get("ready"):
                    ui.label(str(found.get("reason") or "")).classes("console-help")
            with buttons:
                if history:
                    ui.button(t("word.back"), icon=verbs.BACK, on_click=_back).props("flat no-caps")
                else:
                    ui.button(t("word.cancel"), icon=verbs.CANCEL,
                            on_click=lambda: dialog.submit(False)) \
                        .props("flat no-caps")
                if summary:
                    go = ui.button(str(found.get("confirm")
                                       or action.get("label") or "Go"),
                                   icon=verbs.RUN,
                                   on_click=_start).props("no-caps")
                    if not found.get("ready"):
                        go.disable()
                else:
                    ui.button(t("word.next"), icon=verbs.NEXT, on_click=_next).props("no-caps")

        async def _next() -> None:
            try:
                found = await offload.io(
                client.ext_post, f"{base}/check",
                {"values": values, "step": str(step_now["found"].get("step") or "")})
            except Exception as exc:  # noqa: BLE001
                ui.notify(str(exc), type="negative")
                return
            # A step that answers with itself is the same question asked again, not a
            # new one. Remembering it would make Back go nowhere.
            if str(found.get("step") or "") != str(step_now["found"].get("step") or ""):
                history.append(step_now["found"])
            step_now["found"] = found
            draw(found)

        def _back() -> None:
            step_now["found"] = history.pop()
            draw(step_now["found"])

        async def _start() -> None:
            try:
                started = await offload.io(client.ext_post, f"{base}/run",
                                             {"values": values})
            except Exception as exc:  # noqa: BLE001
                ui.notify(str(exc), type="negative")
                return
            job_id = str(started.get("job_id") or "")
            if job_id:
                await _watch(job_id)
                return
            if started.get("ok") is False:
                ui.notify(str(started.get("reason") or t("console.ext_action.not_run")),
                          type="negative")
                return
            # Finished already. Some actions are one call and a sentence, and making
            # those wear a progress bar would be theatre.
            _finished(body, buttons, dialog, started)

        async def _watch(job_id: str) -> None:
            body.clear()
            buttons.clear()
            with body:
                bar = ui.linear_progress(value=0, show_value=False).classes("w-full")
                said = ui.label(t("console.ext_action.working")).classes("console-help")
            with buttons:
                close = ui.button(t("word.close"), icon=verbs.CLOSE,
                        on_click=lambda: dialog.submit(True)) \
                    .props("flat no-caps")
                close.disable()

            while True:
                job = await offload.io(client.job, job_id)
                bar.value = int(job.get("pct") or 0) / 100
                said.text = str(job.get("message") or t("console.ext_action.working"))
                if str(job.get("state")) not in ("running", "queued"):
                    break
                await run.io_bound(_wait)

            close.enable()
            heading.text = t("console.ext_action.what_happened") if job.get("state") == "done" \
                else t("console.ext_action.not_finish")
            _report(body, job)

        step_now = {"found": step}
        draw(step)

    await dialog


def _summary(rows: list[Sequence[Any]]) -> None:
    """What the previous steps add up to, before anything is done about it.

    A row of one is a heading rather than a fact. Where a summary covers both what was
    chosen and what it comes to, running the two together makes a count read as one more
    setting - and the counts are the part somebody is deciding on.
    """
    panel.facts(ui, [(panel.HEADING, str(row[0])) if len(row) < 2
                     else (str(row[0]), str(row[1]))
                     for row in rows])


def _lines(lines: list[str], title: str) -> None:
    if not lines:
        return
    if title:
        ui.label(title).classes("console-group mt-3")
    for line in lines:
        ui.label(str(line)).classes("console-help")


def _finished(body: Any, buttons: Any, dialog: Any, answer: dict) -> None:
    """An action that ran and is done, with whatever it wants to say about it."""
    body.clear()
    buttons.clear()
    with body:
        said = str(answer.get("message") or t("word.done"))
        ui.label(said).classes("console-help")
        facts = [(one[0], one[1]) for one in (answer.get("summary") or [])]
        if facts:
            panel.facts(ui, facts)
    with buttons:
        ui.button(t("word.close"), icon=verbs.CLOSE,
                on_click=lambda: dialog.submit(True)).props("flat no-caps")


def _compare(rows: list[dict]) -> None:
    """Expected beside actual, and what is short.

    Every row, including the ones that agree: a line that appears only when something
    went wrong makes a clean import read as a report with things missing from it.
    """
    entries = []
    for row in rows:
        want, got = int(row.get("expected", 0)), int(row.get("actual", 0))
        short = want - got
        entries.append((str(row.get("label") or row.get("key") or ""),
                        _counts(want, got, short)))
    panel.facts(ui, entries)


def _counts(want: int, got: int, short: int) -> Any:
    def draw() -> None:
        with ui.row().classes("items-center gap-2"):
            ui.label(str(got)).classes("console-fact-value")
            if short:
                # The number alone cannot say whether it is right. What was expected is
                # what makes a shortfall visible without anybody counting.
                ui.label(t("console.ext_action.of_expected", want=want)).classes("console-help")
                ui.label(t("console.ext_action.short", short=(short))).classes(
                    "console-member-chip console-chip-warn")
    return draw


def _wait() -> None:
    import time

    time.sleep(POLL_SECONDS)


def _report(body: Any, job: dict) -> None:
    """What happened, once it has. The counts, and every game that did not come across -
    an import that says only "done" leaves somebody to find the gaps themselves."""
    body.clear()
    with body:
        if job.get("state") == "failed":
            ui.label(str(job.get("error") or t("console.ext_action.not_finish"))) \
                .classes("console-help")
            return
        result = job.get("result") or {}
        compared = list(result.get("against") or [])
        if compared:
            _compare(compared)
        elif result:
            panel.facts(ui, [(str(key).replace("_", " ").capitalize(), str(value))
                             for key, value in result.items()
                             if isinstance(value, (int, str))])
        held = list(result.get("already_here") or [])
        if held:
            ui.label(t("console.ext_action.already",
                    len=(len(held)))).classes("console-group mt-3")
            for row in held[:20]:
                ui.label(t("console.ext_action.matched",
                           value=(row.get('name') or row.get('key')),
                           value2=(row.get('how') or 'name'))).classes("console-help")
            if len(held) > 20:
                ui.label(t("console.ext_action.more",
                        value=(len(held) - 20))).classes("console-help")
        missed = [row for row in (result.get("rows") or []) if row.get("error")]
        if missed:
            ui.label(t("console.ext_action.not_come_across",
                    len=(len(missed)))).classes("console-group mt-3")
            for row in missed[:20]:
                ui.label(f"{row.get('name') or row.get('key')} - {row['error']}") \
                    .classes("console-help")
            if len(missed) > 20:
                ui.label(t("console.ext_action.more",
                        value=(len(missed) - 20))).classes("console-help")
