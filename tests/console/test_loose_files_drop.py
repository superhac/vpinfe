"""A drop of several files that share no folder is counted, not named."""

from __future__ import annotations

import unittest
from typing import Any
from unittest.mock import AsyncMock, Mock, patch

from common.i18n import t
from console import import_dialog, mediasource, page, uploads
from tests.support.clicks import press

GAME = {"id": "g-1", "name": "Medieval Madness", "folder": "/games/Medieval Madness",
        "rom": "mm_109c"}
PLANNED = {"game_dir": GAME["folder"], "blocked": [],
           "items": [{"index": 0, "kind": "backglass",
                      "destination": "/games/Medieval Madness/Medieval Madness.directb2s"}]}


async def _now(callback: Any, *args: Any, **kwargs: Any) -> Any:
    return callback(*args, **kwargs)


class TheTitleTests(unittest.TestCase):
    def test_loose_files_are_counted(self) -> None:
        self.assertEqual(import_dialog.dropped_title("", 3),
                         t("console.import_dialog.import_files", count=3))

    def test_a_drop_with_a_name_is_named(self) -> None:
        self.assertEqual(import_dialog.dropped_title("Medieval Madness", 3),
                         t("console.import_dialog.import_2", name="Medieval Madness"))

    def test_a_drop_with_neither_is_this_drop(self) -> None:
        self.assertEqual(import_dialog.dropped_title("", 0),
                         t("console.import_dialog.import_drop"))


class TheCountReachesTheDialogTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.library = Mock(games=[GAME])
        self.library.upload_plan.return_value = PLANNED
        self.library.tables_for.return_value = []
        self.shown = AsyncMock()
        for patched in (patch("console.offload.run.io_bound", new=_now),
                        patch.object(uploads, "analyzed", new=AsyncMock(return_value={})),
                        patch.object(import_dialog, "open_for", new=self.shown)):
            patched.start()
            self.addCleanup(patched.stop)

    def opened_with(self) -> tuple[str, int]:
        opened = self.shown.await_args
        assert opened is not None
        return opened.kwargs["source"], opened.kwargs["file_count"]

    async def test_from_the_grid(self) -> None:
        drop = uploads.Drop(target=uploads.TARGET_GAME, row_id="g-1", upload_id="u-1",
                            count=3)
        await press(page._took_a_drop, self.library, {"view": "games"}, Mock(), drop)

        self.assertEqual(("", 3), self.opened_with())

    async def test_from_a_panel(self) -> None:
        context = {"library": self.library, "game_id": "g-1", "game": GAME}
        sources = mediasource._Folder(context, "backglass", "Backglass", AsyncMock())

        await press(sources.arrived, uploads.Drop(upload_id="u-1", count=3))

        self.assertEqual(("", 3), self.opened_with())


if __name__ == "__main__":
    unittest.main()
