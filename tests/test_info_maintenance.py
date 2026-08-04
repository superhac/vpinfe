"""Upgrading a whole library at once, and putting it back.

Both walks exist because the lazy path upgrades a table only when something writes it, so
a library is a mix of shapes and the user cannot tell which is which. What matters here is
that neither walk stops on one bad folder and that nothing is ever destroyed.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from common.games.gameparser import GameParser
from common.games.info_maintenance import (
    game_dirs,
    restorable_backup,
    restore_library,
    upgrade_library,
)
from common.games.info_migration import CURRENT_SCHEMA, backup_schema, schema_of

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

    def _game(self, name: str, meta=LEGACY) -> Path:
        game_dir = self.root / name
        game_dir.mkdir()
        (game_dir / f"{name}.vpx").write_text("not really a vpx", encoding="utf-8")
        if meta is not None:
            (game_dir / f"{name}.info").write_text(json.dumps(meta), encoding="utf-8")
        return game_dir

    def _info(self, game_dir: Path) -> dict:
        return json.loads((game_dir / f"{game_dir.name}.info").read_text(encoding="utf-8"))

    def _backups(self, game_dir: Path) -> list[Path]:
        return sorted(p for p in game_dir.iterdir() if ".vpinfe-" in p.name)


class UpgradeTests(LibraryTestCase):
    def test_it_upgrades_every_game_in_one_pass(self):
        for name in ("Dr. Dude", "Taxi", "Whirlwind"):
            self._game(name)

        result = upgrade_library(self.root)

        self.assertEqual(result["upgraded"], 3)
        self.assertEqual(result["failed"], 0)
        for name in ("Dr. Dude", "Taxi", "Whirlwind"):
            after = self._info(self.root / name)
            self.assertEqual(after["vpinfe"]["schema"], 2)
            self.assertNotIn("VPXFile", after)

    def test_it_keeps_a_restore_point_for_each_game(self):
        game = self._game("Dr. Dude")
        original = (game / "Dr. Dude.info").read_text(encoding="utf-8")

        upgrade_library(self.root)

        backups = self._backups(game)
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_text(encoding="utf-8"), original)

    def test_running_it_twice_upgrades_nothing_the_second_time(self):
        self._game("Dr. Dude")
        upgrade_library(self.root)

        result = upgrade_library(self.root)

        self.assertEqual(result["upgraded"], 0)
        self.assertEqual(result["already_current"], 1)
        self.assertEqual(len(self._backups(self.root / "Dr. Dude")), 1)

    def test_one_unreadable_file_does_not_stop_the_others(self):
        """The state somebody is trying to get out of. Failing the run would withhold the
        fix from every other table in the library."""
        self._game("Dr. Dude")
        broken = self._game("Broken")
        (broken / "Broken.info").write_text("{ not json", encoding="utf-8")

        result = upgrade_library(self.root)

        self.assertEqual(result["upgraded"], 1)
        self.assertEqual(result["failed"], 1)
        self.assertEqual(result["failures"][0][0], "Broken")
        self.assertEqual((broken / "Broken.info").read_text(encoding="utf-8"), "{ not json")

    def test_a_folder_with_no_info_is_left_alone(self):
        self._game("No Meta", meta=None)

        result = upgrade_library(self.root)

        self.assertEqual(result["upgraded"], 0)
        self.assertEqual(result["failed"], 0)

    def test_one_game_can_be_upgraded_on_its_own(self):
        self._game("Dr. Dude")
        self._game("Taxi")

        result = upgrade_library(self.root, game_name="Taxi")

        self.assertEqual(result["upgraded"], 1)
        self.assertNotIn("vpinfe", self._info(self.root / "Dr. Dude"))


class RestoreTests(LibraryTestCase):
    def test_it_puts_back_everything_that_was_upgraded(self):
        for name in ("Dr. Dude", "Taxi"):
            self._game(name)
        upgrade_library(self.root)

        result = restore_library(self.root)

        self.assertEqual(result["restored"], 2)
        for name in ("Dr. Dude", "Taxi"):
            after = self._info(self.root / name)
            self.assertEqual(after["VPXFile"]["filehash"], "abc123")
            self.assertEqual(after["User"]["Rating"], 4)
            self.assertNotIn("vpinfe", after)

    def test_a_game_that_never_upgraded_is_left_alone(self):
        self._game("Dr. Dude")

        result = restore_library(self.root)

        self.assertEqual(result["restored"], 0)
        self.assertEqual(result["nothing_to_restore"], 1)
        self.assertIn("VPXFile", self._info(self.root / "Dr. Dude"))

    def test_the_current_file_is_kept_so_the_restore_is_reversible(self):
        game = self._game("Dr. Dude")
        upgrade_library(self.root)
        upgraded = (game / "Dr. Dude.info").read_text(encoding="utf-8")

        restore_library(self.root)

        backups = self._backups(game)
        self.assertEqual(len(backups), 2)
        self.assertIn(upgraded, [b.read_text(encoding="utf-8") for b in backups])

    def test_a_backup_this_build_cannot_read_is_passed_over_not_treated_as_the_end(self):
        """A 2.x build must not restore a schema 2 file, but the unversioned copy sitting
        behind it is still exactly what it wants. Newer backups are stepped over, not a
        dead end."""
        game = self._game("Dr. Dude")
        upgrade_library(self.root)
        restore_library(self.root)          # back to 2.x, and the schema 2 copy is kept

        as_2x = restorable_backup(game, max_schema=0)
        self.assertIsNotNone(as_2x)
        self.assertIsNone(backup_schema(as_2x), "2.x takes the unversioned copy")
        self.assertEqual(backup_schema(restorable_backup(game, max_schema=2)), 2)

    def test_the_newest_readable_backup_wins(self):
        game = self._game("Dr. Dude")
        upgrade_library(self.root)
        restore_library(self.root)
        (game / "Dr. Dude.info").write_text(
            json.dumps({**LEGACY, "User": {"Rating": 1}}), encoding="utf-8")
        upgrade_library(self.root)

        restore_library(self.root, max_schema=0)

        self.assertEqual(self._info(game)["User"]["Rating"], 1)

    def test_an_unreadable_backup_is_skipped_rather_than_restored(self):
        game = self._game("Dr. Dude")
        upgrade_library(self.root)
        (game / "Dr. Dude.info.vpinfe-20990101T000000Z").write_text("{ broken", "utf-8")

        result = restore_library(self.root)

        self.assertEqual(result["restored"], 1)
        self.assertEqual(self._info(game)["User"]["Rating"], 4)

    def test_a_corrupt_current_file_is_still_kept_before_being_replaced(self):
        """The file most likely to need restoring is the one too broken to parse. Refusing
        to keep it would block the rescue to protect a copy nobody wants back."""
        game = self._game("Dr. Dude")
        upgrade_library(self.root)
        (game / "Dr. Dude.info").write_text("{ truncated", encoding="utf-8")

        result = restore_library(self.root)

        self.assertEqual(result["restored"], 1)
        kept = [b.read_text(encoding="utf-8") for b in self._backups(game)]
        self.assertIn("{ truncated", kept)


class WalkTests(LibraryTestCase):
    def test_dot_folders_are_not_games(self):
        self._game("Dr. Dude")
        (self.root / ".hidden").mkdir()

        self.assertEqual([d.name for d in game_dirs(self.root)], ["Dr. Dude"])

    def test_a_missing_root_is_not_an_error(self):
        self.assertEqual(game_dirs(self.root / "nope"), [])


if __name__ == "__main__":
    unittest.main()


class WhatThePageSaysTests(LibraryTestCase):
    """Which of the three things the Tables page tells the user.

    The one that matters is a library a NEWER build upgraded: saying "I upgraded these"
    there is actively wrong, and it is the state every future schema bump creates.
    """

    def _game_at(self, schema, with_backup=True):
        game_dir = self.root / "Dr. Dude"
        game_dir.mkdir()
        (game_dir / "Dr. Dude.vpx").write_text("x", encoding="utf-8")
        live = {"Info": {}, "User": {"Rating": 4}, "vpinfe": {"schema": schema, "game_id": "a"},
                "tables": {"Dr. Dude.vpx": {"rom": "dd"}}}
        (game_dir / "Dr. Dude.info").write_text(json.dumps(live), encoding="utf-8")
        if with_backup:
            older = {**live, "vpinfe": {"schema": CURRENT_SCHEMA, "game_id": "a"}}
            (game_dir / "Dr. Dude.info.vpinfe-20260901T000000Z").write_text(
                json.dumps(older), encoding="utf-8")
        return game_dir

    def _counts(self):
        games = GameParser(str(self.root)).getAllGames()
        return {
            "pending_upgrade": sum(1 for t in games if t.info_pending_upgrade),
            "restorable": sum(1 for t in games if t.info_restorable),
            "newer_than_us": sum(1 for t in games
                                 if (schema_of(t.metaConfig) or 0) > CURRENT_SCHEMA),
        }

    def test_a_library_a_newer_build_upgraded_is_reported_as_that(self):
        self._game_at(CURRENT_SCHEMA + 1)

        counts = self._counts()

        self.assertEqual(counts["newer_than_us"], 1)
        self.assertEqual(counts["pending_upgrade"], 0)

    def test_a_library_this_build_upgraded_is_not(self):
        self._game_at(CURRENT_SCHEMA)

        counts = self._counts()

        self.assertEqual(counts["newer_than_us"], 0)
        self.assertEqual(counts["restorable"], 1)

    def test_a_library_nobody_has_upgraded_says_nothing(self):
        self._game_at(CURRENT_SCHEMA, with_backup=False)

        counts = self._counts()

        self.assertEqual(counts, {"pending_upgrade": 0, "restorable": 0, "newer_than_us": 0})
