"""Which files the source dialog offers and accepts: for media, an asset, a folder kind
and a collection's image."""

from __future__ import annotations

import mimetypes
import unittest
from types import SimpleNamespace
from unittest import mock

from common import i18n
from common.games.collections_service import IMAGE_EXTENSIONS
from common.media_specs import IMAGE_FAMILY
from console import mediasource
from console.data import Library

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


class WhatIsAlreadyThere(unittest.TestCase):
    def test_the_current_file_is_named_as_the_host_tab_lists_it(self) -> None:
        context = {"library": LIBRARY, "game_id": "game", "game": {"folder": "/games/Afm"}}
        folder = mediasource._Folder(context, "alt_color", "Alt Color", _nothing,
                                     "pinmame/altcolor")
        self.assertEqual("/games/Afm/pinmame/altcolor", folder.current)

    def test_nothing_is_current_without_a_game_folder_or_a_file(self) -> None:
        self.assertEqual("", _folder("alt_color").current)
        context = {"library": LIBRARY, "game_id": "game", "game": {"folder": "/games/Afm"}}
        self.assertEqual("", mediasource._Folder(context, "alt_color", "Alt Color",
                                                 _nothing).current)


class ACollectionTakingAGameWheel(unittest.TestCase):
    def test_only_a_collection_image_offers_its_games(self) -> None:
        self.assertEqual([True, False],
                         [mediasource._Image(LIBRARY, "Favorites", "Image", _nothing).games,
                          mediasource._Folder.games])

    def test_every_image_the_library_serves_is_named_so_a_collection_can_save_it(
            self) -> None:
        for suffix in IMAGE_FAMILY:
            served = mimetypes.guess_type(f"wheel{suffix}")[0] or ""
            with self.subTest(served=served):
                named = mediasource._named_for("4 Queens", f"{served}; charset=binary")
                self.assertTrue(named.startswith("4 Queens."))
                self.assertIn(named[len("4 Queens"):], IMAGE_EXTENSIONS)


def _slot(in_view: str, saved_for: str, tables: tuple[str, ...] = (),
          own_names: tuple[str, ...] = (),
          own_files: tuple[str, ...] = ()) -> mediasource._Slot:
    """`own_names` are the tables named apart from the folder, and `own_files` those of
    them already holding a file of their own."""
    slot = mediasource._Slot({"library": LIBRARY, "game_id": "game", "game": {},
                              "lens": in_view,
                              "tables": [{"id": one, "filename": f"{one}.vpx"}
                                         for one in tables]},
                             "wheel", "Wheel", _nothing, mediasource._media(LIBRARY, "wheel"))
    slot.placements = [{"table": "", "label": "Shared", "displaces": []},
                       *({"table": one, "label": f"{one}.vpx",
                          "displaces": [f"medias/(Wheel) {one}.png"] if one in own_files
                          else []} for one in own_names)]
    slot.placed_at = {"table": saved_for, "label": f"{saved_for}.vpx"}
    return slot


class WhereItWent(unittest.TestCase):
    def test_saved_for_the_table_in_view_names_the_table(self) -> None:
        self.assertEqual("Wheel saved for Attack from Mars",
                         _slot("Attack from Mars", "Attack from Mars").said_where("Wheel saved"))

    def test_saved_for_every_table_while_one_with_its_own_is_in_view_says_so(self) -> None:
        """Its own file still covers the shared one, so nothing on screen changes."""
        self.assertEqual(
            "Wheel saved for every table in this game - not what this view is showing",
            _slot("AFM VPW", "", tables=("AFM VPW",), own_names=("AFM VPW",),
                  own_files=("AFM VPW",)).said_where("Wheel saved"))

    def test_saved_for_every_table_while_one_with_none_is_in_view_is_shown(self) -> None:
        self.assertEqual(
            "Wheel saved for every table in this game",
            _slot("AFM VPW", "", tables=("AFM VPW",), own_names=("AFM VPW",))
            .said_where("Wheel saved"))

    def test_a_table_named_as_its_folder_is_shown_a_shared_save(self) -> None:
        one = {"tables": ("Attack from Mars",)}
        several = {"tables": ("Attack from Mars", "AFM VR"), "own_names": ("AFM VR",),
                   "own_files": ("AFM VR",)}
        for game, shape in (("one table", one), ("several", several)):
            for in_view in ("Attack from Mars", ""):
                with self.subTest(game=game, in_view=in_view):
                    self.assertEqual("Wheel saved for every table in this game",
                                     _slot(in_view, "", **shape).said_where("Wheel saved"))

    def test_saved_for_a_table_not_in_view_says_so(self) -> None:
        self.assertEqual(
            "Wheel saved for AFM VR - not what this view is showing",
            _slot("", "AFM VR", tables=("Attack from Mars", "AFM VR"),
                  own_names=("AFM VR",)).said_where("Wheel saved"))

    def test_saved_for_every_table_of_several_says_so(self) -> None:
        self.assertEqual("Wheel saved for every table in this game",
                         _slot("", "", tables=("Attack from Mars", "Attack from Mars VR"))
                         .said_where("Wheel saved"))

    def test_a_translation_orders_what_and_where(self) -> None:
        self.addCleanup(i18n.set_language, i18n.language())
        i18n.set_language("xx")
        with mock.patch.dict(i18n._catalogs, {"xx": {
                "console.mediasource.saved_where": "{where}: {message}"}}):
            said = _slot("", "").said_where("Wheel saved")

        self.assertEqual("for every table in this game: Wheel saved", said)


class TheHostTab(unittest.TestCase):
    def test_it_is_named_from_what_the_page_load_read(self) -> None:
        client = mock.Mock()
        client.games.return_value = []
        client.all_media.return_value = []
        client.library_policy.return_value = {}
        client.discovery.return_value = {"display_name": "Garage"}
        library = Library(client)
        library.load()

        named = mediasource._host_name(library)

        self.assertEqual((named, client.discovery.call_count), ("Garage", 1))


if __name__ == "__main__":
    unittest.main()
