"""The walk's own rules: what Back, Next, an act, a jump back to a done step, and Run
each do, without a browser.
"""

from __future__ import annotations

import unittest
from typing import Any

from console import wizard


def _calls(steps: dict[str, dict[str, Any]], *,
          checked: list[str] | None = None,
          acted: list[tuple[str, str]] | None = None,
          reopened: list[str] | None = None,
          ran: list[dict[str, Any]] | None = None) -> wizard.Calls:
    """A flow with a canned next step for each one `Walk` might leave."""
    async def first(step: str | None = None) -> dict:
        if step is None:
            raise AssertionError("Walk does not ask for its own first step")
        if reopened is not None:
            reopened.append(step)
        return steps[step]

    async def check(values: dict[str, Any], step: str) -> dict:
        if checked is not None:
            checked.append(step)
        return steps[step]

    async def act(key: str, values: dict[str, Any], step: str) -> dict:
        if acted is not None:
            acted.append((key, step))
        return steps[step]

    async def run(values: dict[str, Any]) -> dict:
        if ran is not None:
            ran.append(dict(values))
        return {"ok": True}

    async def job(job_id: str) -> dict:
        raise AssertionError("no run in these tests answers with a job")

    return wizard.Calls(first, check, act, run, job)


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


class ActTests(unittest.IsolatedAsyncioTestCase):
    async def test_an_act_asks_for_the_step_being_left_by_key(self) -> None:
        acted: list[tuple[str, str]] = []
        first = {"step": "one"}
        redrawn = {"step": "one", "notes": ["Connected"], "ready": True}
        walk = wizard.Walk(_calls({"one": redrawn}, acted=acted), first)

        found = await walk.act("connect")

        self.assertEqual(acted, [("connect", "one")])
        self.assertIs(found, redrawn)

    async def test_an_act_does_not_push_the_step_it_leaves(self) -> None:
        first = {"step": "one"}
        walk = wizard.Walk(_calls({"one": {"step": "one"}}), first)

        await walk.act("connect")

        self.assertEqual(walk.history, [])

    async def test_an_act_runs_even_while_the_step_is_not_ready(self) -> None:
        """An act is often what a step needs pressed to become ready - holding it on
        the same gate as Next would make it unreachable."""
        acted: list[tuple[str, str]] = []
        first = {"step": "one", "ready": False}
        walk = wizard.Walk(_calls({"one": {"step": "one", "ready": True}}, acted=acted), first)

        found = await walk.act("connect")

        self.assertEqual(acted, [("connect", "one")])
        self.assertTrue(found["ready"])


class GotoTests(unittest.IsolatedAsyncioTestCase):
    async def test_goto_reopens_by_key_through_first_not_check(self) -> None:
        checked: list[str] = []
        reopened: list[str] = []
        first = {"step": "two"}
        done = {"step": "one", "steps": [{"key": "one", "label": "One", "done": True}]}
        walk = wizard.Walk(_calls({"one": done}, checked=checked, reopened=reopened), first)

        found = await walk.goto("one")

        self.assertEqual(reopened, ["one"])
        self.assertEqual(checked, [])
        self.assertIs(found, done)

    async def test_goto_does_not_touch_the_history(self) -> None:
        first = {"step": "two"}
        walk = wizard.Walk(_calls({"one": {"step": "one"}}, reopened=[]), first)
        walk.history.append({"step": "one"})

        await walk.goto("one")

        self.assertEqual(walk.history, [{"step": "one"}])


if __name__ == "__main__":
    unittest.main()
