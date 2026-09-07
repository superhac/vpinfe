"""What a launcher's row says about whether it can run a table.

One column rather than two, because a launcher that is switched off and a launcher whose
program is gone are answers to the same question and a reader should not have to combine
them.
"""

from __future__ import annotations

import unittest

from common import path_checks
from console import launchers


def _launcher(*, enabled: bool = True, **checks) -> dict:
    return {
        "launcher_id": "l1",
        "display_name": "Visual Pinball X",
        "app": "vpx",
        "app_name": "Visual Pinball X",
        "enabled": enabled,
        "settings": {"bin_path": "/opt/VPinballX"},
        "fields": [{"key": "bin_path", "label": "Program"},
                   {"key": "ini_path", "label": "Configuration File"}],
        "checks": {key: {"state": state, "reason": reason}
                   for key, (state, reason) in checks.items()},
    }


class StateTests(unittest.TestCase):
    def test_a_launcher_that_works_is_ready(self) -> None:
        self.assertEqual(launchers.state_of(_launcher(bin_path=(path_checks.OK, ""))),
                         launchers.STATE_READY)

    def test_an_unset_optional_path_is_not_a_fault(self) -> None:
        """Blank means "use the one the program finds itself"."""
        self.assertEqual(
            launchers.state_of(_launcher(bin_path=(path_checks.OK, ""),
                                         ini_path=(path_checks.UNSET, ""))),
            launchers.STATE_READY)

    def test_a_missing_program_cannot_run(self) -> None:
        self.assertEqual(
            launchers.state_of(_launcher(bin_path=(path_checks.MISSING, "Not there"))),
            launchers.STATE_BROKEN)

    def test_a_switched_off_launcher_says_so(self) -> None:
        self.assertEqual(
            launchers.state_of(_launcher(enabled=False, bin_path=(path_checks.OK, ""))),
            launchers.STATE_OFF)

    def test_a_broken_program_outranks_being_switched_off(self) -> None:
        """Switched off is a choice somebody made. A program that is not there is a
        launcher that cannot run, and it is the one to say when a row is both."""
        self.assertEqual(
            launchers.state_of(_launcher(enabled=False,
                                         bin_path=(path_checks.MISSING, "Not there"))),
            launchers.STATE_BROKEN)

    def test_the_reason_names_the_field_a_person_would_look_for(self) -> None:
        said = list(launchers._broken(
            _launcher(bin_path=(path_checks.MISSING, "Nothing is at that path"))))

        self.assertEqual(said, ["Program: Nothing is at that path"])


class RowTests(unittest.TestCase):
    def test_the_default_is_marked_on_the_one_it_applies_to(self) -> None:
        """A column that says the same thing on every row but one is a column about the
        exception."""
        rows = launchers.rows([_launcher(bin_path=(path_checks.OK, ""))],
                              {"vpx": "l1"})

        self.assertEqual(rows[0]["default"], "Default")

    def test_and_is_blank_everywhere_else(self) -> None:
        rows = launchers.rows([_launcher(bin_path=(path_checks.OK, ""))], {})

        self.assertEqual(rows[0]["default"], "")

    def test_a_row_names_the_program_it_runs(self) -> None:
        rows = launchers.rows([_launcher(bin_path=(path_checks.OK, ""))], {})

        self.assertEqual(rows[0]["program"], "/opt/VPinballX")


if __name__ == "__main__":
    unittest.main()
