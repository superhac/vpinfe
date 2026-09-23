"""A grid whose built-in views filter counts the rows the filter leaves.

The count sits above the rows, so a total there reads as the size of what is shown.
"""

from __future__ import annotations

import ast
import pathlib
import unittest

CONSOLE = pathlib.Path(__file__).resolve().parents[2] / "console"
FOLLOWS = "getDisplayedRowCount"


def _filtering_views(tree: ast.Module) -> bool:
    """Whether any `Preset(...)` here is given a non-empty `filters`."""
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call)
                and getattr(node.func, "attr", getattr(node.func, "id", "")) == "Preset"):
            continue
        for keyword in node.keywords:
            if keyword.arg == "filters" and not (
                    isinstance(keyword.value, ast.Dict) and not keyword.value.keys):
                return True
    return False


class FilteredViewsCountWhatTheyShow(unittest.TestCase):
    def _filtering(self) -> list[pathlib.Path]:
        return [path for path in sorted(CONSOLE.glob("*.py"))
                if _filtering_views(ast.parse(path.read_text(encoding="utf-8")))]

    def test_the_count_follows_the_grid(self) -> None:
        stuck = [path.name for path in self._filtering()
                 if FOLLOWS not in path.read_text(encoding="utf-8")]
        self.assertEqual([], stuck)

    def test_it_found_the_grids(self) -> None:
        """An empty sweep passes and measures nothing, which reads the same as clean."""
        self.assertGreaterEqual(len(self._filtering()), 6)


if __name__ == "__main__":
    unittest.main()
