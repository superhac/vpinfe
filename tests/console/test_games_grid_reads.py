"""What the Games grid reads before it draws, after an import let the page's copy go."""

from __future__ import annotations

import unittest
from unittest.mock import Mock

from console import page
from console.data import Library

GAME = {"id": "g-1", "name": "Some Game", "folder": "/games/Some Game"}


def _library() -> tuple[Library, Mock]:
    client = Mock()
    client.games.return_value = [GAME]
    client.library_game_collections.return_value = {}
    client.all_media.return_value = [
        {"id": "g-1:wheel:", "game_id": "g-1", "kind": "wheel", "present": True,
         "file": "wheel.png"}]
    library = Library(client)
    library.games = [GAME]
    library.media = library._shared_media()
    library.load_game_collections()
    return library, client


class TheGamesGridAfterAnImport(unittest.TestCase):
    def test_it_reads_its_media_again_before_it_draws(self) -> None:
        library, _client = _library()
        library.refresh_after_import()

        reads = page.reads_before_drawing("games", library)

        assert reads is not None
        reads()
        self.assertEqual(library.kinds_present(), ["wheel"])
        self.assertIn("media_wheel", library.game_rows()[0])

    def test_it_reads_the_media_once_for_every_game(self) -> None:
        library, client = _library()
        library.refresh_after_import()
        client.all_media.reset_mock()
        reads = page.reads_before_drawing("games", library)

        assert reads is not None
        reads()
        self.assertEqual(client.all_media.call_count, 1)

    def test_it_reads_nothing_when_it_holds_what_it_draws(self) -> None:
        library, _client = _library()

        self.assertIsNone(page.reads_before_drawing("games", library))


if __name__ == "__main__":
    unittest.main()
