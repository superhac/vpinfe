"""The import dialog's rows, following the new game's folder name as it is typed."""

from __future__ import annotations

import unittest
from typing import Any
from unittest.mock import Mock, patch

from console import import_dialog

ASKED: dict[str, Any] = {"game_dir": "", "rom_name": "", "allow_new_game": True,
                         "media_kind": "", "location_id": "", "asset_kind": "",
                         "add_table": False}
ROW: dict[str, Any] = {"index": 0, "name": "wheel.png", "action": "replace_media",
                       "destination": "/games/New Name/medias/(Wheel) New Name.png"}
RENAMED: dict[str, Any] = {"game_dir": "/games/New Name", "new_game_dir_name": "New Name",
                           "items": [ROW]}


async def _now(callback: Any, *args: Any, **kwargs: Any) -> Any:
    return callback(*args, **kwargs)


class TheRowsFollowTheFolderName(unittest.IsolatedAsyncioTestCase):
    def _following(self, library: Mock) -> tuple[dict[str, Any], Mock, Any]:
        named: dict[str, Any] = {"folder": "Old Name", "vps_id": ""}
        redraw = Mock()
        with patch.object(import_dialog.ui, "timer") as timer:
            import_dialog._following(library, "u-1", ASKED, named, redraw)
        return named, redraw, timer.call_args.args[1]

    async def test_a_new_name_is_planned_and_the_rows_redrawn(self) -> None:
        library = Mock()
        library.upload_plan.return_value = RENAMED
        named, redraw, look = self._following(library)

        named["folder"] = "New Name"
        with patch("console.offload.run.io_bound", new=_now):
            await look()

        library.upload_plan.assert_called_once_with(
            "u-1", **ASKED, vps_id="", new_game_dir_name="New Name")
        redraw.assert_called_once_with(RENAMED)
        self.assertEqual("medias/(Wheel) New Name.png", import_dialog._where(RENAMED, ROW))

    async def test_the_same_name_asks_nothing(self) -> None:
        library = Mock()
        _named, redraw, look = self._following(library)

        await look()

        library.upload_plan.assert_not_called()
        redraw.assert_not_called()

    async def test_a_name_the_install_refuses_leaves_the_rows(self) -> None:
        library = Mock()
        library.upload_plan.side_effect = RuntimeError("needs a name")
        named, redraw, look = self._following(library)

        named["folder"] = ""
        with patch("console.offload.run.io_bound", new=_now):
            await look()

        redraw.assert_not_called()


if __name__ == "__main__":
    unittest.main()
