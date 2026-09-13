"""Putting a ROM set, a sound bank or a colour set into a game.

The things that are neither the game file nor artwork live in a folder of their own, and
which folder is the registry's answer - the same one an upload gets. That is the point:
a library imported from another frontend has to put them where an upload would have, or
the two ways in disagree about where a game's ROM is.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from common.extensions.contract import ContractError
from common.extensions.games import ExtensionGames


class _Files:
    def __init__(self, *roots: Path) -> None:
        self._roots = tuple(str(one) for one in roots)

    def roots(self):
        return self._roots


class PutAssetCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.source = self.root / "source"
        self.source.mkdir()
        self.game = self.root / "Attack from Mars (Bally 1995)"
        self.game.mkdir()
        self.games = ExtensionGames("probe", ("games:read", "games:write"),
                                    _Files(self.source))
        self.games.folder = lambda game_id: str(self.game)


class DestinationTests(PutAssetCase):
    def test_a_rom_lands_where_an_upload_would_have_put_it(self) -> None:
        rom = self.source / "afm_113b.zip"
        rom.write_bytes(b"rom")

        where = self.games.put_asset("g1", "rom", rom)

        self.assertEqual(where, "pinmame/roms/afm_113b.zip")
        self.assertTrue((self.game / where).is_file())

    def test_a_bank_keyed_on_a_rom_lands_under_it(self) -> None:
        bank = self.source / "afm"
        bank.mkdir()
        (bank / "altsound.csv").write_text("x")

        where = self.games.put_asset("g1", "altsound", bank, rom="afm_113b")

        self.assertEqual(where, "pinmame/altsound/afm_113b/afm")
        self.assertTrue((self.game / where / "altsound.csv").is_file())

    def test_a_whole_folder_comes_across(self) -> None:
        """An asset arrives as a directory as often as a file."""
        pack = self.source / "pup"
        (pack / "deep").mkdir(parents=True)
        (pack / "deep" / "clip.mp4").write_text("video")

        where = self.games.put_asset("g1", "pup_pack", pack)

        self.assertTrue((self.game / where / "deep" / "clip.mp4").is_file())

    def test_a_kind_that_needs_a_rom_says_so(self) -> None:
        bank = self.source / "afm"
        bank.mkdir()

        with self.assertRaises(ValueError) as caught:
            self.games.put_asset("g1", "altsound", bank)
        self.assertIn("ROM", str(caught.exception))

    def test_a_kind_with_no_folder_of_its_own_is_refused(self) -> None:
        """A backglass sits beside the game file and is named after it, so "which
        folder" is the wrong question and a made-up answer would be worse."""
        glass = self.source / "x.directb2s"
        glass.write_bytes(b"glass")

        with self.assertRaises(ValueError):
            self.games.put_asset("g1", "backglass", glass)


class BoundsTests(PutAssetCase):
    def test_it_will_not_take_something_outside_what_it_declared(self) -> None:
        stray = self.root / "stray.zip"
        stray.write_bytes(b"rom")

        with self.assertRaises(ContractError):
            self.games.put_asset("g1", "rom", stray)

    def test_it_will_not_write_over_what_is_already_there(self) -> None:
        rom = self.source / "afm_113b.zip"
        rom.write_bytes(b"rom")
        self.games.put_asset("g1", "rom", rom)

        with self.assertRaises(FileExistsError):
            self.games.put_asset("g1", "rom", rom)

    def test_placing_needs_the_write_scope(self) -> None:
        rom = self.source / "afm_113b.zip"
        rom.write_bytes(b"rom")
        reader = ExtensionGames("reader", ("games:read",), _Files(self.source))
        reader.folder = lambda game_id: str(self.game)

        with self.assertRaises(ContractError):
            reader.put_asset("g1", "rom", rom)


if __name__ == "__main__":
    unittest.main()
