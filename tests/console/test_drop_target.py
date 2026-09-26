"""Which game a drop on a row of a file grid means."""

from __future__ import annotations

import unittest
from unittest.mock import Mock

from console import page, uploads
from console.data import Library

GAME = {"id": "g-1", "name": "Some Game", "folder": "/games/Some Game"}


def _library() -> tuple[Library, Mock]:
    client = Mock()
    client.library_policy.return_value = {}
    client.all_tables.return_value = [{"id": "t-1", "game_id": "g-1"}]
    client.all_media.return_value = [{"id": "g-1:wheel:", "game_id": "g-1", "kind": "wheel"}]
    client.all_assets.return_value = [{"id": "g-1:pov:", "game_id": "g-1", "kind": "pov"}]
    library = Library(client)
    library.games = [GAME]
    return library, client


def _dropped(library: Library, view: str, row_id: str) -> tuple[str, str, str]:
    drop = uploads.Drop(target=uploads.TARGET_GAME, row_id=row_id, upload_id="u-1",
                        name="some.file")
    return page._drop_target(library, {"view": view}, drop)


class ADropOnAFileRow(unittest.TestCase):
    def test_a_tables_row_names_its_game(self) -> None:
        library, _client = _library()

        self.assertEqual(_dropped(library, "tables", "t-1"), ("g-1", GAME["folder"], ""))

    def test_an_assets_row_names_its_game(self) -> None:
        library, _client = _library()

        self.assertEqual(_dropped(library, "assets", "g-1:pov:"), ("g-1", GAME["folder"], ""))

    def test_a_media_row_names_its_game_after_a_write_let_the_rows_go(self) -> None:
        library, client = _library()
        library.load_media_rows()
        library.forget_media("g-1")

        self.assertEqual(_dropped(library, "media", "g-1:wheel:"),
                         ("g-1", GAME["folder"], ""))
        self.assertEqual(client.all_media.call_count, 2)

    def test_a_row_that_is_not_there_names_nothing(self) -> None:
        library, _client = _library()

        self.assertEqual(_dropped(library, "media", "g-9:wheel:"), ("", "", ""))


if __name__ == "__main__":
    unittest.main()
