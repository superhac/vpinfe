"""Community: the lists extensions declare, drawn by core."""

from __future__ import annotations

import unittest

from common import install_identity
from console import community, page

DECLARED = {"key": "tables", "title": "Site", "base": "/community/tables",
            "columns": [{"field": "name", "header": "Table", "kind": "text"},
                        {"field": "plays", "header": "Plays", "kind": "number"},
                        {"field": "last", "header": "Last", "kind": "date"},
                        {"field": "vps_id", "header": "VPS", "kind": "text"}],
            "views": [{"name": "Most played", "columns": ["name", "plays"],
                       "sort": [{"field": "plays", "desc": True}], "help": ""}],
            "relation": {"field": "vps_id", "keys": "vps_entry"}}
LOADED = {"name": "site", "state": "loaded", "community": [DECLARED]}


class TheNav(unittest.TestCase):
    def test_a_running_extension_s_list_sits_under_community(self) -> None:
        items = community.nav_items([LOADED, {**LOADED, "name": "off", "state": "failed"}],
                                    install_identity.CORE)
        groups = dict(page.nav_for(None, items))

        self.assertEqual(["community:site:tables"],
                         [one[0] for one in groups[page.NAV_COMMUNITY]])

    def test_community_sits_between_frontend_and_system(self) -> None:
        parents = [parent for parent, _items in page.NAV_GROUPS]

        self.assertEqual([page.NAV_FRONTEND, page.NAV_COMMUNITY, page.NAV_SYSTEM],
                         parents[-3:])

    def test_with_no_list_there_is_no_community(self) -> None:
        self.assertNotIn(page.NAV_COMMUNITY, dict(page.nav_for(None)))

    def test_a_view_finds_its_list(self) -> None:
        self.assertEqual((LOADED, DECLARED),
                         community.find("community:site:tables", [LOADED]))


class TheGrid(unittest.TestCase):
    def test_the_first_column_is_scanned_by_and_in_library_follows(self) -> None:
        shown = community.columns(DECLARED)

        self.assertEqual(["name", "plays", "last", "vps_id", community.HELD],
                         [one["field"] for one in shown])
        self.assertIn("console-cell-identifier", shown[0]["cellClass"])
        self.assertEqual("numericColumn", shown[1]["type"])

    def test_a_view_keeps_its_sort_and_yours_keeps_only_what_is_held(self) -> None:
        presets = community.presets(DECLARED)

        self.assertEqual(({"colId": "plays", "sort": "desc", "sortIndex": 0},),
                         presets["Most played"].sort)
        self.assertEqual({community.HELD: {"values": [True]}},
                         presets["In Your Library"].filters)

    def test_a_row_says_whether_it_is_held_and_by_which_game(self) -> None:
        rows = community.rows([{"name": "AFM", "vps_id": "vps-afm", "last": ""},
                               {"name": "TAF", "vps_id": "vps-taf", "last": ""}], DECLARED,
                              {"vps-afm": {"game_id": "afm", "name": "Attack from Mars"}})

        self.assertEqual([(True, "afm"), (False, "")],
                         [(one[community.HELD], one["held_game"]) for one in rows])
        self.assertIn("last_ago", rows[0])


if __name__ == "__main__":
    unittest.main()
