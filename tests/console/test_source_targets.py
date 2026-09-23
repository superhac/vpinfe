"""Which files the source dialog offers and accepts: for media, an asset, a folder kind
and a collection's image."""

from __future__ import annotations

import unittest
from types import SimpleNamespace

from common.games.collections_service import IMAGE_EXTENSIONS
from common.media_specs import IMAGE_FAMILY
from console import mediasource

LIBRARY = SimpleNamespace(placements=None, displaced_by=None, place_media=None,
                          import_media=None, asset_placements=None,
                          asset_displaced_by=None, place_asset=None, import_asset=None)


async def _nothing() -> None:
    return None


def _folder(kind: str) -> mediasource._Folder:
    return mediasource._Folder({"library": LIBRARY, "game_id": "game", "game": {}},
                               kind, kind, _nothing)


class WhatFits(unittest.TestCase):
    def test_an_asset_takes_a_file_with_its_own_extension_in_any_case(self) -> None:
        target = mediasource._asset(LIBRARY, "pov")
        self.assertEqual([True, True, False],
                         [target.fits({"name": name}) for name in
                          ("view.pov", "VIEW.POV", "view.png")])
        self.assertFalse(target.online)

    def test_media_takes_a_file_of_its_family(self) -> None:
        target = mediasource._media(LIBRARY, "wheel")
        self.assertEqual([True, False], [target.fits({"family": "image"}),
                                         target.fits({"family": "video"})])
        self.assertTrue(target.online)

    def test_a_folder_kind_takes_an_archive_or_a_file_of_any_kind_under_it(self) -> None:
        self.assertEqual([True, True, True, False],
                         [_folder("alt_color").fits({"name": name}) for name in
                          ("afm.cRZ", "afm.pal", "afm colors.ZIP", "afm.png")])

    def test_a_kind_known_only_by_its_folder_takes_only_an_archive(self) -> None:
        self.assertEqual([True, False],
                         [_folder("pup_pack").fits({"name": name}) for name in
                          ("afm pup.7z", "screen.mp4")])

    def test_a_collection_image_takes_an_image(self) -> None:
        image = mediasource._Image(LIBRARY, "Favorites", "Image", _nothing)
        self.assertEqual([True, False], [image.fits({"family": "image"}),
                                         image.fits({"family": "video"})])


class WhatThePickerOffers(unittest.TestCase):
    def test_an_asset_offers_its_own_extensions(self) -> None:
        self.assertEqual((".pov",), mediasource._asset(LIBRARY, "pov").accept)

    def test_media_offers_its_family(self) -> None:
        self.assertEqual(IMAGE_FAMILY, mediasource._media(LIBRARY, "wheel").accept)
        self.assertEqual((".mp4",), mediasource._media(LIBRARY, "playfield_video").accept)

    def test_a_collection_image_offers_what_a_collection_can_save(self) -> None:
        image = mediasource._Image(LIBRARY, "Favorites", "Image", _nothing)
        self.assertEqual(IMAGE_EXTENSIONS, set(image.accept))


if __name__ == "__main__":
    unittest.main()
