"""Every grid marks the one column its rows are scanned by.

The render half is tests/theming/test_identifier_ink.py: nothing here can tell
whether the class resolves to a color.
"""

from __future__ import annotations

import unittest

from console import grid


def _columns(marked: int) -> list[dict]:
    """A column set with `marked` identifier columns in it."""
    built = [grid.column("plain", "Plain"), grid.column("other", "Other")]
    for index in range(marked):
        built.insert(0, grid.identifier(f"id{index}", f"Id {index}"))
    return built


class IdentifierColumnIsMarked(unittest.TestCase):

    def test_the_marker_puts_the_class_on_the_cell(self):
        definition = grid.identifier("name", "Name")
        self.assertIn(grid.IDENTIFIER_CLASS, definition["cellClass"])
        self.assertEqual("name", definition["field"])

    def test_the_marker_keeps_a_cell_class_the_column_already_had(self):
        definition = grid.identifier("name", "Name", cellClass="console-stars-cell")
        self.assertIn("console-stars-cell", definition["cellClass"])
        self.assertIn(grid.IDENTIFIER_CLASS, definition["cellClass"])

    def test_a_plain_column_is_not_marked(self):
        self.assertNotIn(grid.IDENTIFIER_CLASS,
                         str(grid.column("year", "Year").get("cellClass") or ""))


class EveryGridDeclaresExactlyOne(unittest.TestCase):

    def _refusal(self, columns: list[dict]) -> str:
        with self.assertRaises(ValueError) as caught:
            grid.build(columns, [], "console.test.columns")
        return str(caught.exception)

    def test_none_is_refused(self):
        message = self._refusal(_columns(0))
        self.assertIn("console.test.columns", message)
        self.assertIn("declares 0", message)

    def test_two_is_refused_and_names_them(self):
        message = self._refusal(_columns(2))
        self.assertIn("declares 2", message)
        self.assertIn("id0", message)
        self.assertIn("id1", message)


if __name__ == "__main__":
    unittest.main()
