"""Converting a whole library at once, and putting it back.

Both walks exist because the lazy path converts a table only when something writes it, so
a library is a mix of shapes and the user cannot tell which is which. What matters here is
that neither walk stops on one bad folder and that nothing is ever destroyed.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from common.tables.info_maintenance import (
    convert_library,
    restorable_backup,
    restore_library,
    table_dirs,
)
from common.tables.info_migration import backup_schema

LEGACY = {
    "Info": {"Title": "Dr. Dude", "Rom": "dd_l2", "Authors": "someone"},
    "User": {"Rating": 4, "StartCount": 12, "Tags": ["fast"]},
    "VPXFile": {"filename": "Dr. Dude.vpx", "filehash": "abc123", "rom": "dd_l2"},
    "Medias": {"wheel": {"Source": "user"}},
}


class LibraryTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

    def _table(self, name: str, meta=LEGACY) -> Path:
        table_dir = self.root / name
        table_dir.mkdir()
        (table_dir / f"{name}.vpx").write_text("not really a vpx", encoding="utf-8")
        if meta is not None:
            (table_dir / f"{name}.info").write_text(json.dumps(meta), encoding="utf-8")
        return table_dir

    def _info(self, table_dir: Path) -> dict:
        return json.loads((table_dir / f"{table_dir.name}.info").read_text(encoding="utf-8"))

    def _backups(self, table_dir: Path) -> list[Path]:
        return sorted(p for p in table_dir.iterdir() if ".vpinfe-" in p.name)


class ConvertTests(LibraryTestCase):
    def test_it_converts_every_table_in_one_pass(self):
        for name in ("Dr. Dude", "Taxi", "Whirlwind"):
            self._table(name)

        result = convert_library(self.root)

        self.assertEqual(result["converted"], 3)
        self.assertEqual(result["failed"], 0)
        for name in ("Dr. Dude", "Taxi", "Whirlwind"):
            after = self._info(self.root / name)
            self.assertEqual(after["vpinfe"]["schema"], 2)
            self.assertNotIn("VPXFile", after)

    def test_it_keeps_a_restore_point_for_each_table(self):
        table = self._table("Dr. Dude")
        original = (table / "Dr. Dude.info").read_text(encoding="utf-8")

        convert_library(self.root)

        backups = self._backups(table)
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_text(encoding="utf-8"), original)

    def test_running_it_twice_converts_nothing_the_second_time(self):
        self._table("Dr. Dude")
        convert_library(self.root)

        result = convert_library(self.root)

        self.assertEqual(result["converted"], 0)
        self.assertEqual(result["already_current"], 1)
        self.assertEqual(len(self._backups(self.root / "Dr. Dude")), 1)

    def test_one_unreadable_file_does_not_stop_the_others(self):
        """The state somebody is trying to get out of. Failing the run would withhold the
        fix from every other table in the library."""
        self._table("Dr. Dude")
        broken = self._table("Broken")
        (broken / "Broken.info").write_text("{ not json", encoding="utf-8")

        result = convert_library(self.root)

        self.assertEqual(result["converted"], 1)
        self.assertEqual(result["failed"], 1)
        self.assertEqual(result["failures"][0][0], "Broken")
        self.assertEqual((broken / "Broken.info").read_text(encoding="utf-8"), "{ not json")

    def test_a_folder_with_no_info_is_left_alone(self):
        self._table("No Meta", meta=None)

        result = convert_library(self.root)

        self.assertEqual(result["converted"], 0)
        self.assertEqual(result["failed"], 0)

    def test_one_table_can_be_converted_on_its_own(self):
        self._table("Dr. Dude")
        self._table("Taxi")

        result = convert_library(self.root, table_name="Taxi")

        self.assertEqual(result["converted"], 1)
        self.assertNotIn("vpinfe", self._info(self.root / "Dr. Dude"))


class RestoreTests(LibraryTestCase):
    def test_it_puts_back_everything_that_was_converted(self):
        for name in ("Dr. Dude", "Taxi"):
            self._table(name)
        convert_library(self.root)

        result = restore_library(self.root)

        self.assertEqual(result["restored"], 2)
        for name in ("Dr. Dude", "Taxi"):
            after = self._info(self.root / name)
            self.assertEqual(after["VPXFile"]["filehash"], "abc123")
            self.assertEqual(after["User"]["Rating"], 4)
            self.assertNotIn("vpinfe", after)

    def test_a_table_that_never_converted_is_left_alone(self):
        self._table("Dr. Dude")

        result = restore_library(self.root)

        self.assertEqual(result["restored"], 0)
        self.assertEqual(result["nothing_to_restore"], 1)
        self.assertIn("VPXFile", self._info(self.root / "Dr. Dude"))

    def test_the_current_file_is_kept_so_the_restore_is_reversible(self):
        table = self._table("Dr. Dude")
        convert_library(self.root)
        converted = (table / "Dr. Dude.info").read_text(encoding="utf-8")

        restore_library(self.root)

        backups = self._backups(table)
        self.assertEqual(len(backups), 2)
        self.assertIn(converted, [b.read_text(encoding="utf-8") for b in backups])

    def test_a_backup_this_build_cannot_read_is_passed_over_not_treated_as_the_end(self):
        """A 2.x build must not restore a schema 2 file, but the unversioned copy sitting
        behind it is still exactly what it wants. Newer backups are stepped over, not a
        dead end."""
        table = self._table("Dr. Dude")
        convert_library(self.root)
        restore_library(self.root)          # back to 2.x, and the schema 2 copy is kept

        as_2x = restorable_backup(table, max_schema=0)
        self.assertIsNotNone(as_2x)
        self.assertIsNone(backup_schema(as_2x), "2.x takes the unversioned copy")
        self.assertEqual(backup_schema(restorable_backup(table, max_schema=2)), 2)

    def test_the_newest_readable_backup_wins(self):
        table = self._table("Dr. Dude")
        convert_library(self.root)
        restore_library(self.root)
        (table / "Dr. Dude.info").write_text(
            json.dumps({**LEGACY, "User": {"Rating": 1}}), encoding="utf-8")
        convert_library(self.root)

        restore_library(self.root, max_schema=0)

        self.assertEqual(self._info(table)["User"]["Rating"], 1)

    def test_an_unreadable_backup_is_skipped_rather_than_restored(self):
        table = self._table("Dr. Dude")
        convert_library(self.root)
        (table / "Dr. Dude.info.vpinfe-20990101T000000Z").write_text("{ broken", "utf-8")

        result = restore_library(self.root)

        self.assertEqual(result["restored"], 1)
        self.assertEqual(self._info(table)["User"]["Rating"], 4)

    def test_a_corrupt_current_file_is_still_kept_before_being_replaced(self):
        """The file most likely to need restoring is the one too broken to parse. Refusing
        to keep it would block the rescue to protect a copy nobody wants back."""
        table = self._table("Dr. Dude")
        convert_library(self.root)
        (table / "Dr. Dude.info").write_text("{ truncated", encoding="utf-8")

        result = restore_library(self.root)

        self.assertEqual(result["restored"], 1)
        kept = [b.read_text(encoding="utf-8") for b in self._backups(table)]
        self.assertIn("{ truncated", kept)


class WalkTests(LibraryTestCase):
    def test_dot_folders_are_not_tables(self):
        self._table("Dr. Dude")
        (self.root / ".hidden").mkdir()

        self.assertEqual([d.name for d in table_dirs(self.root)], ["Dr. Dude"])

    def test_a_missing_root_is_not_an_error(self):
        self.assertEqual(table_dirs(self.root / "nope"), [])


if __name__ == "__main__":
    unittest.main()
