"""The address the Console draws a picture from: the file, its size and its version."""

from __future__ import annotations

import unittest

from console import art, list_art
from console.data import _thumb


class ArtAddressTests(unittest.TestCase):
    def test_a_picture_asks_for_its_size_under_its_version(self) -> None:
        self.assertEqual(art.media("G1", "wheel", version="abc", size=art.CELL),
                         "/api/v1/games/G1/media/wheel?size=256&v=abc")

    def test_a_video_is_never_asked_for_a_size(self) -> None:
        self.assertEqual(art.media("G1", "playfield_video", version="abc", size=art.CELL),
                         "/api/v1/games/G1/media/playfield_video?v=abc")

    def test_nothing_known_about_it_is_the_plain_address(self) -> None:
        self.assertEqual(art.media("G1", "wheel"), "/api/v1/games/G1/media/wheel")

    def test_a_table_s_file_is_its_own_address(self) -> None:
        self.assertEqual(art.media("G1", "wheel", "tbl 1", size=art.PANEL),
                         "/api/v1/games/G1/tables/tbl%201/media/wheel?size=1024")

    def test_a_collection_name_is_one_path_segment(self) -> None:
        self.assertEqual(art.collection("AC/DC & more", version="v1"),
                         "/api/v1/collections/AC%2FDC%20%26%20more/image?v=v1")

    def test_an_address_the_api_gave_keeps_its_own_query(self) -> None:
        self.assertEqual(art.sized("/api/v1/games/G1/media/wheel", art.CELL),
                         "/api/v1/games/G1/media/wheel?size=256")
        self.assertEqual(art.sized("/x?v=1", art.CELL), "/x?v=1&size=256")


class DrawnArtTests(unittest.TestCase):
    def test_a_grid_cell_draws_the_small_copy(self) -> None:
        cell = _thumb("G1", "backglass", {"present": True, "version": "abc"})

        self.assertIn('src="/api/v1/games/G1/media/backglass?size=256&v=abc"', cell)

    def test_a_grid_cell_video_is_the_file_itself(self) -> None:
        cell = _thumb("G1", "backglass_video", {"present": True, "version": "abc"})

        self.assertIn('src="/api/v1/games/G1/media/backglass_video?v=abc#t=0.1"', cell)

    def test_a_collection_s_picture_draws_the_small_copy(self) -> None:
        self.assertEqual(
            list_art.collection({"name": "Bally", "image": "b.png", "image_version": "abc"}),
            "/api/v1/collections/Bally/image?size=256&v=abc")

    def test_a_collection_with_no_picture_asks_for_none(self) -> None:
        self.assertEqual(list_art.collection({"name": "Bally", "image_version": "abc"}), "")


if __name__ == "__main__":
    unittest.main()
