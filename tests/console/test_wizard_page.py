"""The page host's own drawing: the same step body and footer the dialog draws, with
the step list beside them instead of above, and the current step kept in the address -
all proven with a fake flow, since nothing in the tree hosts a real one yet."""

from __future__ import annotations

import asyncio
import unittest
from collections.abc import Callable
from typing import Any
from unittest import mock

from nicegui import core, ui

from console import wizard
from tests.support.clicks import said

# Made at import, outside any task, where NiceGUI still hands out the script's own page.
_PAGE = ui.element()


def _calls(*, first: dict[str, Any],
          on_check: Callable[[dict[str, Any], str], dict[str, Any]] | None = None,
          on_act: Callable[[str, dict[str, Any], str], dict[str, Any]] | None = None,
          on_goto: Callable[[str], dict[str, Any]] | None = None,
          on_run: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
          seen_first: list[str | None] | None = None) -> wizard.Calls:
    async def first_call(step: str | None = None) -> dict:
        if seen_first is not None:
            seen_first.append(step)
        if step is None:
            return first
        if on_goto is None:
            raise AssertionError("this flow answers no step by key")
        return on_goto(step)

    async def check(values: dict[str, Any], step: str) -> dict:
        if on_check is None:
            raise AssertionError("this flow answers no check")
        return on_check(values, step)

    async def act(key: str, values: dict[str, Any], step: str) -> dict:
        if on_act is None:
            raise AssertionError("this flow answers no act")
        return on_act(key, values, step)

    async def run(values: dict[str, Any]) -> dict:
        return on_run(values) if on_run is not None else {"ok": True}

    async def job(job_id: str) -> dict:
        raise AssertionError("no test here drives a job")

    return wizard.Calls(first_call, check, act, run, job)


async def _settled() -> None:
    for _ in range(8):
        await asyncio.sleep(0)


async def _opened(calls: wizard.Calls, *, step: str | None = None) -> ui.element:
    """The page, drawn past its first render. Unlike the dialog host, `open_page`
    returns once it has drawn rather than staying open, so there is no task to hold."""
    was = set(_PAGE.client.layout.descendants())
    with _PAGE:
        await wizard.open_page(label="Test", calls=calls, under="test.action", step=step)
    await _settled()
    return next(one for one in set(_PAGE.client.layout.descendants()) - was
               if "console-wizard-page" in one.classes)


def _forward(page: ui.element) -> ui.button:
    return next(one for one in page.descendants()
               if isinstance(one, ui.button) and wizard._FORWARD in one.classes)


def _labelled(page: ui.element, text: str) -> ui.label:
    return next(one for one in page.descendants()
               if isinstance(one, ui.label) and one.text == text)


def _ran(run: Callable[[], Any]) -> Any:
    """`run`, with NiceGUI's loop set so a handler's own task is started at all."""
    async def inside() -> Any:
        was = core.loop
        core.loop = asyncio.get_running_loop()
        try:
            return await run()
        finally:
            core.loop = was

    return asyncio.run(inside())


class NotReadyTests(unittest.TestCase):
    def test_a_plain_step_held_not_ready_disables_next_and_says_why(self) -> None:
        first = {"step": "one", "fields": [], "ready": False, "reason": "Pick something first"}

        async def run() -> tuple[bool, str]:
            page = await _opened(_calls(first=first))
            disabled = _forward(page)._props.get("disable", False)
            reason = _labelled(page, "Pick something first").text
            return disabled, reason

        disabled, reason = _ran(run)
        self.assertEqual((True, "Pick something first"), (disabled, reason))


class ActTests(unittest.TestCase):
    def test_pressing_an_act_asks_for_it_by_key_and_redraws_the_same_step(self) -> None:
        first = {"step": "one", "fields": [], "acts": [{"key": "connect", "label": "Connect"}],
                 "ready": False, "reason": "Not connected"}
        redrawn = {"step": "one", "fields": [], "notes": ["Connected"], "ready": True}
        acted: list[tuple[str, str]] = []

        def acting(key: str, values: dict[str, Any], step: str) -> dict[str, Any]:
            acted.append((key, step))
            return redrawn

        async def run() -> tuple[list[tuple[str, str]], str, bool]:
            page = await _opened(_calls(first=first, on_act=acting))
            said(next(one for one in page.descendants()
                     if isinstance(one, ui.button) and one.text == "Connect"), "click")
            await _settled()
            note = _labelled(page, "Connected").text
            disabled = _forward(page)._props.get("disable", False)
            return acted, note, disabled

        found, note, disabled = _ran(run)
        self.assertEqual([("connect", "one")], found)
        self.assertEqual("Connected", note)
        self.assertFalse(disabled)


class StepListTests(unittest.TestCase):
    def test_no_steps_key_draws_no_list(self) -> None:
        first = {"step": "one", "fields": []}

        async def run() -> bool:
            page = await _opened(_calls(first=first))
            return any("console-wizard-step--here" in one.classes
                      or "console-wizard-steps" in one.classes for one in page.descendants())

        self.assertFalse(_ran(run))

    def test_a_done_step_is_a_link_and_an_open_one_is_not(self) -> None:
        first = {"step": "two", "fields": [],
                 "steps": [{"key": "one", "label": "One", "done": True},
                          {"key": "two", "label": "Two", "done": False},
                          {"key": "three", "label": "Three", "done": False}]}

        async def run() -> tuple[list[str], list[str]]:
            page = await _opened(_calls(first=first))
            linked = [one.text for one in page.descendants()
                     if isinstance(one, ui.label) and "console-link" in one.classes]
            current = [one.text for one in page.descendants()
                      if isinstance(one, ui.label) and "console-wizard-step--here" in one.classes]
            return linked, current

        linked, current = _ran(run)
        self.assertEqual(["One"], linked)
        self.assertEqual(["Two"], current)

    def test_clicking_a_done_step_reopens_it_by_key(self) -> None:
        first = {"step": "two", "fields": [],
                 "steps": [{"key": "one", "label": "One", "done": True},
                          {"key": "two", "label": "Two", "done": False}]}
        reopened = {"step": "one", "fields": [], "notes": ["Back on one"],
                   "steps": first["steps"]}
        asked: list[str] = []

        def going(key: str) -> dict[str, Any]:
            asked.append(key)
            return reopened

        async def run() -> tuple[list[str], str]:
            page = await _opened(_calls(first=first, on_goto=going))
            said(_labelled(page, "One"), "click")
            await _settled()
            note = _labelled(page, "Back on one").text
            return asked, note

        asked, note = _ran(run)
        self.assertEqual(["one"], asked)
        self.assertEqual("Back on one", note)


class TitleFocusTests(unittest.TestCase):
    def test_a_step_transition_focuses_the_title_not_a_field(self) -> None:
        first = {"step": "one", "fields": [{"key": "name", "type": "string", "label": "Name"}]}
        second = {"step": "two", "fields": []}

        async def run() -> list[str]:
            with mock.patch.object(ui, "run_javascript") as js:
                page = await _opened(_calls(first=first, on_check=lambda v, s: second))
                heading = next(one for one in page.descendants()
                              if "console-dialog-title" in one.classes)
                js.reset_mock()
                said(_forward(page), "click")
                await _settled()
                calls_seen = [call.args[0] for call in js.call_args_list]
            return [text for text in calls_seen if f"c{heading.id}" in text]

        self.assertTrue(_ran(run))

    def test_an_act_redraw_focuses_the_field_not_the_title(self) -> None:
        first = {"step": "one", "fields": [{"key": "name", "type": "string", "label": "Name"}],
                 "acts": [{"key": "go", "label": "Go"}]}
        redrawn = {"step": "one", "fields": [{"key": "name", "type": "string", "label": "Name"}]}

        async def run() -> bool:
            with mock.patch.object(ui, "run_javascript") as js:
                page = await _opened(_calls(first=first, on_act=lambda k, v, s: redrawn))
                heading = next(one for one in page.descendants()
                              if "console-dialog-title" in one.classes)
                js.reset_mock()
                said(next(one for one in page.descendants()
                         if isinstance(one, ui.button) and one.text == "Go"), "click")
                await _settled()
                calls_seen = [call.args[0] for call in js.call_args_list]
            return any(f"c{heading.id}" in text for text in calls_seen)

        self.assertFalse(_ran(run))


class AddressTests(unittest.TestCase):
    def test_opening_writes_the_first_step_into_the_address(self) -> None:
        first = {"step": "one", "fields": []}

        async def run() -> list[str]:
            with mock.patch.object(ui, "run_javascript") as js:
                await _opened(_calls(first=first))
                return [call.args[0] for call in js.call_args_list]

        calls_seen = _ran(run)
        self.assertTrue(any("replaceState" in text and '"one"' in text
                            for text in calls_seen))

    def test_pressing_next_writes_the_new_step_into_the_address(self) -> None:
        first = {"step": "one", "fields": []}
        second = {"step": "two", "fields": []}

        async def run() -> list[str]:
            with mock.patch.object(ui, "run_javascript") as js:
                page = await _opened(_calls(first=first, on_check=lambda v, s: second))
                js.reset_mock()
                said(_forward(page), "click")
                await _settled()
                return [call.args[0] for call in js.call_args_list]

        calls_seen = _ran(run)
        self.assertTrue(any("replaceState" in text and '"two"' in text
                            for text in calls_seen))

    def test_a_step_given_at_open_is_asked_for_by_key_not_started_fresh(self) -> None:
        resumed = {"step": "two", "fields": [], "notes": ["Resumed"]}
        seen: list[str | None] = []

        async def run() -> tuple[list[str | None], str]:
            page = await _opened(_calls(first={"step": "one", "fields": []},
                                        on_goto=lambda key: resumed, seen_first=seen),
                                 step="two")
            note = _labelled(page, "Resumed").text
            return seen, note

        seen, note = _ran(run)
        self.assertEqual(["two"], seen)
        self.assertEqual("Resumed", note)


class RunTests(unittest.TestCase):
    def test_finishing_without_a_job_draws_the_message_and_no_close_button(self) -> None:
        first = {"step": "one", "fields": [], "summary": [["Ready"]]}

        async def run() -> tuple[str, bool]:
            page = await _opened(_calls(first=first,
                                        on_run=lambda values: {"message": "All set"}))
            said(_forward(page), "click")
            await _settled()
            message = _labelled(page, "All set").text
            has_close = any(isinstance(one, ui.button) and one.text == "Close"
                            for one in page.descendants())
            return message, has_close

        message, has_close = _ran(run)
        self.assertEqual("All set", message)
        self.assertFalse(has_close)


if __name__ == "__main__":
    unittest.main()
