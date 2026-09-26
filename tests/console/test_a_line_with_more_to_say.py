"""A line with more to say than it shows, and the mark at its end that shows it."""

from __future__ import annotations

import unittest
from typing import Any

from nicegui import ui

from console import metrics, panel
from tests.support import lines


def _drawn(text: str, hint: str = "") -> ui.element:
    with ui.column() as body:
        panel.line(text, hint=hint)
    return body


def _mark(body: ui.element) -> ui.icon:
    return next(one for one in body.descendants() if isinstance(one, ui.icon))


class LineTests(unittest.TestCase):
    def test_a_line_with_nothing_more_is_its_words_alone(self) -> None:
        body = _drawn("Read just now")

        self.assertEqual({"Read just now": ""}, lines.details(body))
        self.assertFalse([one for one in body.descendants() if isinstance(one, ui.icon)])

    def test_a_line_with_more_ends_in_the_mark_that_opens_it(self) -> None:
        body = _drawn("Could not read it", "Nothing is at /x")

        self.assertEqual({"Could not read it": "Nothing is at /x"}, lines.details(body))

    def test_the_mark_is_reached_by_a_keyboard_and_named_by_its_detail(self) -> None:
        mark = _mark(_drawn("Could not read it", "Nothing is at /x"))

        self.assertEqual(("0", "button", "Nothing is at /x"),
                         (str(mark.props["tabindex"]), mark.props["role"],
                          mark.props["aria-label"]))

    def test_a_click_on_the_mark_stops_at_it(self) -> None:
        mark = _mark(_drawn("Could not read it", "Nothing is at /x"))

        self.assertIn("click.stop", [one.type for one in mark._event_listeners.values()])


class ReadingAgainTests(unittest.TestCase):
    def test_the_same_graphics_reason_is_not_drawn_again(self) -> None:
        held = {"watch_gpu": True, "gpu": {"available": False, "reason": "Not installed",
                                           "detail": "Nothing is at /usr/bin/nvidia-smi"}}
        with ui.column() as cards:
            pass
        metrics._draw_cards(cards, held)
        first = [one.id for one in cards.descendants()]

        metrics._draw_cards(cards, held)

        self.assertEqual(first, [one.id for one in cards.descendants()])
        self.assertEqual({"Not installed": "Nothing is at /usr/bin/nvidia-smi"},
                         lines.details(cards))

    def test_a_changed_graphics_reason_is(self) -> None:
        held: dict[str, Any] = {"watch_gpu": True, "gpu": {
            "available": False, "reason": "Not installed", "detail": ""}}
        with ui.column() as cards:
            pass
        metrics._draw_cards(cards, held)
        held["gpu"] = {**held["gpu"], "detail": "Nothing is at /usr/bin/nvidia-smi"}

        metrics._draw_cards(cards, held)

        self.assertEqual({"Not installed": "Nothing is at /usr/bin/nvidia-smi"},
                         lines.details(cards))


if __name__ == "__main__":
    unittest.main()
