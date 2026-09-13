"""Reading a PinUP Popper library.

Written after the reader met a real database for the first time. What is pinned is the
schema's shape and the two things that database settled: Popper records the extension
each emulator plays, always, and it records a game's media key separately from its name.

The fixture is built here rather than copied. The schema is a fact about Popper; a
library is somebody's own.
"""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from common.extensions import host

host.Registry().load(host.BUNDLED_DIR / "library_importer")

from vpinfe_ext_library_importer import popper  # noqa: E402

EMULATORS = ("EMUID integer primary key, EmuName text, Description text, DirGames text, "
             "DirMedia text, EmuDisplay text, Visible integer, DirRoms text, "
             "GamesExt text")
GAMES = ("GameID integer primary key, EMUID integer, GameName text, GameFileName text, "
         "GameDisplay text, Visible integer, GameYear text, ROM text, Manufact text, "
         "GameType text, GameTheme text, GameRating text, IPDBNum text, "
         "MediaSearch text")


class PopperCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

    def _library(self, emulators, games) -> Path:
        db = sqlite3.connect(self.root / popper.DATABASE)
        db.execute(f"create table Emulators ({EMULATORS})")
        db.execute(f"create table Games ({GAMES})")
        db.executemany(
            "insert into Emulators (EMUID, EmuName, DirGames, DirRoms, Visible, "
            "GamesExt) values (?, ?, ?, ?, ?, ?)", emulators)
        db.executemany(
            "insert into Games (GameID, EMUID, GameName, GameFileName, GameDisplay, "
            "Visible, GameYear, ROM, Manufact) values (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            games)
        db.commit()
        db.close()
        return self.root


class ReadTests(PopperCase):
    def test_a_folder_with_the_database_is_claimed(self) -> None:
        self.assertTrue(popper.detect(self._library([], [])))

    def test_a_folder_without_one_is_not(self) -> None:
        self.assertFalse(popper.detect(self.root))

    def test_the_games_of_an_emulator_are_read(self) -> None:
        root = self._library(
            [(1, "Visual Pinball X", "", "", 1, "vpx")],
            [(1, 1, "Taxi (Williams 1988)", "Taxi (Williams 1988).vpx", "Taxi", 1,
              "1988", "taxi_l4", "Williams")])

        library = popper.read(root)

        self.assertEqual(len(library.games), 1)
        self.assertEqual(library.games[0].rom, "taxi_l4")

    def test_the_long_name_is_the_display_name_and_not_the_short_one(self) -> None:
        """Counter-intuitive, and worth pinning because it reads backwards: `GameName`
        holds the whole "Title (Manufacturer Year) version" a person sees, and
        `GameDisplay` holds the shorter title. A real library had "The Addams Family
        (Bally 1992) 2.4.41" in the first and "Leprechaun King" in the second."""
        root = self._library(
            [(1, "Visual Pinball X", "", "", 1, "vpx")],
            [(1, 1, "Leprechaun King (Orbital 2020)",
              "Leprechaun King (Orbital 2020).vpx", "Leprechaun King", 1, "", "", "")])

        found = popper.read(root).games[0]

        self.assertEqual(found.display_name, "Leprechaun King (Orbital 2020)")
        self.assertEqual(found.title, "Leprechaun King")

    def test_a_row_with_no_name_is_reported_rather_than_dropped(self) -> None:
        root = self._library(
            [(1, "Visual Pinball X", "", "", 1, "vpx")],
            [(1, 1, "", "", "", 1, "", "", "")])

        library = popper.read(root)

        self.assertEqual(library.games, ())
        self.assertTrue(any("no name" in note for note in library.notes))


class PlayableTests(PopperCase):
    """Which emulators come across.

    Popper records the extension per emulator and always fills it in, which neither of
    the other sources does - so this filter is one column here rather than three guesses.
    """

    def _read(self, plays=None):
        root = self._library(
            [(1, "Visual Pinball X", "", "", 1, "vpx"),
             (2, "Future Pinball", "", "", 1, "fpt"),
             (3, "PC Games", "", "", 1, "lnk")],
            [(1, 1, "Taxi", "Taxi.vpx", "Taxi", 1, "", "", ""),
             (2, 2, "BBB", "BBB.fpt", "BBB", 1, "", "", "")])
        return popper.read(root, plays)

    def test_only_what_this_build_plays_comes_across(self) -> None:
        found = self._read()

        self.assertEqual([one.name for one in found.systems], ["Visual Pinball X"])

    def test_what_was_left_is_named(self) -> None:
        said = [one for one in self._read().notes if "does not play" in one]

        self.assertTrue(said)
        self.assertIn("Future Pinball", said[0])
        self.assertIn("PC Games", said[0])

    def test_an_extension_providing_an_app_changes_the_answer(self) -> None:
        found = self._read(plays=lambda suffix: suffix in (".vpx", ".fpt"))

        self.assertEqual(sorted(one.name for one in found.systems),
                         ["Future Pinball", "Visual Pinball X"])

    def test_an_emulator_that_records_no_extension_is_kept(self) -> None:
        """Saying nothing is not saying no, and a blank column should not drop a
        library."""
        root = self._library([(1, "Something", "", "", 1, "")],
                             [(1, 1, "A", "A.vpx", "A", 1, "", "", "")])

        self.assertEqual([one.name for one in popper.read(root).systems], ["Something"])


if __name__ == "__main__":
    unittest.main()
