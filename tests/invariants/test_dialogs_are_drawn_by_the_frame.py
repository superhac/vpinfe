"""Every Console dialog is drawn by `console/dialog.py`, so they all share one design."""

from __future__ import annotations

import pathlib
import unittest

CONSOLE = pathlib.Path(__file__).resolve().parents[2] / "console"
FRAME = "dialog.py"
OPENS_ONE = "ui.dialog("

# Not questions, so not on the frame: nothing in them is answered or committed.
NOT_ASKING = {
    "mediaview.py": "an enlarged picture or text, with nothing to answer",
    "remote.py": "the phone remote's own sheets, drawn for a touch screen",
}


class DialogsAreDrawnByTheFrame(unittest.TestCase):
    def test_no_dialog_is_drawn_by_hand(self) -> None:
        by_hand = sorted(path.name for path in CONSOLE.glob("*.py")
                         if path.name not in (FRAME, *NOT_ASKING)
                         and OPENS_ONE in path.read_text(encoding="utf-8"))
        self.assertEqual([], by_hand)

    def test_every_exception_still_draws_one(self) -> None:
        """One that no longer opens a dialog is an exception to delete."""
        for name in NOT_ASKING:
            with self.subTest(name=name):
                self.assertIn(OPENS_ONE, (CONSOLE / name).read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
