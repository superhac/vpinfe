"""The walk's own rules: what Back, Next and Run each do, without a browser.

`errors`, `acts` and `steps` are not built yet; these are the rules a plain `Walk`
already has to hold on its own, with a fake `Calls` standing in for HTTP.
"""

from __future__ import annotations

import unittest
from typing import Any

from console import wizard


def _calls(steps: dict[str, dict[str, Any]], *,
          checked: list[str] | None = None,
          ran: list[dict[str, Any]] | None = None) -> wizard.Calls:
    """A flow with a canned next step for each one `Walk` might leave. `Walk` never
    calls `first` itself - its caller already holds the answer - so it is left to fail
    loudly if that ever changes."""
    async def first() -> dict:
        raise AssertionError("Walk does not ask for its own first step")

    async def check(values: dict[str, Any], step: str) -> dict:
        if checked is not None:
            checked.append(step)
        return steps[step]

    async def run(values: dict[str, Any]) -> dict:
        if ran is not None:
            ran.append(dict(values))
        return {"ok": True}

    async def job(job_id: str) -> dict:
        raise AssertionError("no run in these tests answers with a job")

    return wizard.Calls(first, check, run, job)


class BackTests(unittest.IsolatedAsyncioTestCase):
    async def test_back_pops_the_history_without_asking_again(self) -> None:
        checked: list[str] = []
        first = {"step": "one"}
        walk = wizard.Walk(_calls({"one": {"step": "two"}}, checked=checked), first)

        await walk.next()
        again = walk.back()

        self.assertEqual(checked, ["one"])
        self.assertIs(again, first)


class SelfAnswerTests(unittest.IsolatedAsyncioTestCase):
    async def test_a_step_that_answers_with_itself_is_not_pushed(self) -> None:
        first = {"step": "one"}
        refused = {"step": "one", "errors": {"path": "not reachable"}}
        walk = wizard.Walk(_calls({"one": refused}), first)

        found = await walk.next()

        self.assertIs(found, refused)
        self.assertEqual(walk.history, [])
        with self.assertRaises(IndexError):
            walk.back()


class ReadyTests(unittest.IsolatedAsyncioTestCase):
    async def test_not_ready_holds_next(self) -> None:
        checked: list[str] = []
        first = {"step": "one", "ready": False}
        walk = wizard.Walk(_calls({"one": {"step": "two"}}, checked=checked), first)

        found = await walk.next()

        self.assertEqual(checked, [])
        self.assertIs(found, first)

    async def test_not_ready_holds_run(self) -> None:
        ran: list[dict] = []
        first = {"step": "summary", "summary": [], "ready": False}
        walk = wizard.Walk(_calls({}, ran=ran), first)

        found = await walk.run()

        self.assertEqual(ran, [])
        self.assertIs(found, first)

    async def test_ready_lets_next_and_run_through(self) -> None:
        ran: list[dict] = []
        checked: list[str] = []
        step = {"step": "one", "ready": True}
        walk = wizard.Walk(_calls({"one": {"step": "two"}}, checked=checked, ran=ran), step)

        await walk.next()

        self.assertEqual(checked, ["one"])

        summary = {"step": "summary", "summary": [], "ready": True}
        walk = wizard.Walk(_calls({}, ran=ran), summary)
        await walk.run()

        self.assertEqual(len(ran), 1)

    async def test_ready_absent_is_the_same_as_ready(self) -> None:
        """`ready` is optional; a step that never mentions it is not held."""
        checked: list[str] = []
        first = {"step": "one"}
        walk = wizard.Walk(_calls({"one": {"step": "two"}}, checked=checked), first)

        await walk.next()

        self.assertEqual(checked, ["one"])


if __name__ == "__main__":
    unittest.main()
