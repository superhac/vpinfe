"""The shared stepping control: Back, Next, Run and the summary, for any flow that asks
its questions in stages rather than all at once.

A flow answers every call with a step, and how many there are is read off that, never
declared: no fields means press it and it happens, fields mean fill them in first, and a
`summary` means the last step before Run. A flow reaches this through `Calls`, its own
four calls already bound to wherever it answers from - HTTP for an extension
(`console/ext_action.py`), or nothing at all for a flow with no boundary to cross.
"""

from __future__ import annotations

import json
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
    "choice": "panel.choice",
    "number": "panel.number",
}

# The forward-verb button's own marker, so a keypress can find whichever step's button is
# current without rebinding a listener every time the step redraws.
_FORWARD = "console-wizard-forward"


@dataclass
class Calls:
    """A flow's own four calls: the first step (or, given a key, a done step reopened),
    the check that answers the next one, an act that answers the same one, and the run.
    `job` polls a run that answered with a `job_id` instead of finishing."""
    first: Callable[[str | None], Awaitable[dict]]
    check: Callable[[dict[str, Any], str], Awaitable[dict]]
    act: Callable[[str, dict[str, Any], str], Awaitable[dict]]
    run: Callable[[dict[str, Any]], Awaitable[dict]]
    job: Callable[[str], Awaitable[dict]]


class Walk:
    """The stepping loop: the current answer, its history, and the values gathered so
    far. Back, Next, an act, reopening a done step, and Run are decided here, never
    drawn, so the rules hold without a browser.
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

    async def act(self, key: str) -> dict:
        # No `ready` gate: an act is often what a step needs pressed to become ready
        # (Connect) rather than something it is withheld until.
        self.step = await self.calls.act(key, self.values, str(self.step.get("step") or ""))
        return self.step

    async def goto(self, step_key: str) -> dict:
        # Through `first`, not `check` - reopening a done step asks nothing new of it,
        # the way a page reload does. History is untouched; Back still goes where it
        # pointed before the jump.
        self.step = await self.calls.first(step_key)
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
        elif kind == "choice":
            options = [(str(one[0]), str(one[1]), str(one[2]) if len(one) > 2 else "")
                      for one in field.get("choices") or []]

            def caught(control: Any, key: str = key) -> None:
                held[key] = ("choice", control)
                refused(control, key)

            entries.append((label, panel.choice(
                options, str(values.get(key) or ""),
                changed(key, lambda value: str(value or "")), on_control=caught)))
        elif kind == "number":
            def caught(control: Any, key: str = key) -> None:
                held[key] = ("number", control)
                refused(control, key)

            entries.append((label, panel.number(
                values.get(key), changed(key, lambda value: value),
                unit=str(field.get("unit") or ""),
                low=field.get("min"), high=field.get("max"),
                whole=False, on_control=caught)))
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
        elif kind == "number":
            # Not stringified: a number field holds None or a number, and `str(None)`
            # would write the word "None" into an answer nobody typed.
            values[key] = control.value
        else:
            values[key] = str(control.value or "")


def _focus_now(control: Any) -> None:
    """A step's own first field, focused directly rather than through a `show` event.
    The dialog host calls this from its second step on; the page host, with no `show`
    event of its own, calls it for every step. Steps down to a nested `input`/`textarea`
    the same way `frame.focus` does.
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


def _focus_title(control: Any) -> None:
    """Steps to the label itself, which needs `tabindex=-1` to take focus at all - a
    plain label is not in the tab order by default."""
    ui.run_javascript(f"""
        (() => {{
          const el = document.getElementById('c{control.id}');
          if (el) el.focus();
        }})()
    """)


def _enter_presses_forward(root_id: int) -> str:
    """Enter anywhere in `root_id` but a textarea presses whichever step's forward
    button is current."""
    return f"""
        (() => {{
          const root = document.getElementById('c{root_id}');
          if (!root) return;
          root.addEventListener('keyup', (event) => {{
            if (event.key !== 'Enter' || event.target.tagName === 'TEXTAREA') {{
              return;
            }}
            const btn = root.querySelector('.{_FORWARD}');
            if (btn && !btn.disabled) btn.click();
          }});
        }})()
    """


def _sync_step(step_key: str) -> None:
    """Writes `step` into the address; every other query parameter is left alone."""
    ui.run_javascript(f"""
        (() => {{
          const url = new URL(location.href);
          const step = {json.dumps(step_key)};
          if (step) url.searchParams.set('step', step); else url.searchParams.delete('step');
          history.replaceState(null, '', url.pathname + url.search);
        }})()
    """)


def _step_list(steps: list[dict[str, Any]], current: str, go: Callable[[str], Any]) -> None:
    """The path as it stands, named steps only. Only a `done` step answers a click - a
    step still ahead has nothing to reopen, and clicking it would say otherwise."""
    with ui.row().classes("console-wizard-steps gap-3 px-3 mb-2"):
        for entry in steps:
            key = str(entry.get("key") or "")
            text = str(entry.get("label") or key)
            if key == current:
                ui.label(text).classes("console-wizard-step--here")
            elif entry.get("done"):
                ui.label(text).classes("console-link").on("click", lambda key=key: go(key))
            else:
                ui.label(text).classes("console-help")


def _acts(acts: list[dict[str, Any]], go: Callable[[str], Any]) -> None:
    """An act is `{key, label}`; the flow draws no icon of its own, so this carries the
    same one the wizard's own confirm does for the same reason.
    """
    with ui.row().classes("gap-2 px-3 mb-2"):
        for act in acts:
            key = str(act.get("key") or "")
            label = str(act.get("label") or key)
            panel.action(label, lambda key=key: go(key), icon=verbs.RUN,
                        hint=str(act.get("hint") or label))()


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
    walk = Walk(calls, await calls.first(None))
    client = ApiClient()
    held: dict[str, tuple[str, Any]] = {}
    opened = False
    current_key = ""

    with frame.opened("", wide=True, persistent=True,
                      classes="console-import-card") as dialog:
        heading = ui.label("").classes("console-dialog-title").props("tabindex=-1")
        body = ui.column().classes("w-full gap-0 console-import-body")
        buttons = frame.footer()

        def draw(found: dict) -> None:
            nonlocal held, opened, current_key
            fresh = current_key != str(found.get("step") or "")
            current_key = str(found.get("step") or "")
            heading.text = str(found.get("title") or label)
            body.clear()
            buttons.clear()
            summary = found.get("summary")
            with body:
                if found.get("steps"):
                    _step_list(list(found["steps"]), current_key, _goto)
                if found.get("help"):
                    ui.label(str(found["help"])).classes("console-help px-3 mb-2")
                if summary:
                    _summary(summary)
                held = _controls(list(found.get("fields") or []), walk.values,
                                 client=client, errors=dict(found.get("errors") or {}))
                if found.get("acts"):
                    _acts(list(found["acts"]), _act)
                _lines(list(found.get("notes") or []),
                       t("console.ext_action.worth_knowing") if summary else "")
                if not found.get("ready", True):
                    ui.label(str(found.get("reason") or "")).classes("console-help px-3")
            with buttons:
                if walk.history:
                    frame.quiet(t("word.back"), _back, icon=verbs.BACK)
                else:
                    frame.cancel(lambda: dialog.submit(False))
                if summary:
                    go = frame.answer(str(found.get("confirm") or label or t("word.run")),
                                       _start, icon=verbs.RUN)
                else:
                    go = frame.answer(t("word.next"), _next, icon=verbs.NEXT)
                if not found.get("ready", True):
                    go.disable()
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
                dialog.on("show", lambda: ui.run_javascript(
                    _enter_presses_forward(dialog.id)))
            elif fresh:
                _focus_title(heading)
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
        async def _act(key: str) -> None:
            _sync(walk.values, held)
            try:
                found = await walk.act(key)
            except Exception as exc:  # noqa: BLE001
                ui.notify(t("console.ext_action.could_not_go_on"), caption=why(exc),
                          type="negative")
                return
            draw(found)

        @on_page
        async def _goto(step_key: str) -> None:
            _sync(walk.values, held)
            try:
                found = await walk.goto(step_key)
            except Exception as exc:  # noqa: BLE001
                ui.notify(t("console.ext_action.could_not_go_on"), caption=why(exc),
                          type="negative")
                return
            draw(found)

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
                await _watch(calls.job, job_id, body=body, buttons=buttons, heading=heading,
                            under=under, close=lambda: dialog.submit(True))
                return
            if started.get("ok") is False:
                ui.notify(str(started.get("reason") or t("console.ext_action.not_run")),
                          type="negative")
                return
            # Finished already. Some actions are one call and a sentence, and making
            # those wear a progress bar would be theatre.
            _finished(body, buttons, lambda: dialog.submit(True), started)

        draw(walk.step)

    await dialog


async def open_page(*, label: str, calls: Calls, under: str, step: str | None = None) -> None:
    """Run one flow as a Console view: the same steps the dialog host walks, drawn
    with the step list beside the step's own content instead of above it, and the
    current step kept in the address so a reload comes back to it.

    `step` is the key the caller read off its own address, if any - the flow answers
    `GET` with it, the way a done step reopens. Answering `None` gets its first step,
    same as the dialog host.
    """
    walk = Walk(calls, await calls.first(step))
    client = ApiClient()
    held: dict[str, tuple[str, Any]] = {}
    opened = False
    current_key = ""

    with ui.column().classes("w-full gap-0 console-wizard-page") as page:
        heading = ui.label("").classes("console-dialog-title").props("tabindex=-1")
        body = ui.row().classes("w-full gap-4 items-start console-wizard-page-body")
        buttons = frame.footer()

        def draw(found: dict) -> None:
            nonlocal held, opened, current_key
            fresh = current_key != str(found.get("step") or "")
            current_key = str(found.get("step") or "")
            heading.text = str(found.get("title") or label)
            body.clear()
            buttons.clear()
            summary = found.get("summary")
            with body:
                if found.get("steps"):
                    with ui.column().classes("console-wizard-page-steps"):
                        _step_list(list(found["steps"]), current_key, _goto)
                with ui.column().classes("w-full min-w-0 gap-0 console-wizard-page-content"):
                    if found.get("help"):
                        ui.label(str(found["help"])).classes("console-help px-3 mb-2")
                    if summary:
                        _summary(summary)
                    held = _controls(list(found.get("fields") or []), walk.values,
                                     client=client, errors=dict(found.get("errors") or {}))
                    if found.get("acts"):
                        _acts(list(found["acts"]), _act)
                    _lines(list(found.get("notes") or []),
                          t("console.ext_action.worth_knowing") if summary else "")
                    if not found.get("ready", True):
                        ui.label(str(found.get("reason") or "")).classes("console-help px-3")
            with buttons:
                if walk.history:
                    frame.quiet(t("word.back"), _back, icon=verbs.BACK)
                if summary:
                    go = frame.answer(str(found.get("confirm") or label or t("word.run")),
                                       _start, icon=verbs.RUN)
                else:
                    go = frame.answer(t("word.next"), _next, icon=verbs.NEXT)
                if not found.get("ready", True):
                    go.disable()
            go.classes(_FORWARD)
            _sync_step(current_key)
            # held keeps insertion order, so its first entry is the step's first field.
            first = next(iter(held.values()), None)
            control = first[1] if first else None
            if not opened:
                opened = True
                if control is not None:
                    _focus_now(control)
                # Bound once: a listener added on every redraw would pile up on the
                # same page element, one more for every step visited.
                ui.run_javascript(_enter_presses_forward(page.id))
            elif fresh:
                _focus_title(heading)
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
        async def _act(key: str) -> None:
            _sync(walk.values, held)
            try:
                found = await walk.act(key)
            except Exception as exc:  # noqa: BLE001
                ui.notify(t("console.ext_action.could_not_go_on"), caption=why(exc),
                          type="negative")
                return
            draw(found)

        @on_page
        async def _goto(step_key: str) -> None:
            _sync(walk.values, held)
            try:
                found = await walk.goto(step_key)
            except Exception as exc:  # noqa: BLE001
                ui.notify(t("console.ext_action.could_not_go_on"), caption=why(exc),
                          type="negative")
                return
            draw(found)

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
                # No `close`: nothing here is a dialog to dismiss.
                await _watch(calls.job, job_id, body=body, buttons=buttons, heading=heading,
                            under=under, close=None)
                return
            if started.get("ok") is False:
                ui.notify(str(started.get("reason") or t("console.ext_action.not_run")),
                          type="negative")
                return
            _finished(body, buttons, None, started)

        draw(walk.step)


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


async def _watch(poll: Callable[[str], Awaitable[dict]], job_id: str, *, body: Any,
                 buttons: Any, heading: Any, under: str,
                 close: Callable[[], Any] | None) -> None:
    """Poll a run that answered with a `job_id` instead of finishing, then draw what
    it came to. `close` is the dismiss button's own action; a page has nothing to
    dismiss to and draws no button for it.
    """
    body.clear()
    buttons.clear()
    with body, ui.column().classes("w-full gap-1 px-3"):
        bar = ui.linear_progress(value=0, show_value=False).classes("w-full")
        said = ui.label(t("console.ext_action.working")).classes("console-help")
    stop = None
    if close is not None:
        with buttons:
            stop = frame.cancel(close, t("word.close"))
            stop.disable()

    while True:
        job = await poll(job_id)
        bar.value = int(job.get("pct") or 0) / 100
        said.text = str(job.get("message") or t("console.ext_action.working"))
        if str(job.get("state")) not in ("running", "queued"):
            break
        await run.io_bound(_wait)

    if stop is not None:
        stop.enable()
    heading.text = t("console.ext_action.what_happened") if job.get("state") == "done" \
        else t("console.ext_action.not_finish")
    _report(body, job, under)


def _finished(body: Any, buttons: Any, close: Callable[[], Any] | None, answer: dict) -> None:
    """A flow that ran and is done, with whatever it wants to say about it. `close` is
    the dismiss action, drawn only where there is one."""
    body.clear()
    buttons.clear()
    with body:
        said = str(answer.get("message") or t("word.done"))
        ui.label(said).classes("console-help px-3")
        facts = [(one[0], one[1]) for one in (answer.get("summary") or [])]
        if facts:
            panel.facts(ui, facts)
    if close is not None:
        with buttons:
            frame.cancel(close, t("word.close"))


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
