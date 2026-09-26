"""What a PinballY library remembers about playing, and what of it crosses.

Pinned against the shape of a real file rather than a convenient one: UTF-16 with a BOM,
a key that is "<display name>.<system>", and names with dots and quotes in them. Of 746
rows in the real one, 92 had a play count and 33 had categories - so most of a stats file
is empty, and reading an empty cell as a zero would overwrite what is already here.
"""

from __future__ import annotations

import codecs
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


class EncodingTests(unittest.TestCase):
    TEXT = f"{HEADER}\nCafé (Williams 1988).Visual Pinball X,20221211012447,33,9191\n"
    ROWS = [("Café (Williams 1988)", 33)]

    def _read(self, data: bytes) -> tuple[list[tuple[str, int | None]], list]:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = Path(tmp.name) / gamestats.STATS_FILE
        path.write_bytes(data)
        found, notes = gamestats.read(path)
        return [(one.name, one.play_count) for one in found], notes

    def _sized(self, encoding: str, even: bool, text: str = TEXT) -> bytes:
        data = text.encode(encoding)
        return data if (len(data) % 2 == 0) == even else (text + "\n").encode(encoding)

    def test_every_encoding_it_meets_keeps_its_rows(self) -> None:
        lost = [gamestats.t("note.bytes_lost", file=gamestats.STATS_FILE)]
        cases = {
            "UTF-8, even": (self._sized("utf-8", True), []),
            "UTF-8, odd": (self._sized("utf-8", False), []),
            "UTF-8 with a mark, even": (self._sized("utf-8-sig", True), []),
            "UTF-8 with a mark, odd": (self._sized("utf-8-sig", False), []),
            "UTF-16 with a mark": (self.TEXT.encode("utf-16"), []),
            "UTF-16 BE with a mark": (codecs.BOM_UTF16_BE + self.TEXT.encode("utf-16-be"),
                                      []),
            "UTF-16 LE without a mark": (self.TEXT.encode("utf-16-le"), []),
            "UTF-16 BE without a mark": (self.TEXT.encode("utf-16-be"), []),
            "Windows-1252, even": (self._sized("cp1252", True), lost),
            "Windows-1252, odd": (self._sized("cp1252", False), lost),
        }
        for said, (data, notes) in cases.items():
            with self.subTest(said):
                self.assertEqual(self._read(data), (self.ROWS, notes))

    def test_a_file_longer_than_a_csv_field_keeps_its_rows(self) -> None:
        text = HEADER + "\n" + "".join(
            f"Café {n} (Williams 1988).Visual Pinball X,20221211012447,{n},9191\n"
            for n in range(5000))
        for encoding in ("cp1252", "utf-16-be"):
            with self.subTest(encoding):
                found, _ = self._read(self._sized(encoding, True, text))
                self.assertEqual((len(found), found[-1]),
                                 (5000, ("Café 4999 (Williams 1988)", 4999)))

    def test_a_file_cut_short_after_its_mark_keeps_the_rows_before_the_cut(self) -> None:
        self.assertEqual(self._read(self.TEXT.encode("utf-16") + b"\x00"),
                         (self.ROWS, [gamestats.t("note.bytes_lost",
                                                  file=gamestats.STATS_FILE)]))

    def test_an_empty_file_says_nothing(self) -> None:
        self.assertEqual(self._read(b""), ([], []))


if __name__ == "__main__":
    unittest.main()
