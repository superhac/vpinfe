"""A heading is declared once, so the three selectors cannot drift apart on colour.

Spacing is theirs to vary. Type is not.
"""

from __future__ import annotations

import pathlib
import re
import unittest

REPO = pathlib.Path(__file__).resolve().parent.parent.parent
SHEET = REPO / "console/static/console-base.css"
HEADINGS = ("console-card-title", "console-group", "console-fact-heading")
# The properties that are the treatment. Spacing is what a heading may declare for itself.
TYPE = ("color", "font-size", "letter-spacing", "text-transform")


def _blocks() -> list[tuple[str, str]]:
    text = SHEET.read_text(encoding="utf-8")
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    return re.findall(r"([^{}]+)\{([^{}]*)\}", text)


class TestOneHeading(unittest.TestCase):
    def test_the_type_is_declared_once(self) -> None:
        declaring = [sel.strip() for sel, body in _blocks()
                     if any(f"{p}:" in body for p in TYPE)
                     and any(f".{h}" in sel for h in HEADINGS)]
        self.assertEqual(len(declaring), 1,
                         f"a heading's type belongs in one block, found {declaring}")

    def test_that_block_covers_all_three(self) -> None:
        block = next(sel for sel, body in _blocks()
                     if any(f"{p}:" in body for p in TYPE)
                     and any(f".{h}" in sel for h in HEADINGS))
        for name in HEADINGS:
            self.assertIn(f".{name}", block, f"{name} is a heading and shares the type")

    def test_it_is_the_accent(self) -> None:
        body = next(body for sel, body in _blocks()
                    if any(f".{h}" in sel for h in HEADINGS) and "color:" in body)
        self.assertIn("var(--accent)", body)


if __name__ == "__main__":
    unittest.main()
