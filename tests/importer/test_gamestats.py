"""What a PinballY library remembers about playing, and what of it crosses.

Pinned against the shape of a real file rather than a convenient one: UTF-16 with a BOM,
a key that is "<display name>.<system>", and names with dots and quotes in them. Of 746
rows in the real one, 92 had a play count and 33 had categories - so most of a stats file
is empty, and reading an empty cell as a zero would overwrite what is already here.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from common.extensions import host

host.Registry().load(host.BUNDLED_DIR / "library_importer")

from vpinfe_ext_library_importer import gamestats  # noqa: E402

HEADER = ("Game,Last Played,Play Count,Play Time,Is Favorite,Rating,Audio Volume,"
          "Categories,Is Hidden,Date Added,High Score Style,Marked For Capture,"
          "Show When Running")


class ReadTests(unittest.TestCase):
    def _file(self, *rows: str) -> Path:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = Path(tmp.name) / gamestats.STATS_FILE
        path.write_bytes("\n".join((HEADER, *rows)).encode("utf-16"))
        return path

    def test_it_reads_the_encoding_the_frontend_writes(self) -> None:
        """UTF-16 with a BOM. Read as UTF-8 the whole file fails, not one row."""
        found, notes = gamestats.read(
            self._file("Taxi (Williams 1988).Visual Pinball X,20221211012447,33,9191"))

        self.assertEqual(notes, [])
        self.assertEqual(found[0].play_count, 33)
        self.assertEqual(found[0].play_time_seconds, 9191)

    def test_the_key_is_a_display_name_and_a_system(self) -> None:
        found, _ = gamestats.read(
            self._file("Taxi (Williams 1988).Visual Pinball X,,1,2"))

        self.assertEqual(found[0].name, "Taxi (Williams 1988)")
        self.assertEqual(found[0].system, "Visual Pinball X")

    def test_a_name_with_dots_in_it_keeps_them(self) -> None:
        """Split from the right: a game's own name holds dots far more often than a
        system's does, and "1.2.3... (Talleres 1973)" is a real row."""
        found, _ = gamestats.read(
            self._file("1.2.3... (Talleres 1973).Visual Pinball X,,4,5"))

        self.assertEqual(found[0].name, "1.2.3... (Talleres 1973)")
        self.assertEqual(found[0].system, "Visual Pinball X")

    def test_an_empty_cell_is_absent_and_not_a_zero(self) -> None:
        """The distinction the whole import rests on: a game nobody played and a game
        whose count was never written are different, and only one should overwrite what
        is already here."""
        found, _ = gamestats.read(
            self._file("Taxi (Williams 1988).Visual Pinball X,,,,,,,Verified"))

        self.assertIsNone(found[0].play_count)
        self.assertIsNone(found[0].play_time_seconds)
        self.assertIsNone(found[0].last_played)
        self.assertEqual(found[0].tags, ("Verified",))

    def test_a_row_that_remembers_nothing_is_left_out(self) -> None:
        found, _ = gamestats.read(
            self._file("Taxi (Williams 1988).Visual Pinball X,,,,,,,,,20190515040000"))

        self.assertEqual(found, [])

    def test_a_date_is_read_as_the_time_somebody_was_standing_there(self) -> None:
        """No zone is written beside it, so it is local. Reading it as UTC moves every
        date by however far the machine is from Greenwich."""
        import datetime

        found, _ = gamestats.read(
            self._file("Taxi (Williams 1988).Visual Pinball X,20221211012447,1,2"))

        when = datetime.datetime.fromtimestamp(found[0].last_played)
        self.assertEqual(when.strftime("%Y%m%d%H%M%S"), "20221211012447")

    def test_a_date_that_is_not_one_is_absent(self) -> None:
        found, _ = gamestats.read(
            self._file("Taxi (Williams 1988).Visual Pinball X,nonsense,1,2"))

        self.assertIsNone(found[0].last_played)

    def test_categories_become_tags(self) -> None:
        found, _ = gamestats.read(
            self._file("Taxi (Williams 1988).Visual Pinball X,,1,2,,,,\"Verified, Fun\""))

        self.assertEqual(found[0].tags, ("Verified", "Fun"))

    def test_no_file_is_not_an_error(self) -> None:
        """A source without one is a source whose owner never played through it."""
        found, notes = gamestats.read(Path("/nowhere/GameStats.csv"))

        self.assertEqual((found, notes), ([], []))


if __name__ == "__main__":
    unittest.main()
