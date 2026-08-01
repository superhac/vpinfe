"""Putting back a .info that a newer VPinFE converted.

This runs in the release somebody downgrades *to*, so the cases that matter are the ones
where the newer build left something this one has never seen.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from common.info_restore import (
    backup_names,
    backup_path,
    copy_aside,
    converted_by_newer,
    restorable_backup,
    restore_library,
    table_dirs,
)

OURS = {
    "Info": {"Title": "Dr. Dude", "Rom": "dd_l2"},
    "User": {"Rating": 4, "StartCount": 12, "Tags": ["fast"]},
    "VPXFile": {"filename": "Dr. Dude.vpx", "filehash": "abc123"},
    "Medias": {"wheel": {"Source": "user"}},
}

CONVERTED = {
    "Info": {"Title": "Dr. Dude"},
    "User": {"Rating": 4, "StartCount": 12, "Tags": ["fast"]},
    "vpinfe": {"schema": 2, "id": "mJ8F4RqD8U"},
    "game_files": {"Dr. Dude.vpx": {"file_hash": "abc123"}},
}


class RestoreTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

    def _converted_table(self, name="Dr. Dude", saved=OURS, live=CONVERTED):
        """A folder as a newer VPinFE leaves it: converted .info, original kept beside it."""
        table_dir = self.root / name
        table_dir.mkdir()
        (table_dir / f"{name}.vpx").write_text("not really a vpx", encoding="utf-8")
        (table_dir / f"{name}.info").write_text(json.dumps(live), encoding="utf-8")
        stamp = f"{name}.info.vpinfe-20260729T143022Z"
        (table_dir / stamp).write_text(json.dumps(saved), encoding="utf-8")
        return table_dir

    def _info(self, table_dir):
        return json.loads(
            (table_dir / f"{table_dir.name}.info").read_text(encoding="utf-8"))

    def _backups(self, table_dir):
        return sorted(p for p in table_dir.iterdir() if ".vpinfe-" in p.name)


class RestoreTests(RestoreTestCase):
    def test_it_puts_back_what_this_version_wrote(self):
        table = self._converted_table()

        result = restore_library(self.root)

        self.assertEqual(result["restored"], 1)
        after = self._info(table)
        self.assertEqual(after["VPXFile"]["filehash"], "abc123")
        self.assertEqual(after["User"]["Rating"], 4)
        self.assertNotIn("vpinfe", after)

    def test_a_table_a_newer_build_never_touched_is_left_alone(self):
        table_dir = self.root / "Taxi"
        table_dir.mkdir()
        (table_dir / "Taxi.vpx").write_text("x", encoding="utf-8")
        (table_dir / "Taxi.info").write_text(json.dumps(OURS), encoding="utf-8")

        result = restore_library(self.root)

        self.assertEqual(result["restored"], 0)
        self.assertEqual(result["nothing_to_restore"], 1)

    def test_the_converted_file_is_kept_so_the_restore_is_reversible(self):
        table = self._converted_table()

        restore_library(self.root)

        kept = [json.loads(p.read_text(encoding="utf-8")) for p in self._backups(table)]
        self.assertIn(CONVERTED, kept)

    def test_a_copy_this_version_cannot_read_is_never_restored(self):
        """The rule that makes the whole thing safe: a schema 2 file put back here would
        leave the user on a shape this build has never understood."""
        table = self._converted_table(saved=CONVERTED)

        result = restore_library(self.root)

        self.assertEqual(result["restored"], 0)
        self.assertIsNone(restorable_backup(table))

    def test_a_newer_copy_is_stepped_over_to_reach_one_we_can_read(self):
        table = self._converted_table()
        (table / "Dr. Dude.info.vpinfe-20990101T000000Z").write_text(
            json.dumps(CONVERTED), encoding="utf-8")

        restore_library(self.root)

        self.assertEqual(self._info(table)["VPXFile"]["filehash"], "abc123")

    def test_an_unreadable_copy_is_skipped_rather_than_restored(self):
        table = self._converted_table()
        (table / "Dr. Dude.info.vpinfe-20990101T000000Z").write_text("{ broken", "utf-8")

        result = restore_library(self.root)

        self.assertEqual(result["restored"], 1)
        self.assertEqual(self._info(table)["User"]["Rating"], 4)

    def test_a_corrupt_current_file_is_still_kept_before_being_replaced(self):
        """The file most likely to need restoring is the one too broken to parse."""
        table = self._converted_table()
        (table / "Dr. Dude.info").write_text("{ truncated", encoding="utf-8")

        result = restore_library(self.root)

        self.assertEqual(result["restored"], 1)
        kept = [p.read_text(encoding="utf-8") for p in self._backups(table)]
        self.assertIn("{ truncated", kept)

    def test_one_bad_folder_does_not_stop_the_others(self):
        self._converted_table("Dr. Dude")
        self._converted_table("Taxi")

        result = restore_library(self.root)

        self.assertEqual(result["restored"], 2)
        self.assertEqual(result["failed"], 0)

    def test_one_table_can_be_restored_on_its_own(self):
        self._converted_table("Dr. Dude")
        other = self._converted_table("Taxi")

        result = restore_library(self.root, table_name="Dr. Dude")

        self.assertEqual(result["restored"], 1)
        self.assertIn("vpinfe", self._info(other))


class OfferTests(RestoreTestCase):
    """What decides whether the Tables page offers a restore at all."""

    def test_a_converted_table_is_worth_offering(self):
        self.assertTrue(converted_by_newer(CONVERTED))

    def test_a_table_this_version_wrote_is_not(self):
        self.assertFalse(converted_by_newer(OURS))

    def test_leftover_saved_copies_alone_do_not_keep_the_offer_alive(self):
        """After a restore the folder still holds the copies, but the live file is ours
        again. Offering to put back a file that is already in place reads as though the
        restore did not work."""
        table = self._converted_table()
        restore_library(self.root)

        self.assertFalse(converted_by_newer(self._info(table)))
        self.assertTrue(self._backups(table), "the copies are still there")


class NamingTests(RestoreTestCase):
    def test_the_name_matches_what_the_newer_release_writes(self):
        """A contract between two releases: neither side may change it alone."""
        from datetime import datetime, timezone

        stamp = datetime(2026, 7, 29, 14, 30, 22, tzinfo=timezone.utc)

        self.assertEqual(backup_path("/tables/X/X.info", stamp),
                         "/tables/X/X.info.vpinfe-20260729T143022Z")

    def test_saved_copies_are_listed_newest_first(self):
        names = {"X.info", "X.info.vpinfe-20260101T000000Z",
                 "X.info.vpinfe-20260729T143022Z", "X.vpx"}

        self.assertEqual(backup_names(names, "X.info"),
                         ["X.info.vpinfe-20260729T143022Z",
                          "X.info.vpinfe-20260101T000000Z"])

    def test_dot_folders_are_not_tables(self):
        (self.root / ".hidden").mkdir()
        self._converted_table("Dr. Dude")

        self.assertEqual([d.name for d in table_dirs(self.root)], ["Dr. Dude"])


if __name__ == "__main__":
    unittest.main()


class CollisionOrderingTests(RestoreTestCase):
    """Two backups in the same second still sort in the order they were made.

    The names are the only ordering a restore has: it takes the newest readable one. A
    bump that wrapped 59 to 0 made the newer file sort 59 seconds older, so a restore
    could reach past a good backup to an older one.
    """

    def _two_at(self, when):
        table_dir = self.root / "Dr. Dude"
        table_dir.mkdir()
        info = table_dir / "Dr. Dude.info"
        info.write_text(json.dumps(OURS), encoding="utf-8")
        first = copy_aside(str(info), when)
        second = copy_aside(str(info), when)
        return Path(first).name, Path(second).name

    def test_a_collision_on_the_last_second_of_a_minute_still_sorts_forward(self):
        from datetime import datetime, timezone

        first, second = self._two_at(datetime(2026, 8, 1, 12, 30, 59, tzinfo=timezone.utc))

        self.assertGreater(second, first)

    def test_a_collision_at_midnight_rolls_the_date(self):
        from datetime import datetime, timezone

        first, second = self._two_at(datetime(2026, 8, 1, 23, 59, 59, tzinfo=timezone.utc))

        self.assertGreater(second, first)
        self.assertIn("20260802T000000Z", second)
