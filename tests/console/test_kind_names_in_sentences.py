"""A media kind's name inside a sentence reads as the catalog gives it."""

from __future__ import annotations

import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, call, patch

from console import mediamap, mediasource

LIBRARY = SimpleNamespace(placements=None, displaced_by=None, place_media=None,
                          import_media=None)


async def _nothing() -> None:
    return None


class KindNamesInSentences(unittest.TestCase):
    def test_the_replace_question(self) -> None:
        with patch.object(mediasource.confirm, "ask", AsyncMock(return_value=True)) as ask:
            asyncio.run(mediasource.confirm_replace("Real DMD", ["old.png"]))

        self.assertEqual(ask.call_args.args[0], "Replace the Real DMD that is there?")

    def test_a_folder_with_nothing_to_use(self) -> None:
        folder = mediasource._Folder({"library": LIBRARY, "game_id": "game", "game": {}},
                                     "pup_pack", "PUP Pack", _nothing)
        with patch.object(mediasource, "ui") as ui, \
                patch.object(mediasource.offload, "io",
                             AsyncMock(return_value={"path": "", "entries": []})):
            asyncio.run(folder._show_folder(MagicMock(), ""))

        self.assertIn(call("Nothing here to use as PUP Pack"), ui.label.call_args_list)

    def test_a_file_already_in_a_slot(self) -> None:
        slot = mediasource._Slot(
            {"library": LIBRARY, "game_id": "game", "game": {}, "lens": "",
             "media": {"scoreview": {"file": "afm.png"}}},
            "wheel", "Wheel", _nothing, mediasource._media(LIBRARY, "wheel"))

        self.assertEqual(slot._in_use("afm.png"), "Already the DMD")

    def test_an_empty_tile(self) -> None:
        self.assertEqual(mediamap._tooltip("playfield_fss", {"present": False}),
                         "No Playfield FSS")


if __name__ == "__main__":
    unittest.main()
