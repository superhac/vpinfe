"""The shared media spec table, and the payload built from it."""

from __future__ import annotations

import os
import unittest

from common.media_specs import apply_media_specs, game_media_payload, media_filename_map
from tests.support.library import fake_game


class MediaSpecTests(unittest.TestCase):
    def test_media_specs_apply_and_payload_use_shared_specs(self) -> None:
        root = os.path.join(os.sep, "tmp", "Table")
        game = fake_game(root, PlayfieldImagePath=None, BGImagePath=None)

        apply_media_specs(
            game,
            game_contents={"bg.png"},
            medias_contents={"fss.png"},
            playfield_variant="fss",
        )

        self.assertEqual(game.BGImagePath, os.path.join(root, "bg.png"))
        self.assertEqual(game.PlayfieldImagePath, os.path.join(root, "medias", "fss.png"))
        self.assertEqual(media_filename_map("fss")["playfield"], "fss.png")
        self.assertEqual(game_media_payload(game)["PlayfieldImagePath"],
                         os.path.join(root, "medias", "fss.png"))


if __name__ == "__main__":
    unittest.main()
