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
from common.i18n import t
from common.media_specs import MEDIA_SPECS

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

    def test_a_file_under_another_token_is_displaced_and_replaced(self) -> None:
        for kind, token, alias in (("flyer", "(Flyer)", "(GameInfo)"),
                                   ("instruction_card", "(InstructionCard)", "(RuleCard)"),
                                   ("instruction_card", "(InstructionCard)", "(GameHelp)")):
            with self.subTest(alias=alias):
                old = self.root / "medias" / f"{alias} {BUILD}.png"
                old.write_bytes(b"old")

                going = media_placement.displaced(self.root, kind, BUILD, ".jpg")
                media_placement.place(self.root, kind, BUILD, self._source("new.jpg"))

                self.assertEqual([p.name for p in going], [old.name])
                self.assertEqual(self._medias(), [f"{token} {BUILD}.jpg"])
                (self.root / "medias" / f"{token} {BUILD}.jpg").unlink()

    def test_a_file_spelled_in_another_case_is_named_as_it_is_and_replaced(self) -> None:
        (self.root / "medias" / "(backglass) mygame.png").write_bytes(b"old")

        going = media_placement.displaced(self.root, KIND, GAME, ".png")
        media_placement.place(self.root, KIND, GAME, self._source())

        self.assertEqual([p.name for p in going], ["(backglass) mygame.png"])
        self.assertEqual(self._medias(), ["(Backglass) MyGame.png"])


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

    def test_a_file_under_another_token_moves(self) -> None:
        (self.root / "medias" / f"(GameInfo) {BUILD}.png").write_bytes(b"flyer")

        media_placement.retier(self.root, "flyer", BUILD, GAME)

        self.assertEqual(self._medias(), ["(Flyer) MyGame.png"])

    def test_the_file_that_shows_is_the_one_that_moves(self) -> None:
        cases = (("instruction_card", self.root / "medias" / f"(GameHelp) {BUILD}.png",
                  self.root / "medias" / f"(InstructionCard) {BUILD}.png",
                  "(InstructionCard) MyGame.png"),
                 (KIND, self.root / f"(Backglass) {BUILD}.png",
                  self.root / "medias" / f"(Backglass) {BUILD}.png",
                  "(Backglass) MyGame.png"))
        for kind, behind, shows, moved in cases:
            with self.subTest(shows=shows.name, behind=behind.name):
                behind.write_bytes(b"behind")
                shows.write_bytes(b"shows")

                media_placement.retier(self.root, kind, BUILD, GAME)

                self.assertEqual(b"shows", (self.root / "medias" / moved).read_bytes())
                for path in media_placement.displaced(self.root, kind, GAME, ".png"):
                    path.unlink()

    def test_the_rest_of_the_family_moves_behind_it(self) -> None:
        """Left at the table's tier, a file behind the one that moved goes on serving
        that table as its own."""
        shows = self.root / "medias" / f"(Flyer) {BUILD}.png"
        family = (shows, self.root / "medias" / f"(Flyer) {BUILD}.jpg",
                  self.root / f"(Flyer) {BUILD}.png",
                  self.root / "medias" / f"(GameInfo) {BUILD}.png")
        for path in family:
            path.write_bytes(path.name.encode())

        media_placement.retier(self.root, "flyer", BUILD, GAME)

        self.assertEqual([], media_placement.displaced(self.root, "flyer", BUILD, ".png"))
        self.assertEqual(["(Flyer) MyGame.jpg", "(Flyer) MyGame.png", "(GameInfo) MyGame.png"],
                         self._medias())
        self.assertEqual(shows.name.encode(),
                         (self.root / "medias" / "(Flyer) MyGame.png").read_bytes())
        self.assertEqual(family[2].name.encode(),
                         (self.root / "(Flyer) MyGame.png").read_bytes())

    def test_moving_a_file_that_is_not_there_is_refused(self) -> None:
        with self.assertRaises(UnplaceableError) as caught:
            media_placement.retier(self.root, KIND, BUILD, GAME)

        self.assertEqual(str(caught.exception),
                         t("error.games.nothing_in_slot_to_move",
                           slot=t("media.kind.backglass.label"), name=BUILD))

    def test_a_file_the_slot_does_not_take_names_what_it_does(self) -> None:
        spec = next(one for one in MEDIA_SPECS if one.kind == KIND)
        with self.assertRaises(UnplaceableError) as caught:
            media_placement.place(self.root, KIND, GAME, self._source("theme.mp3"))

        self.assertEqual(str(caught.exception),
                         t("error.games.slot_does_not_take", slot=spec.label,
                           extension=".mp3", join=", ".join(spec.family)))
        self.assertEqual(self._medias(), [])


class RemoveTests(unittest.TestCase):
    def setUp(self) -> None:
        self._dir = TemporaryDirectory()
        self.addCleanup(self._dir.cleanup)
        self.root = Path(self._dir.name)
        (self.root / "medias").mkdir()

    def _medias(self) -> list[str]:
        return sorted(p.name for p in (self.root / "medias").iterdir())

    def test_a_file_under_another_token_goes(self) -> None:
        for kind, alias in (("flyer", "(GameInfo)"), ("instruction_card", "(RuleCard)"),
                            ("instruction_card", "(GameHelp)")):
            with self.subTest(alias=alias):
                (self.root / "medias" / f"{alias} {BUILD}.png").write_bytes(b"art")

                removed = media_placement.remove(self.root, kind, BUILD)

                self.assertEqual(removed, [f"medias/{alias} {BUILD}.png"])
                self.assertEqual(self._medias(), [])

    def test_a_file_spelled_in_another_case_goes_under_its_own_name(self) -> None:
        (self.root / "medias" / "(backglass) mygame.png").write_bytes(b"art")

        removed = media_placement.remove(self.root, KIND, GAME)

        self.assertEqual(removed, ["medias/(backglass) mygame.png"])
        self.assertEqual(self._medias(), [])

    def test_the_whole_family_goes_from_both_folders_and_no_other_tier(self) -> None:
        for name in (f"(Backglass) {BUILD}.png", f"(Backglass) {BUILD}.jpg",
                     "(Backglass) MyGame.png"):
            (self.root / "medias" / name).write_bytes(b"art")
        (self.root / f"(Backglass) {BUILD}.png").write_bytes(b"art")

        removed = media_placement.remove(self.root, KIND, BUILD)

        self.assertEqual(sorted(removed), [f"(Backglass) {BUILD}.png",
                                           f"medias/(Backglass) {BUILD}.jpg",
                                           f"medias/(Backglass) {BUILD}.png"])
        self.assertEqual(self._medias(), ["(Backglass) MyGame.png"])


if __name__ == "__main__":
    unittest.main()
