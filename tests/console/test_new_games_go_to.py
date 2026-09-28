"""One choice says where new games go: a folder of game folders, or ask each time."""

from __future__ import annotations

import unittest
from typing import Any

from common import config_service
from common.i18n import t
from console import locations
from console.settings import settings_here


def _folder(location_id: str, kind: str = "root", write_to: bool = False) -> dict[str, Any]:
    return {"location_id": location_id, "name": f"{location_id}/tables",
            "path": f"/games/{location_id}", "kind": kind, "state": "ready",
            "reachable": True, "writable": True, "reason": "", "write_to": write_to,
            "shadowed": 0, "where": "local", "origin": None}


def _listing(*folders: dict[str, Any], ask: bool) -> dict[str, Any]:
    target = next((one["location_id"] for one in folders if one["write_to"]), "")
    return {"locations": list(folders), "write_to": target, "ask_where_new_games_go": ask}


class DestinationTests(unittest.TestCase):
    def test_every_folder_of_game_folders_is_offered_and_asking_too(self) -> None:
        offered, chosen = locations.destinations(_listing(
            _folder("a", write_to=True), _folder("b"), _folder("one", kind="game"),
            ask=False))

        self.assertEqual(list(offered), ["a", "b", locations.ASK])
        self.assertEqual(offered[locations.ASK], t("console.locations.ask_each_time"))
        self.assertEqual(chosen, "a")

    def test_asking_is_the_choice_when_it_is_set(self) -> None:
        found = _listing(_folder("a", write_to=True), _folder("b"), ask=True)

        self.assertEqual(locations.destinations(found)[1], locations.ASK)
        self.assertTrue(locations.asking(found))

    def test_with_one_folder_there_is_nothing_to_ask(self) -> None:
        found = _listing(_folder("a", write_to=True), _folder("one", kind="game"), ask=True)

        self.assertEqual(locations.destinations(found), ({"a": "a/tables"}, "a"))
        self.assertFalse(locations.asking(found))

    def test_while_asking_no_row_says_it_is_where_new_games_go(self) -> None:
        held = [_folder("a", write_to=True), _folder("b")]

        self.assertEqual([row["new_games"] for row in locations.rows(held, asks=True)],
                         ["", ""])
        self.assertEqual([row["new_games"] for row in locations.rows(held)],
                         [t("word.created_here"), ""])


class HomeTests(unittest.TestCase):
    def test_the_setting_names_this_page_as_its_home(self) -> None:
        described = {(option["section"], option["key"]): option
                     for block in config_service.schema()["sections"]
                     for option in block["options"]}

        self.assertEqual(described[("updates", "ask_where_new_games_go")]["home"], "locations")

    def test_settings_leaves_out_what_another_page_is_the_home_of(self) -> None:
        schema = config_service.schema()["sections"]
        kept = {option["key"] for block in settings_here(schema)
                for option in block["options"]}

        self.assertNotIn("ask_where_new_games_go", kept)
        self.assertIn("download_spreadsheet", kept)


if __name__ == "__main__":
    unittest.main()
