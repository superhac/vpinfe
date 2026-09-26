"""The picture beside a game or table's name in the Games, Tables, Media and Assets grids.

A real library on disk, read over the API the way the Console reads it, and each grid
drawn in-process from what that read gave.
"""

from __future__ import annotations

import asyncio
import io
import os
import unittest
from collections.abc import Callable
from typing import Any
from unittest import mock

from nicegui import core, ui
from PIL import Image
from starlette.testclient import TestClient

import httpapi
from common import icons
from common.games import game_repository
from common.games.locations import KIND_ROOT, Location
from common.paths import get_ini_config
from console import assets, games, grid, media, page, themes
from console.api import ApiClient
from console.data import Library
from tests.support.library import TempTree, game_info, write_game

TWO = "Two Tables (Maker 2001)"
PLAIN = "Plain Wheel (Maker 2002)"
BARE = "No Art (Maker 2003)"
TWO_ID, PLAIN_ID, BARE_ID = "gameTwo001", "gamePlain1", "gameBare01"
RED, BLUE, GREEN, WHITE = (200, 0, 0), (0, 0, 200), (0, 160, 0), (255, 255, 255)
GRIDS = ("games", "tables", "media", "assets")
# The 80px frame and the 12px gap after it.
ROOM_PX = 92


def _png(color: tuple[int, int, int]) -> bytes:
    held = io.BytesIO()
    Image.new("RGB", (40, 20), color).save(held, "PNG")
    return held.getvalue()


def _tables(**ids: str) -> dict:
    return {table_id: {"id": table_id, "filename": filename}
            for table_id, filename in ids.items()}


def _answered(*_args: Any, **_kwargs: Any) -> asyncio.Future:
    """What the grid says back, with no browser to say it: nothing hidden, no filter."""
    said = asyncio.get_running_loop().create_future()
    said.set_result([])
    return said


class _OverTheApi(ApiClient):
    """The Console's own client, answered by the API in-process. Keeps each path it
    reads, and apart from those, each one read on an event loop."""

    def __init__(self, api: TestClient) -> None:
        super().__init__("http://testserver")
        self._api = api
        self.read: list[str] = []
        self.on_loop: list[str] = []

    def _get(self, path: str) -> dict:
        self.read.append(path)
        try:
            asyncio.get_running_loop()
            self.on_loop.append(path)
        except RuntimeError:
            pass
        answer = self._api.get(path or "/")
        answer.raise_for_status()
        return answer.json()


class _Drawn(TempTree):
    def setUp(self) -> None:
        super().setUp()
        write_game(self.root, TWO, vpx=False,
                   info=game_info("Two", game_id=TWO_ID,
                                  tables=_tables(tblDesktop=f"{TWO}.vpx",
                                                 tblVRbuild=f"{TWO} - VR.vpx"),
                                  vpinfe={"default_table": "tblVRbuild"}),
                   files={f"{TWO}.vpx": b"vpx", f"{TWO} - VR.vpx": b"vpx"},
                   medias={"wheel.png": _png(RED), f"(Wheel) {TWO} - VR.png": _png(BLUE)})
        write_game(self.root, PLAIN,
                   info=game_info("Plain", game_id=PLAIN_ID,
                                  tables=_tables(tblPlain01=f"{PLAIN}.vpx")),
                   medias={"wheel.png": _png(GREEN)})
        write_game(self.root, BARE,
                   info=game_info("Bare", game_id=BARE_ID,
                                  tables=_tables(tblBare001=f"{BARE}.vpx")))

        previous = dict(game_repository._PARSERS)
        game_repository._PARSERS.clear()
        self.addCleanup(game_repository._PARSERS.update, previous)
        self.addCleanup(game_repository._PARSERS.clear)
        for patcher in (
                mock.patch.object(game_repository.locations, "configured",
                                  return_value=[Location(location_id="test",
                                                         path=str(self.root),
                                                         kind=KIND_ROOT)]),
                mock.patch.object(ui, "run_javascript"),
                mock.patch.object(ui, "notify"),
                mock.patch.object(ui.aggrid, "run_grid_method", side_effect=_answered)):
            patcher.start()
            self.addCleanup(patcher.stop)

        self.http = TestClient(httpapi.create_api_app())
        self.client = _OverTheApi(self.http)

    def _list_art(self, value: str) -> None:
        self._write_list_art(value)
        self.addCleanup(self._write_list_art, "")

    @staticmethod
    def _write_list_art(value: str) -> None:
        store = get_ini_config()
        store.set_value("console", "list_art", value)
        store.save()

    def _hide_media_kinds(self, *kinds: str) -> None:
        self.http.put("/library/policy", json={"hidden_media_kinds": list(kinds)}) \
            .raise_for_status()
        self.addCleanup(self.http.put, "/library/policy", json={"hidden_media_kinds": []})

    def _library(self, view: str) -> Library:
        """Read as a page reads before it draws `view`."""
        library = Library(self.client)
        library.load()
        self._read_before_drawing(view, library)
        return library

    @staticmethod
    def _read_before_drawing(view: str, library: Library) -> None:
        reads = page.reads_before_drawing(view, library)
        if reads is not None:
            reads()

    def _grid(self, view: str, library: Library) -> ui.aggrid:
        draws: dict[str, Callable[[], Any]] = {
            "games": lambda: games.build(library.game_rows(), library.kinds_present(),
                                         library, lambda _row: None, {"view": "games"}),
            "tables": lambda: games.build_tables(library.table_rows(), library,
                                                 lambda _row: None, {"view": "tables"}),
            "media": lambda: media.build(library.media_rows(), library,
                                         lambda _row: None, {"view": "media"}),
            "assets": lambda: assets.build(library.asset_rows(), library,
                                           lambda _row: None, {"view": "assets"}),
        }
        holder = ui.card()

        async def inside() -> None:
            was = core.loop
            core.loop = asyncio.get_running_loop()
            try:
                with holder:
                    draws[view]()
            finally:
                core.loop = was

        asyncio.run(inside())
        return next(one for one in holder.descendants() if isinstance(one, ui.aggrid))

    def _drawn(self, view: str) -> ui.aggrid:
        return self._grid(view, self._library(view))

    @staticmethod
    def _name_column(table: ui.aggrid) -> dict[str, Any]:
        return next(one for one in table.options["columnDefs"]
                    if grid.IDENTIFIER_CLASS in str(one.get("cellClass") or ""))

    @staticmethod
    def _rows(table: ui.aggrid, key: str = "id") -> dict[str, dict[str, Any]]:
        return {str(row[key]): row for row in table.options["rowData"]}

    def _color(self, address: str) -> tuple[int, ...]:
        """Which of the four colors the picture `address` serves is. The nearest, since
        the cell-size copy is re-encoded lossily."""
        answer = self.http.get(address.removeprefix("/api/v1"))
        self.assertEqual(answer.status_code, 200, address)
        with Image.open(io.BytesIO(answer.content)) as image:
            seen = image.convert("RGB").getpixel((0, 0))
        assert isinstance(seen, tuple)
        return min((RED, BLUE, GREEN, WHITE),
                   key=lambda named: sum(abs(int(a) - int(b))
                                         for a, b in zip(named, seen, strict=True)))


class ArtBesideTheName(_Drawn):
    def test_every_grid_keeps_its_56px_rows(self) -> None:
        for view in GRIDS:
            with self.subTest(grid=view):
                table = self._drawn(view)
                self.assertEqual(table.options["rowHeight"], 56)
                self.assertIn("console-grid-two-line", table.classes)

    def test_the_name_column_grows_by_the_frame_and_its_gap(self) -> None:
        on = {view: self._name_column(self._drawn(view))["width"] for view in GRIDS}
        self._list_art("none")
        off = {view: self._name_column(self._drawn(view))["width"] for view in GRIDS}

        self.assertEqual({view: on[view] - off[view] for view in GRIDS},
                         dict.fromkeys(GRIDS, ROOM_PX))

    def test_a_width_somebody_set_stays_theirs(self) -> None:
        columns = self._drawn("games").options["columnDefs"]

        state = grid.applied_state(columns, grid.Layout("games", widths={"name": 333}))

        self.assertEqual(next(one["width"] for one in state if one["colId"] == "name"), 333)

    def test_a_game_shows_its_default_table_s_art(self) -> None:
        rows = self._rows(self._drawn("games"))

        self.assertEqual(self._color(rows[TWO_ID]["art"]), BLUE)
        self.assertEqual(self._color(rows[PLAIN_ID]["art"]), GREEN)

    def test_a_table_shows_its_own(self) -> None:
        rows = self._rows(self._drawn("tables"))

        self.assertEqual(self._color(rows["tblDesktop"]["art"]), RED)
        self.assertEqual(self._color(rows["tblVRbuild"]["art"]), BLUE)

    def test_a_media_or_asset_row_shows_its_game_s(self) -> None:
        shown = {game_id: row["art"] for game_id, row in self._rows(self._drawn("games")).items()}
        for view in ("media", "assets"):
            with self.subTest(grid=view):
                rows = self._drawn(view).options["rowData"]
                self.assertTrue(rows)
                self.assertEqual({(row["game_id"], row["art"]) for row in rows},
                                 {(row["game_id"], shown[row["game_id"]]) for row in rows})

    def test_a_row_with_no_art_asks_for_none_and_its_grid_draws_the_glyph(self) -> None:
        glyphs = {"games": icons.GAMES, "tables": icons.TABLES,
                  "media": icons.GAMES, "assets": icons.GAMES}
        for view, glyph in glyphs.items():
            with self.subTest(grid=view):
                table = self._drawn(view)
                bare = [row for row in table.options["rowData"]
                        if row.get("game_id", row["id"]) == BARE_ID]
                self.assertTrue(bare)
                self.assertEqual({row["art"] for row in bare}, {""})
                self.assertIn(glyph, self._name_column(table)[":cellRenderer"])

    def test_none_draws_no_frame(self) -> None:
        self._list_art("none")
        for view in GRIDS:
            with self.subTest(grid=view):
                rows = self._drawn(view).options["rowData"]
                self.assertEqual([row for row in rows if "art" in row], [])
        self.assertEqual([path for path in self.client.read if "art=" in path], [])

    def test_a_kind_media_kinds_switches_off_draws_no_frame(self) -> None:
        self._hide_media_kinds("wheel")

        rows = self._drawn("games").options["rowData"]

        self.assertEqual([row for row in rows if "art" in row], [])


class TheArtIsReadBeforeTheDraw(_Drawn):
    def test_the_games_grid_reads_the_listing_off_the_loop(self) -> None:
        self._drawn("games")

        self.assertIn("/tables?art=wheel", self.client.read)
        self.assertEqual(self.client.on_loop, [])

    def test_a_kind_chosen_since_is_read_before_the_next_draw(self) -> None:
        library = self._library("games")
        self._list_art("backglass")

        self._read_before_drawing("games", library)

        self.assertIn("/tables?art=backglass", self.client.read)

    def test_a_media_write_reads_that_game_s_art_again_and_no_other(self) -> None:
        library = self._library("games")
        wheel = self.root / PLAIN / "medias" / "wheel.png"
        held = wheel.stat()
        wheel.write_bytes(_png(WHITE))
        os.utime(wheel, ns=(held.st_atime_ns, held.st_mtime_ns + 10**9))
        library.forget_media(PLAIN_ID)
        before = len(self.client.read)

        self._read_before_drawing("games", library)

        self.assertIn(f"/tables?art=wheel&game={PLAIN_ID}", self.client.read[before:])
        self.assertNotIn("/tables?art=wheel", self.client.read[before:])
        rows = self._rows(self._grid("games", library))
        self.assertEqual(self._color(rows[PLAIN_ID]["art"]), WHITE)


class ThemesKeepTheirPreview(unittest.TestCase):
    def test_at_88px_with_the_palette_where_a_theme_has_none(self) -> None:
        renderer = next(one for one in themes.COLUMNS
                        if grid.IDENTIFIER_CLASS in one["cellClass"])[":cellRenderer"]

        self.assertEqual(grid.base_row_px(themes.COLUMNS), 88)
        self.assertIn("palette", renderer)
        self.assertNotIn("image_not_supported", renderer)


if __name__ == "__main__":
    unittest.main()
