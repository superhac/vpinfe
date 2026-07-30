"""Turning an unversioned 2.x .info into schema 2.

The one place in this branch that rewrites a file a user already has, so what matters
here is what survives, not what the new shape looks like.
"""

from __future__ import annotations

import json
import unittest
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory

from common.tables.info_migration import (
    backup_path,
    is_versioned,
    migrate,
    needs_migration,
    write_backup,
)
from common.tables.metaconfig import MetaConfig

LEGACY = {
    "Info": {"Title": "Dr. Dude", "VPSId": "vps-1", "Rom": "dd_l2",
             "Authors": ["someone", "someone else"]},
    "User": {"Rating": 7, "Favorite": 1, "LastRun": 1671033801, "StartCount": 12,
             "RunTime": 340, "Tags": ["fast"], "FrontendDOFEvent": "E901",
             "Score": {"rom": "dd_l2"}},
    "VPXFile": {"filename": "Dr. Dude.vpx", "filehash": "abc123", "version": "1.2",
                "releaseDate": "22.06.2019", "saveDate": "Tue Dec 13 16:03:21 2022",
                "saveRev": "4", "vbsHash": "def456", "rom": "dd_l2",
                "detectnfozzy": True, "detectscorebit": True},
    "VPinFE": {"deletedNVRamOnClose": True, "altlauncher": "/opt/vpx",
               "pluginprofile": "no-dmd", "alttitle": "Doctor Dude",
               "altvpsid": "vps-override"},
    "Medias": {"wheel": {"Source": "user"}},
}


class DetectionTests(unittest.TestCase):
    def test_a_2x_file_is_recognised(self):
        self.assertTrue(needs_migration(LEGACY))

    def test_a_stamped_file_is_left_alone(self):
        self.assertFalse(needs_migration({"vpinfe": {"schema": 2}, "VPXFile": {}}))
        self.assertFalse(needs_migration({"VPinFE": {"schema": 2}}))

    def test_a_file_we_wrote_is_not_migrated_again(self):
        self.assertFalse(needs_migration(migrate(LEGACY)))

    def test_migrating_twice_changes_nothing(self):
        self.assertEqual(migrate(migrate(LEGACY)), migrate(LEGACY))

    def test_junk_is_not_a_2x_file(self):
        for value in (None, [], "", {}, {"Info": {}}):
            with self.subTest(value=value):
                self.assertFalse(needs_migration(value))


class WhatSurvivesTests(unittest.TestCase):
    def setUp(self):
        self.after = migrate(LEGACY)

    def test_play_history_is_untouched(self):
        """Ratings, counts and tags are the user's, and no part of this reshapes them."""
        user = self.after["User"]
        for key in ("Rating", "Favorite", "LastRun", "StartCount", "RunTime", "Tags"):
            self.assertEqual(user[key], LEGACY["User"][key], key)

    def test_a_key_outside_the_spec_survives(self):
        """Score is written by the NVRAM reader and is not one of the specced six."""
        self.assertEqual(self.after["User"]["Score"], {"rom": "dd_l2"})

    def test_the_dof_override_moves_and_leaves_nothing_behind(self):
        self.assertEqual(self.after["vpinfe"]["frontend_dof_event"], "E901")
        self.assertNotIn("FrontendDOFEvent", self.after["User"])

    def test_our_settings_keep_their_values_under_new_names(self):
        vpinfe = self.after["vpinfe"]
        self.assertTrue(vpinfe["delete_nvram_on_close"])
        self.assertEqual(vpinfe["alt_launcher"], "/opt/vpx")
        self.assertEqual(vpinfe["plugin_profile"], "no-dmd")
        self.assertEqual(vpinfe["alt_title"], "Doctor Dude")
        self.assertEqual(vpinfe["alt_vpsid"], "vps-override")

    def test_the_table_file_becomes_a_game_file(self):
        entry = self.after["game_files"]["Dr. Dude.vpx"]
        self.assertEqual(entry["file_hash"], "abc123")
        self.assertEqual(entry["vbs_hash"], "def456")
        self.assertEqual(entry["rom"], "dd_l2")
        self.assertEqual(entry["save_rev"], "4")

    def test_dates_are_normalised_on_the_way_through(self):
        entry = self.after["game_files"]["Dr. Dude.vpx"]
        self.assertEqual(entry["release_date"], "2019-06-22")
        self.assertEqual(entry["save_date"], "2022-12-13T16:03:21")

    def test_the_scorbit_typo_is_corrected(self):
        self.assertTrue(self.after["game_files"]["Dr. Dude.vpx"]["detect_scorbit"])

    def test_camel_case_detect_keys_are_not_dropped(self):
        """Real files carry both detectssf and detectSSF."""
        after = migrate({**LEGACY, "VPXFile": {**LEGACY["VPXFile"],
                                               "detectSSF": True, "detectFleep": True}})
        entry = after["game_files"]["Dr. Dude.vpx"]
        self.assertTrue(entry["detect_ssf"])
        self.assertTrue(entry["detect_fleep"])

    def test_authors_land_on_the_game_file(self):
        """Table-level authors only worked while a folder held one game file."""
        self.assertEqual(self.after["game_files"]["Dr. Dude.vpx"]["authors"],
                         ["someone", "someone else"])

    def test_the_described_file_becomes_the_default(self):
        self.assertEqual(self.after["vpinfe"]["default_game_file"], "Dr. Dude.vpx")

    def test_a_section_we_do_not_own_is_left_alone(self):
        after = migrate({**LEGACY, "SomeOtherTool": {"note": "keep me"}})
        self.assertEqual(after["SomeOtherTool"], {"note": "keep me"})

    def test_what_is_deliberately_gone(self):
        for section in ("VPXFile", "Medias", "VPinFE"):
            self.assertNotIn(section, self.after, section)
        self.assertNotIn("Rom", self.after["Info"])
        self.assertNotIn("Authors", self.after["Info"])

    def test_a_folder_with_no_table_file_still_migrates(self):
        """Nine files in the corpus have no VPXFile at all."""
        after = migrate({"Info": {"Title": "x"}, "User": {"Rating": 2},
                         "Medias": {}, "VPinFE": {"altlauncher": "/opt/vpx"}})
        self.assertEqual(after["game_files"], {})
        self.assertEqual(after["User"]["Rating"], 2)
        self.assertTrue(is_versioned(after))


class BackupTests(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.info = self.root / "Example.info"
        self.info.write_text(json.dumps(LEGACY), encoding="utf-8")

    def _backups(self):
        return sorted(p for p in self.root.iterdir() if ".vpinfe-" in p.name)

    def test_the_name_carries_a_sortable_utc_stamp(self):
        path = backup_path("/tables/X/X.info", datetime(2026, 7, 29, 14, 30, 22, tzinfo=UTC))

        self.assertEqual(path, "/tables/X/X.info.vpinfe-20260729T143022Z")
        self.assertNotIn(":", path, "Windows will not have a colon in a filename")

    def test_reading_does_not_write_anything(self):
        before = self.info.read_text(encoding="utf-8")

        MetaConfig(str(self.info))

        self.assertEqual(self.info.read_text(encoding="utf-8"), before)
        self.assertEqual(self._backups(), [])

    def test_the_first_write_keeps_the_original_byte_for_byte(self):
        original = self.info.read_text(encoding="utf-8")

        meta = MetaConfig(str(self.info))
        meta.writeConfig()

        backups = self._backups()
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_text(encoding="utf-8"), original)
        self.assertEqual(json.loads(self.info.read_text(encoding="utf-8"))["vpinfe"]["schema"], 2)

    def test_later_writes_do_not_pile_up_restore_points(self):
        """One per schema bump over the app's lifetime, not one per rebuild."""
        meta = MetaConfig(str(self.info))
        meta.writeConfig()
        meta.writeConfig()
        MetaConfig(str(self.info)).writeConfig()

        self.assertEqual(len(self._backups()), 1)

    def test_a_second_migration_never_overwrites_the_first_backup(self):
        stamp = datetime(2026, 7, 29, 14, 30, 22, tzinfo=UTC)
        first = write_backup(str(self.info), json.dumps(LEGACY), stamp)
        second = write_backup(str(self.info), json.dumps({"Info": {}}), stamp)

        self.assertNotEqual(first, second)
        self.assertEqual(json.loads(Path(first).read_text())["Info"]["Title"], "Dr. Dude")

    def test_an_unreadable_backup_is_refused_rather_than_written(self):
        with self.assertRaises(json.JSONDecodeError):
            write_backup(str(self.info), "{ this is not json")

        self.assertEqual(self._backups(), [])


if __name__ == "__main__":
    unittest.main()
