"""Which files on this machine the source dialog offers, for media and for an asset."""

from __future__ import annotations

import unittest
from types import SimpleNamespace

from console import mediasource

LIBRARY = SimpleNamespace(placements=None, displaced_by=None, place_media=None,
                          import_media=None, asset_placements=None,
                          asset_displaced_by=None, place_asset=None, import_asset=None)


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


if __name__ == "__main__":
    unittest.main()
