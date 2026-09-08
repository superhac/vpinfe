"""Copies of the file an app keeps its settings in.

Restoring the wrong one is a mistake somebody makes once, and without a copy of what was
there it is the last one they get to make.
"""

from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from common.games import config_backups as backups


class _Case(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.ini = self.root / "VPinballX.ini"
        self.ini.write_text("[A]\nB = 1\n")
        self.files = {"Application settings": str(self.ini)}
        patch = mock.patch.object(backups, "BACKUPS_DIR", self.root / "backups")
        patch.start()
        self.addCleanup(patch.stop)


class TakeTests(_Case):
    def test_a_copy_carries_when_and_why(self) -> None:
        taken = backups.take("L1", self.files, label="before the change")[0]

        self.assertTrue(taken.taken_at)
        self.assertEqual(taken.reason, backups.MANUAL)
        self.assertEqual(taken.label, "before-the-change")

    def test_a_file_that_is_not_there_is_not_copied(self) -> None:
        self.assertEqual(backups.take("L1", {"x": str(self.root / "gone.ini")}), [])

    def test_each_launcher_keeps_its_own(self) -> None:
        """Two launchers on one machine each have their own file, and copies of both in
        one folder would be told apart by a filename alone."""
        backups.take("L1", self.files)
        backups.take("L2", self.files)

        self.assertEqual(len(backups.held("L1")), 1)
        self.assertEqual(len(backups.held("L2")), 1)

    def test_a_label_cannot_carry_anything_into_a_filename(self) -> None:
        taken = backups.take("L1", self.files, label="../../etc/passwd")[0]

        self.assertNotIn("/", taken.name)
        self.assertNotIn("..", taken.name)


    def test_the_folder_is_named_for_a_person_looking_in_it(self) -> None:
        """Somebody who opens Finder should not have to work out which of two
        ten-character ids is theirs."""
        backups.take("a4CbR4RnyE", self.files, named="Visual Pinball X")

        home = backups.home_for("a4CbR4RnyE", "Visual Pinball X")
        self.assertTrue(home.endswith("Visual-Pinball-X--a4CbR4RnyE"))
        self.assertTrue(Path(home).is_dir())

    def test_and_the_id_still_keeps_two_of_one_name_apart(self) -> None:
        first = backups.home_for("aaa", "Visual Pinball X")
        second = backups.home_for("bbb", "Visual Pinball X")

        self.assertNotEqual(first, second)


class RestoreTests(_Case):
    def test_putting_one_back_restores_what_it_held(self) -> None:
        made = backups.take("L1", self.files)[0]
        self.ini.write_text("[A]\nB = 2\n")

        backups.restore("L1", made.name, self.files)

        self.assertEqual(self.ini.read_text(), "[A]\nB = 1\n")

    def test_and_keeps_what_was_there_first(self) -> None:
        """So putting the wrong one back is something to undo rather than regret."""
        made = backups.take("L1", self.files)[0]
        self.ini.write_text("[A]\nB = 2\n")

        safety = backups.restore("L1", made.name, self.files)

        self.assertIsNotNone(safety)
        self.assertEqual(safety.reason, backups.BEFORE_RESTORE)
        self.assertIn(backups.BEFORE_RESTORE, [one.reason for one in backups.held("L1")])

    def test_a_hyphenated_reason_still_reads_back(self) -> None:
        """`before-restore` is one word with a hyphen in it, and a pattern that allowed
        only letters read its reason as blank."""
        made = backups.take("L1", self.files)[0]
        self.ini.write_text("x")
        backups.restore("L1", made.name, self.files)

        reasons = {one.reason for one in backups.held("L1")}
        self.assertEqual(reasons, {backups.MANUAL, backups.BEFORE_RESTORE})

    def test_a_name_that_is_not_there_is_refused(self) -> None:
        with self.assertRaises(FileNotFoundError):
            backups.restore("L1", "nothing.ini", self.files)

    def test_a_name_that_climbs_out_of_the_folder_is_refused(self) -> None:
        with self.assertRaises(FileNotFoundError):
            backups.restore("L1", "../../../etc/passwd", self.files)

    def test_a_copy_of_a_file_this_app_does_not_keep_is_refused(self) -> None:
        made = backups.take("L1", self.files)[0]

        with self.assertRaises(ValueError):
            backups.restore("L1", made.name, {"other": str(self.root / "Other.ini")})


class OrderTests(_Case):
    def test_the_newest_is_first(self) -> None:
        """The one somebody wants is almost always the last one taken."""
        backups.take("L1", self.files, label="older")
        with mock.patch.object(backups, "datetime") as clock:
            clock.now.return_value.strftime.return_value = "20991231T235959Z"
            backups.take("L1", self.files, label="newer")

        self.assertEqual(backups.held("L1")[0].label, "newer")


if __name__ == "__main__":
    unittest.main()
