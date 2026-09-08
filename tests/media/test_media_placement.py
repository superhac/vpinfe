"""Placing a media file, and moving one between tiers.

The tier is the filename, so both operations are naming operations: `displaced` says
which names a write would take over, and `retier` changes which name a file already
has. Both are tested against a real folder because what they mean is what is on disk.
"""

from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from common.games import media_placement
from common.games.media_placement import UnplaceableError

KIND = "backglass"
GAME = "MyGame"
BUILD = "MyGame - build1"


class PlacementTests(unittest.TestCase):
    def setUp(self) -> None:
        self._dir = TemporaryDirectory()
        self.addCleanup(self._dir.cleanup)
        self.root = Path(self._dir.name)
        (self.root / "medias").mkdir()

    def _source(self, name: str = "source.png") -> Path:
        path = self.root / name
        path.write_bytes(b"bytes")
        return path

    def _medias(self) -> list[str]:
        return sorted(p.name for p in (self.root / "medias").iterdir())

    def test_nothing_is_displaced_in_an_empty_slot(self) -> None:
        self.assertEqual(media_placement.displaced(self.root, KIND, GAME, ".png"), [])

    def test_the_file_with_the_same_name_is_displaced(self) -> None:
        media_placement.place(self.root, KIND, GAME, self._source())

        going = media_placement.displaced(self.root, KIND, GAME, ".png")

        self.assertEqual([p.name for p in going], ["(Backglass) MyGame.png"])

    def test_a_different_extension_displaces_the_whole_family(self) -> None:
        """The surprising one: a .jpg dropped over a .png takes the .png, because one
        kind holds one file at a tier and the name is not the same name."""
        media_placement.place(self.root, KIND, GAME, self._source())

        going = media_placement.displaced(self.root, KIND, GAME, ".jpg")

        self.assertEqual([p.name for p in going], ["(Backglass) MyGame.png"])

    def test_displaced_names_exactly_what_place_removes(self) -> None:
        """The two must not drift: a confirmation built on `displaced` is only honest
        while it lists what `place` actually takes."""
        media_placement.place(self.root, KIND, GAME, self._source())
        predicted = {p.name for p in media_placement.displaced(self.root, KIND, GAME,
                                                               ".jpg")}

        media_placement.place(self.root, KIND, GAME, self._source("other.jpg"))

        self.assertEqual(set(self._medias()) & predicted, set())
        self.assertEqual(self._medias(), ["(Backglass) MyGame.jpg"])


class RetierTests(PlacementTests):
    def test_a_builds_file_takes_the_folder_name(self) -> None:
        media_placement.place(self.root, KIND, BUILD, self._source())

        media_placement.retier(self.root, KIND, BUILD, GAME)

        self.assertEqual(self._medias(), ["(Backglass) MyGame.png"])

    def test_the_extension_survives_the_move(self) -> None:
        media_placement.place(self.root, KIND, BUILD, self._source("art.jpg"))

        media_placement.retier(self.root, KIND, BUILD, GAME)

        self.assertEqual(self._medias(), ["(Backglass) MyGame.jpg"])

    def test_moving_onto_an_occupied_tier_replaces_what_is_there(self) -> None:
        """Same rule as a drop - the arriving file wins and the other one goes, rather
        than sitting behind it forever."""
        media_placement.place(self.root, KIND, GAME, self._source("old.png"))
        media_placement.place(self.root, KIND, BUILD, self._source("new.jpg"))

        media_placement.retier(self.root, KIND, BUILD, GAME)

        self.assertEqual(self._medias(), ["(Backglass) MyGame.jpg"])

    def test_moving_a_file_that_is_not_there_is_refused(self) -> None:
        with self.assertRaises(UnplaceableError):
            media_placement.retier(self.root, KIND, BUILD, GAME)


if __name__ == "__main__":
    unittest.main()
