"""Every Console dialog is made by `console/dialog.py`, so they all share one design."""

from __future__ import annotations

import ast
import pathlib
import unittest

from tests.support import trees

CONSOLE = pathlib.Path(__file__).resolve().parents[2] / "console"
FRAME = "dialog.py"
OPENS_ONE = "ui.dialog("

# Not questions, so they draw their own card: nothing in them is answered or committed.
NOT_ASKING = {
    "mediaview.py": "an enlarged picture or text, with nothing to answer",
    "remote.py": "the phone remote's own sheets, drawn for a touch screen",
}


def _called(path: pathlib.Path) -> set[str]:
    """What `path` calls on `console.dialog`, by name."""
    tree = trees.tree_for(path)
    names = {alias.asname or alias.name for one in ast.walk(tree)
             if isinstance(one, ast.ImportFrom) and one.module == "console"
             for alias in one.names if alias.name == "dialog"}
    return {one.func.attr for one in ast.walk(tree)
            if isinstance(one, ast.Call) and isinstance(one.func, ast.Attribute)
            and isinstance(one.func.value, ast.Name) and one.func.value.id in names}


class DialogsAreDrawnByTheFrame(unittest.TestCase):
    def test_no_dialog_is_drawn_by_hand(self) -> None:
        by_hand = sorted(path.name for path in CONSOLE.glob("*.py")
                         if path.name != FRAME
                         and OPENS_ONE in path.read_text(encoding="utf-8"))
        self.assertEqual([], by_hand)

    def test_only_an_exception_draws_its_own_card(self) -> None:
        own = sorted(path.name for path in CONSOLE.glob("*.py") if "made" in _called(path))
        self.assertEqual(sorted(NOT_ASKING), own)

    def test_an_exception_asks_nothing(self) -> None:
        for name in NOT_ASKING:
            with self.subTest(name=name):
                self.assertNotIn("opened", _called(CONSOLE / name))


if __name__ == "__main__":
    unittest.main()
