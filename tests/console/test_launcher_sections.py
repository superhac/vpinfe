"""Which sections a launcher's rail offers, and when.

Offering a settings editor for a program that is not on this machine is a form of
lying: there is nothing to read it out of and nothing a write could mean. Setup and
Actions stay, because pointing the launcher somewhere else is how it gets fixed.
"""

from __future__ import annotations

import unittest
from types import SimpleNamespace

from common import path_checks
from console import workbench


def _context(state: str, groups=("backglass",)) -> dict:
    return {
        "launcher": {"checks": {"bin_path": {"state": state}}},
        "config_groups": [SimpleNamespace(key=key, label=key.title(), settings=[1])
                          for key in groups],
    }


def _shown(context: dict) -> list[str]:
    return [s.key for s in workbench.sections_for("launcher")
            if s.shown is None or s.shown(context)]


class RailTests(unittest.TestCase):
    def test_a_working_launcher_offers_the_groups_its_app_declares(self) -> None:
        shown = _shown(_context(path_checks.OK))

        self.assertIn("launcher_backglass", shown)
        self.assertIn("launcher_setup", shown)
        self.assertIn("launcher_actions", shown)

    def test_a_program_that_is_not_there_leaves_only_what_can_fix_it(self) -> None:
        shown = _shown(_context(path_checks.MISSING))

        self.assertEqual(shown, ["launcher_setup", "launcher_actions"])

    def test_a_group_the_app_does_not_declare_is_absent_rather_than_empty(self) -> None:
        """An install without the plugin architecture shows fewer sections, not empty
        ones - and that follows from what the app answered rather than a version test."""
        shown = _shown(_context(path_checks.OK, groups=("backglass",)))

        self.assertNotIn("launcher_rom", shown)
        self.assertNotIn("launcher_scoreview", shown)

    def test_a_group_declared_with_nothing_in_it_is_also_absent(self) -> None:
        context = _context(path_checks.OK)
        context["config_groups"] = [SimpleNamespace(key="backglass", label="Backglass",
                                                    settings=[])]

        self.assertNotIn("launcher_backglass", _shown(context))


class PlayingTests(unittest.TestCase):
    def test_not_knowing_is_not_a_reason_to_refuse_to_draw(self) -> None:
        class Broken:
            def play_state(self):
                raise RuntimeError("no answer")

        self.assertFalse(workbench._playing(Broken()))

    def test_a_table_playing_is_reported(self) -> None:
        class Playing:
            def play_state(self):
                return {"launching": True}

        self.assertTrue(workbench._playing(Playing()))

    def test_the_reason_says_who_the_other_writer_is(self) -> None:
        """The program rewrites this file itself when a table exits, so an edit made now
        is one of two writers and the last one wins."""
        self.assertIn("writes this file itself", workbench.PLAYING_NOTE)


if __name__ == "__main__":
    unittest.main()
