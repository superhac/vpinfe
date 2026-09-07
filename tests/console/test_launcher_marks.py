"""Which launcher the rail marks, and why.

A rail row is a signpost: it says something under here is wrong and the page it opens
says what. So the mark is a glyph with a reason in its tooltip rather than a chip, and
it appears only where the answer is not the ordinary one.
"""

from __future__ import annotations

import unittest

from common import path_checks
from console import launchers


def _launcher(*, enabled: bool = True, **checks) -> dict:
    return {
        "launcher_id": "l1",
        "display_name": "Visual Pinball X",
        "enabled": enabled,
        "fields": [{"key": "bin_path", "label": "Program"},
                   {"key": "ini_path", "label": "Configuration File"}],
        "checks": {key: {"state": state, "reason": reason}
                   for key, (state, reason) in checks.items()},
    }


class MarkTests(unittest.TestCase):
    def test_a_launcher_that_works_is_not_marked(self) -> None:
        """A mark on every row says nothing."""
        self.assertIsNone(launchers._mark(
            _launcher(bin_path=(path_checks.OK, ""))))

    def test_an_unset_optional_path_is_not_a_fault(self) -> None:
        """Blank means "use the one the program finds itself"."""
        self.assertIsNone(launchers._mark(
            _launcher(bin_path=(path_checks.OK, ""),
                      ini_path=(path_checks.UNSET, ""))))

    def test_a_missing_program_is_marked(self) -> None:
        self.assertIsNotNone(launchers._mark(
            _launcher(bin_path=(path_checks.MISSING, "Nothing is at that path"))))

    def test_the_reason_names_the_field_a_person_would_look_for(self) -> None:
        said = list(launchers._broken(
            _launcher(bin_path=(path_checks.MISSING, "Nothing is at that path"))))

        self.assertEqual(said, ["Program: Nothing is at that path"])

    def test_a_switched_off_launcher_is_marked(self) -> None:
        self.assertIsNotNone(launchers._mark(
            _launcher(enabled=False, bin_path=(path_checks.OK, ""))))

    def test_a_broken_program_outranks_being_switched_off(self) -> None:
        """Switched off is a choice somebody made. A program that is not there is a
        launcher that cannot run, and it is the one to say when a row is both."""
        said = list(launchers._broken(
            _launcher(enabled=False,
                      bin_path=(path_checks.MISSING, "Nothing is at that path"))))

        self.assertEqual(said, ["Program: Nothing is at that path"])


if __name__ == "__main__":
    unittest.main()
