"""A dialog from `console/dialog.py` is deleted once the browser says it has hidden, and
what its caller reads after `await` is still there to read."""

from __future__ import annotations

import asyncio
import unittest
from typing import Any

from nicegui import ui

from console import dialog as frame
from tests.support.clicks import said

# Made at import, outside any task, where NiceGUI still hands out the script's own page.
_PAGE = ui.element()
TIMES = 5


async def _answer(box: ui.dialog) -> Any:
    return await box


async def _asked(*, persistent: bool = False, dismissed: bool = False
                 ) -> tuple[ui.dialog, Any, Any]:
    """A name asked for, typed, answered or dismissed, and hidden: the dialog, its field,
    and what the await gave back."""
    with _PAGE, frame.opened("Name", persistent=persistent) as box:
        field = frame.field()
    waiting = asyncio.create_task(_answer(box))
    await asyncio.sleep(0)
    said(field, "update:value", "Typed")
    if dismissed:
        said(box, "update:modelValue", False)
    else:
        box.submit(field.value)
    answered = await waiting
    said(box, "hide")
    return box, field, answered


def _elements() -> int:
    return len(_PAGE.client.elements)


class ADialogIsGoneOnceClosed(unittest.TestCase):
    def _again_and_again(self, **asked: Any) -> None:
        async def run() -> None:
            before = _elements()
            for _ in range(TIMES):
                box, _field, _answered = await _asked(**asked)
                self.assertTrue(box.is_deleted)
            self.assertEqual(before, _elements())
        asyncio.run(run())

    def test_opening_and_closing_one_leaves_the_page_as_it_was(self) -> None:
        self._again_and_again()

    def test_a_persistent_one_goes_too(self) -> None:
        self._again_and_again(persistent=True)

    def test_one_dismissed_by_escape_or_a_click_outside_goes_too(self) -> None:
        self._again_and_again(dismissed=True)

    def test_a_field_read_after_the_await_still_reads(self) -> None:
        box, field, answered = asyncio.run(_asked())

        self.assertTrue(box.is_deleted)
        self.assertEqual(("Typed", "Typed"), (answered, field.value))

    def test_a_hide_listener_added_before_it_opens_still_runs(self) -> None:
        heard: list[bool] = []

        async def run() -> ui.dialog:
            with _PAGE, frame.opened("Name") as box:
                frame.field()
            box.on("hide", lambda: heard.append(box.is_deleted))
            waiting = asyncio.create_task(_answer(box))
            await asyncio.sleep(0)
            box.submit(True)
            await waiting
            said(box, "hide")
            return box

        box = asyncio.run(run())

        self.assertEqual([False], heard)
        self.assertTrue(box.is_deleted)

    def test_one_opened_again_before_it_hides_stays(self) -> None:
        async def run() -> tuple[bool, bool]:
            with _PAGE, frame.opened("Name") as box:
                frame.field()
            waiting = asyncio.create_task(_answer(box))
            await asyncio.sleep(0)
            box.submit(True)
            await waiting
            box.open()
            said(box, "hide")
            kept = not box.is_deleted
            box.close()
            said(box, "hide")
            return kept, box.is_deleted

        self.assertEqual((True, True), asyncio.run(run()))


if __name__ == "__main__":
    unittest.main()
