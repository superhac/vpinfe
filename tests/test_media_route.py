"""The /media/<game_id>/<kind> route the contract-2 payload addresses.

Contract 2 names the kinds a game has and leaves the bytes to be fetched, so this route
is what makes that payload usable. The lookup is tested directly; the handler is tested
through a real request, because the parts that matter - conditional GET, Range, the 404 -
only exist at the HTTP layer.
"""

from __future__ import annotations

import json
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest import mock
from tempfile import TemporaryDirectory

from common.games import media_lookup
from common.games.gameparser import GameParser
from frontend.customhttpserver import CustomHTTPServer


def _library(root: Path) -> None:
    game = root / "Example Game (Bally 1990)"
    (game / "medias").mkdir(parents=True)
    (game / "Example Game (Bally 1990).vpx").write_bytes(b"vpx")
    (game / "medias" / "wheel.png").write_bytes(b"\x89PNG wheel bytes")
    (game / "medias" / "bg.png").write_bytes(b"\x89PNG backglass bytes")
    (game / "Example Game (Bally 1990).info").write_text(json.dumps({
        "Info": {"Title": "Example Game", "Manufacturer": "Bally", "Year": "1990"},
        "vpinfe": {"game_id": "exmpl00001", "schema": 2},
    }), encoding="utf-8")


class LookupTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = TemporaryDirectory()
        self.root = Path(self._tmp.name)
        _library(self.root)
        self.games = GameParser(str(self.root)).getAllGames()
        self.addCleanup(self._tmp.cleanup)

    def test_it_finds_the_file_behind_a_kind(self) -> None:
        path = media_lookup.media_path(self.games, "exmpl00001", "wheel")

        self.assertIsNotNone(path)
        self.assertEqual(path.name, "wheel.png")

    def test_an_unknown_game_or_kind_is_none_rather_than_an_error(self) -> None:
        self.assertIsNone(media_lookup.media_path(self.games, "nosuchgame", "wheel"))
        self.assertIsNone(media_lookup.media_path(self.games, "exmpl00001", "nosuchkind"))

    def test_a_kind_with_no_file_is_none(self) -> None:
        self.assertIsNone(media_lookup.media_path(self.games, "exmpl00001", "topper"))

    def test_resolved_kinds_lists_only_what_exists(self) -> None:
        kinds = media_lookup.resolved_kinds(self.games[0])

        self.assertIn("wheel", kinds)
        self.assertIn("bg", kinds)
        self.assertNotIn("topper", kinds)


class RouteTests(unittest.TestCase):
    """Served for real, because conditional GET and Range are HTTP behavior."""

    @classmethod
    def setUpClass(cls) -> None:
        cls._tmp = TemporaryDirectory()
        cls.root = Path(cls._tmp.name)
        _library(cls.root)

        # The route asks the shared repository for the library. Patched rather than
        # injected: ensure_games_loaded rebuilds its parser when the configured games
        # root does not match, which it would not here.
        cls.games = GameParser(str(cls.root)).getAllGames()
        cls._patch = mock.patch("common.games.game_repository.ensure_games_loaded",
                                return_value=cls.games)
        cls._patch.start()

        cls.server = CustomHTTPServer({"/tables/": str(cls.root)})
        cls.server.start_file_server(port=0)   # 0 = any free port; it serves on its own thread
        cls.port = cls.server.file_server.server_address[1]

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.file_server.shutdown()
        cls.server.file_server.server_close()
        cls._patch.stop()
        cls._tmp.cleanup()

    def _get(self, path, headers=None):
        request = urllib.request.Request(f"http://127.0.0.1:{self.port}{path}",
                                         headers=headers or {})
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                return response.status, dict(response.headers), response.read()
        except urllib.error.HTTPError as exc:
            with exc:                      # closing it keeps the warnings quiet
                return exc.code, dict(exc.headers), exc.read()

    def test_it_serves_the_file(self) -> None:
        status, headers, body = self._get("/media/exmpl00001/wheel")

        self.assertEqual(status, 200)
        self.assertEqual(body, b"\x89PNG wheel bytes")
        self.assertEqual(headers["Content-Type"], "image/png")

    def test_it_carries_an_etag_and_honors_it(self) -> None:
        _, headers, _ = self._get("/media/exmpl00001/wheel")
        etag = headers["ETag"]

        status, _, body = self._get("/media/exmpl00001/wheel",
                                    {"If-None-Match": etag})

        self.assertEqual(status, 304, "an unchanged file should not be sent twice")
        self.assertEqual(body, b"")

    def test_it_asks_to_be_revalidated(self) -> None:
        """Replacing art in the Manager UI has to show up without a hard refresh."""
        _, headers, _ = self._get("/media/exmpl00001/wheel")

        self.assertEqual(headers["Cache-Control"], "no-cache")

    def test_a_range_request_is_answered_partially(self) -> None:
        status, headers, body = self._get("/media/exmpl00001/wheel",
                                          {"Range": "bytes=0-3"})

        self.assertEqual(status, 206)
        self.assertEqual(body, b"\x89PNG")
        self.assertEqual(headers["Content-Range"], "bytes 0-3/16")

    def test_an_unknown_game_is_a_404(self) -> None:
        status, _, _ = self._get("/media/nosuchgame/wheel")

        self.assertEqual(status, 404)

    def test_a_kind_this_game_lacks_is_a_404(self) -> None:
        status, _, _ = self._get("/media/exmpl00001/topper")

        self.assertEqual(status, 404)

    def test_an_unrelated_media_path_still_falls_through(self) -> None:
        """The route must not swallow /media/ paths that are not its shape."""
        status, _, _ = self._get("/media/")

        self.assertEqual(status, 404, "a 404 from the static mounts, not a crash")


if __name__ == "__main__":
    unittest.main()
