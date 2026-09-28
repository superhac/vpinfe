"""The shared stepping control: Back, Next, Run and the summary, for any flow that asks
its questions in stages rather than all at once.

A flow answers every call with a step, and how many there are is read off that, never
declared: no fields means press it and it happens, fields mean fill them in first, and a
`summary` means the last step before Run. A flow reaches this through `Calls`, its own
three calls already bound to wherever it answers from - HTTP for an extension
(`console/ext_action.py`), or nothing at all for a flow with no boundary to cross.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from typing import Any

from nicegui import run, ui

from common.failures import why
from common.i18n import literal_or, t
from console import dialog as frame
from console import panel, verbs
from console.api import ApiClient
from console.on_page import on_page

# How often to ask a running job how it is doing. A job here is minutes of copying, so a
# tighter loop would be a question asked hundreds of times for the same answer.
POLL_SECONDS = 1.0

# What a field's `type` draws, in the Console's own grammar. Checked against the field
# table an extension author reads (docs/extensions.md) - the two must agree.
FIELD_TYPES = {
    "string": "panel.field",
    "path": "panel.path_field",
    "select": "panel.select",
    "multi": "panel.multi_select",
    "switch": "panel.switch",
}

# The forward-verb button's own marker, so a keypress can find whichever step's button is
# current without rebinding a listener every time the step redraws.
_FORWARD = "console-wizard-forward"


@dataclass
class Calls:
    """A flow's own three calls: the first step, the check that answers the next one,
    and the run. `job` polls a run that answered with a `job_id` instead of finishing."""
    first: Callable[[], Awaitable[dict]]
    check: Callable[[dict[str, Any], str], Awaitable[dict]]
    run: Callable[[dict[str, Any]], Awaitable[dict]]
    job: Callable[[str], Awaitable[dict]]


class Walk:
    """The stepping loop: the current answer, its history, and the values gathered so
    far. Back, Next and Run are decided here, never drawn, so the rules hold without a
    browser.
    """

    def __init__(self, calls: Calls, first: dict) -> None:
        self.calls = calls
        self.step = first
        self.history: list[dict] = []
        self.values: dict[str, Any] = {}

    async def next(self) -> dict:
        if not self.step.get("ready", True):
            return self.step
        found = await self.calls.check(self.values, str(self.step.get("step") or ""))
        # A step that answers with itself is the same question asked again, not a new
        # one. Remembering it would make Back go nowhere.
        if str(found.get("step") or "") != str(self.step.get("step") or ""):
            self.history.append(self.step)
        self.step = found
        return found

    def back(self) -> dict:
        self.step = self.history.pop()
        return self.step

    async def run(self) -> dict:
        if not self.step.get("ready", True):
            return self.step
        return await self.calls.run(self.values)


def _controls(fields: list[dict], values: dict[str, Any], *,
             client: ApiClient, errors: dict[str, Any]) -> dict[str, tuple[str, Any]]:
    """Draw what the task asked for, in the Console's own grammar.

    Returns each field's own kind and control, keyed by its key - what the dialog host
    reads back before Next, Back or Run (a path field only pushes what it holds on its
    own check, and Next can come sooner than that), and where it sends focus and a
    refusal from `errors`.
    """
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

    def refused(control: Any, key: str) -> None:
        said = errors.get(key)
        if not said:
            return
        text, detail = _worded(said)
        control.props["error"] = True
        control.props["error-message"] = text
        if detail:
            control.tooltip(detail)

    held: dict[str, tuple[str, Any]] = {}
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

            def caught(control: Any, key: str = key) -> None:
                held[key] = ("multi", control)
                refused(control, key)

            entries.append((label, panel.multi_select(
                choices, list(values.get(key) or []),
                changed(key, lambda value: list(value or [])), on_control=caught)))
        elif kind == "select":
            choices = {str(one[0]): str(one[1]) for one in field.get("choices") or []}

            def caught(control: Any, key: str = key) -> None:
                held[key] = ("select", control)
                refused(control, key)

            entries.append((label, panel.select(
                choices, str(values.get(key) or ""),
                changed(key, lambda value: str(value or "")), on_control=caught)))
        elif kind == "switch":
            def caught(control: Any, key: str = key) -> None:
                held[key] = ("switch", control)
                refused(control, key)

            entries.append((label, panel.switch(
                bool(values.get(key)), changed(key, bool), on_control=caught)))
        elif kind == "path":
            def draw_path(field: dict = field, key: str = key) -> None:
                def synced(_state: str, said: str) -> str:
                    # The 0.3s check is a poll, not a push on every keystroke; Next
                    # reads the control directly instead of waiting on it.
                    values[key] = said
                    return ""

                control = panel.path_field(
                    str(field.get("placeholder") or ""),
                    wants=str(field.get("wants") or "dir"),
                    value=str(values.get(key) or ""), width="w-full",
                    on_checked=synced, browse=client.folders)
                held[key] = ("path", control)
                refused(control, key)

            entries.append((label, draw_path))
        else:
            def caught(control: Any, key: str = key) -> None:
                held[key] = ("string", control)
                refused(control, key)

            entries.append((label, panel.field(
                str(values.get(key) or ""), typed(key), on_control=caught)))
        if field.get("help"):
            entries.append((panel.ASIDE, _aside(str(field["help"]))))
    panel.facts(ui, entries)
    return held


def _sync(values: dict[str, Any], held: dict[str, tuple[str, Any]]) -> None:
    """What is on screen now, back into the walk's values."""
    for key, (kind, control) in held.items():
        if kind == "multi":
            values[key] = list(control.value or [])
        elif kind == "switch":
            values[key] = bool(control.value)
        else:
            values[key] = str(control.value or "")


def _focus_now(control: Any) -> None:
    """A later step's own first field - the dialog's `show` already ran once, for the
    first step, so `frame.focus`'s own binding never fires again. Steps down to a nested
    `input`/`textarea` the same way `frame.focus` does.
    """
    ui.run_javascript(f"""
        (() => {{
          let tries = 0;
          const go = () => {{
            const field = document.getElementById('c{control.id}');
            if (!field) {{ if (++tries < 40) setTimeout(go, 25); return; }}
            const target = field.matches('input,textarea') ? field
              : (field.querySelector('input,textarea') || field);
            target.focus();
          }};
          go();
        }})()
    """)


def _aside(text: str) -> Any:
    def draw() -> None:
        ui.label(text).classes("console-help")
    return draw


async def open_dialog(*, label: str, calls: Calls, under: str) -> None:
    """Run one flow in the dialog host: ask what it asks, in as many steps as it asks
    it, then do it.

    The flow decides what to ask next from what it has been given so far, and says so
    by answering with another step. This keeps everything answered and hands the whole
    lot back each time, along with the step being left, so a step is a question rather
    than a session - nothing is held between requests that could be stale by the time it
    is used, and going Back and forward again asks the same questions in the same order
    rather than jumping over the ones already answered.

    It stops asking when it answers with a summary instead of fields. `under` is where
    a run's report belongs in the flow's own catalog.
    """
    walk = Walk(calls, await calls.first())
    client = ApiClient()
    held: dict[str, tuple[str, Any]] = {}
    opened = False

    with frame.opened("", wide=True, persistent=True,
                      classes="console-import-card") as dialog:
        heading = ui.label("").classes("console-dialog-title")
        body = ui.column().classes("w-full gap-0 console-import-body")
        buttons = frame.footer()

        def draw(found: dict) -> None:
            nonlocal held, opened
            heading.text = str(found.get("title") or label)
            body.clear()
            buttons.clear()
            summary = found.get("summary")
            with body:
                if found.get("help"):
                    ui.label(str(found["help"])).classes("console-help px-3 mb-2")
                if summary:
                    _summary(summary)
                held = _controls(list(found.get("fields") or []), walk.values,
                                 client=client, errors=dict(found.get("errors") or {}))
                _lines(list(found.get("notes") or []),
                       t("console.ext_action.worth_knowing") if summary else "")
                if summary and not found.get("ready"):
                    ui.label(str(found.get("reason") or "")).classes("console-help px-3")
            with buttons:
                if walk.history:
                    frame.quiet(t("word.back"), _back, icon=verbs.BACK)
                else:
                    frame.cancel(lambda: dialog.submit(False))
                if summary:
                    go = frame.answer(str(found.get("confirm") or label or t("word.run")),
                                       _start, icon=verbs.RUN)
                    if not found.get("ready"):
                        go.disable()
                else:
                    go = frame.answer(t("word.next"), _next, icon=verbs.NEXT)
            go.classes(_FORWARD)
            # held keeps insertion order, so its first entry is the step's first field.
            first = next(iter(held.values()), None)
            control = first[1] if first else None
            if not opened:
                opened = True
                if control is not None:
                    frame.focus(dialog, control)
                # Bound once: a listener added on every redraw would pile up on the
                # same persistent dialog element, one more for every step visited.
                dialog.on("show", lambda: ui.run_javascript(f"""
                    (() => {{
                      const root = document.getElementById('c{dialog.id}');
                      if (!root) return;
                      root.addEventListener('keyup', (event) => {{
                        if (event.key !== 'Enter' || event.target.tagName === 'TEXTAREA') {{
                          return;
                        }}
                        const btn = root.querySelector('.{_FORWARD}');
                        if (btn && !btn.disabled) btn.click();
                      }});
                    }})()
                """))
            elif control is not None:
                _focus_now(control)

        @on_page
        async def _next() -> None:
            _sync(walk.values, held)
            try:
                found = await walk.next()
            except Exception as exc:  # noqa: BLE001
                ui.notify(t("console.ext_action.could_not_go_on"), caption=why(exc),
                          type="negative")
                return
            draw(found)

        def _back() -> None:
            _sync(walk.values, held)
            draw(walk.back())

        @on_page
        async def _start() -> None:
            _sync(walk.values, held)
            try:
                started = await walk.run()
            except Exception as exc:  # noqa: BLE001
                ui.notify(t("said.could_not_start_it"), caption=why(exc), type="negative")
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
            with body, ui.column().classes("w-full gap-1 px-3"):
                bar = ui.linear_progress(value=0, show_value=False).classes("w-full")
                said = ui.label(t("console.ext_action.working")).classes("console-help")
            with buttons:
                close = frame.cancel(lambda: dialog.submit(True), t("word.close"))
                close.disable()

            while True:
                job = await calls.job(job_id)
                bar.value = int(job.get("pct") or 0) / 100
                said.text = str(job.get("message") or t("console.ext_action.working"))
                if str(job.get("state")) not in ("running", "queued"):
                    break
                await run.io_bound(_wait)

            close.enable()
            heading.text = t("console.ext_action.what_happened") if job.get("state") == "done" \
                else t("console.ext_action.not_finish")
            _report(body, job, under)

        draw(walk.step)

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


def _worded(said: Any) -> tuple[str, str]:
    if isinstance(said, dict):
        detail = str(said.get("detail") or "")
        text = str(said.get("text") or "")
        return (text, detail) if text else (detail, "")
    return str(said), ""


def _line(text: str, detail: str) -> None:
    panel.line(text, hint=detail, classes="console-help px-3")


def _lines(lines: list[Any], title: str) -> None:
    if not lines:
        return
    if title:
        panel.facts(ui, [(panel.HEADING, title)])
    for line in lines:
        _line(*_worded(line))


def _finished(body: Any, buttons: Any, dialog: Any, answer: dict) -> None:
    """A flow that ran and is done, with whatever it wants to say about it."""
    body.clear()
    buttons.clear()
    with body:
        said = str(answer.get("message") or t("word.done"))
        ui.label(said).classes("console-help px-3")
        facts = [(one[0], one[1]) for one in (answer.get("summary") or [])]
        if facts:
            panel.facts(ui, facts)
    with buttons:
        frame.cancel(lambda: dialog.submit(True), t("word.close"))


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


def _report(body: Any, job: dict, under: str) -> None:
    """What happened, once it has. The counts, and every game that did not come across -
    a run that says only "done" leaves somebody to find the gaps themselves.

    `under` is the flow's own place in its catalog."""
    body.clear()
    with body:
        if job.get("state") == "failed":
            ui.label(str(job.get("error") or t("console.ext_action.not_finish"))) \
                .classes("console-help px-3")
            return
        result = job.get("result") or {}
        compared = list(result.get("against") or [])
        if compared:
            _compare(compared)
        elif result:
            panel.facts(ui, [(literal_or("", f"{under}.result.{key}", fallback=str(key))[0],
                              str(value))
                             for key, value in result.items()
                             if isinstance(value, (int, str))])
        held = list(result.get("already_here") or [])
        if held:
            panel.facts(ui, [(panel.HEADING, t("console.ext_action.already", count=len(held)))])
            for row in held[:20]:
                name = row.get("name") or row.get("key")
                ui.label(t("console.ext_action.matched", name=name, how=row["how"])
                         if row.get("how") else str(name)).classes("console-help px-3")
            if len(held) > 20:
                ui.label(t("console.ext_action.more",
                        count=len(held) - 20)).classes("console-help px-3")
        missed = [row for row in (result.get("rows") or []) if row.get("error")]
        if missed:
            panel.facts(ui, [(panel.HEADING,
                              t("console.ext_action.not_come_across", count=len(missed)))])
            for row in missed[:20]:
                error, detail = _worded(row["error"])
                _line(t("console.ext_action.missed", name=(row.get("name") or row.get("key")),
                        error=error), detail)
            if len(missed) > 20:
                ui.label(t("console.ext_action.more",
                        count=len(missed) - 20)).classes("console-help px-3")
