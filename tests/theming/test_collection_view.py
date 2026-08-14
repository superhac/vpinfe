"""What the wheel shows when a collection is chosen.

The frontend had a membership engine of its own until this. It read a collection's game
ids and nothing else, so a member naming a table, an exclusion, a limit and a stored
order were all invisible on the surface a player actually uses - while REST answered
correctly for the same collection. These are the cases that told the two apart.
"""

from __future__ import annotations

import configparser
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from common.games.collection_store import BUILTIN_ALL, CollectionStore, public_name
from frontend import game_state
from frontend.api import API
from frontend.library_resolver import LibraryResolver
from tests.support.library import TempTree


def _game(gid, title, tables, manufacturer="", default=""):
    return SimpleNamespace(
        gameDirName=title,
        fullPathGame=f"/games/{title}",
        fullPathVPXfile=f"/games/{title}/{title}.vpx",
        creation_time=0,
        pupPackExists=False, altColorExists=False, altSoundExists=False,
        meta_config={
            "Info": {"Title": title, "Manufacturer": manufacturer, "Year": "1995",
                     "Type": "SS", "Themes": []},
            "User": {"Rating": 0, "LastRun": 0, "StartCount": 0, "RunTime": 0},
            "vpinfe": {"game_id": gid, **({"default_table": default} if default else {})},
            "tables": tables,
        },
    )


def _table(tid, filename):
    return {"id": tid, "filename": filename}


def _ini() -> SimpleNamespace:
    parser = configparser.ConfigParser()
    parser.add_section("general")
    return SimpleNamespace(config=parser, save=lambda: None)


class CollectionViewTests(TempTree):
    def setUp(self) -> None:
        super().setUp()
        self.collections = CollectionStore(str(self.root / "collections.json"))
        patcher = patch("frontend.library_resolver.get_collections_manager",
                        lambda: self.collections)
        patcher.start()
        self.addCleanup(patcher.stop)

        self.mm = _game("mm", "Medieval Madness",
                        {"vpw": _table("vpw", "MM VPW.vpx"),
                         "jp": _table("jp", "MM JP.vpx")},
                        manufacturer="Williams", default="vpw")
        self.afm = _game("afm", "Attack from Mars", {"a1": _table("a1", "AFM.vpx")},
                         manufacturer="Bally")
        self.taf = _game("taf", "The Addams Family", {"t1": _table("t1", "TAF.vpx")},
                         manufacturer="Bally")
        self.games = [self.mm, self.afm, self.taf]

    def _api(self, games=None):
        api = API.__new__(API)
        api._iniConfig = _ini()
        api.library = LibraryResolver(_ini(), games=list(
            self.games if games is None else games))
        return api

    def _rows(self, api):
        return [(entry.game.meta_config["vpinfe"]["game_id"], entry.table_id)
                for entry in api.entries]

    def test_the_default_view_is_the_whole_library(self) -> None:
        """`builtin:all` is what an empty collection has always meant, and the name for
        it never leaves core."""
        api = self._api()

        self.assertEqual(api.current_collection, BUILTIN_ALL)
        self.assertEqual(public_name(api.current_collection), "")
        self.assertEqual(api.get_current_collection(), "None")
        self.assertEqual(self._rows(api),
                         [("taf", "t1"), ("afm", "a1"), ("mm", "vpw")])

    def test_a_collection_naming_two_tables_of_one_game_shows_both(self) -> None:
        """The case the wheel could not express: two rows, one game, in curated order."""
        self.collections.add_collection("Friday Night")
        self.collections.set_order("Friday Night", "manual")
        self.collections.add_member("Friday Night", "mm", table_id="vpw")
        self.collections.add_member("Friday Night", "afm")
        self.collections.add_member("Friday Night", "mm", table_id="jp")

        api = self._api()
        game_state.apply_collection(api, "Friday Night")

        self.assertEqual(self._rows(api),
                         [("mm", "vpw"), ("afm", "a1"), ("mm", "jp")])

    def test_a_curated_order_is_held_and_is_not_one_of_the_theme_sorts(self) -> None:
        """`Manual` is what the sort UI reads back, and what stops a later refresh
        sorting the curator's list alphabetically."""
        self.collections.add_collection("Friday Night", ["mm", "taf"])
        self.collections.set_order("Friday Night", "manual")

        api = self._api()
        game_state.apply_collection(api, "Friday Night")

        self.assertEqual(api.current_sort, game_state.MANUAL_SORT)
        self.assertEqual(self._rows(api), [("mm", "vpw"), ("taf", "t1")],
                         "the curator's order, not the alphabetical one")

    def test_a_limit_caps_the_wheel(self) -> None:
        self.collections.add_collection("Short", ["mm", "afm", "taf"])
        self.collections.set_limit("Short", 2)

        api = self._api()
        game_state.apply_collection(api, "Short")

        self.assertEqual(self._rows(api), [("taf", "t1"), ("afm", "a1")])

    def test_an_exclusion_is_absent_from_the_wheel(self) -> None:
        self.collections.add_filter_collection("Bally", manufacturer="Bally")
        self.collections.exclude("Bally", "taf")

        api = self._api()
        game_state.apply_collection(api, "Bally")

        self.assertEqual(self._rows(api), [("afm", "a1")])

    def test_a_filter_control_makes_a_collection_out_of_the_library(self) -> None:
        """Not a narrowing of what was on screen: Friday Night holds no Addams Family,
        and filtering to Bally from inside it shows one."""
        self.collections.add_collection("Friday Night", ["mm", "afm"])

        api = self._api()
        game_state.apply_collection(api, "Friday Night")
        game_state.apply_filters(api, manufacturer="Bally")

        self.assertEqual(api.current_collection, BUILTIN_ALL)
        self.assertEqual(self._rows(api), [("taf", "t1"), ("afm", "a1")])

    def test_games_no_build_has_parsed_yet_each_get_a_row(self) -> None:
        """A folder that has never been scanned has no game id. Keyed on that, every one
        of them would collapse into a single row - which is a fresh install's whole
        library."""
        fresh = [_game("", "Alpha", {}), _game("", "Bravo", {})]

        api = self._api(fresh)

        self.assertEqual([entry.game.gameDirName for entry in api.entries],
                         ["Alpha", "Bravo"])


if __name__ == "__main__":
    unittest.main()
