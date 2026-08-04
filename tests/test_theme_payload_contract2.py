"""The theme payload at both contracts.

Contract 1 is what twelve published themes read and the parity gate holds against
master. Contract 2 is the shape the API serves, so a theme and a REST client describe
a game the same way.
"""

import json
import unittest
from types import SimpleNamespace

from common.games.collection_resolver import entries_for, visible_entries
from frontend.game_state import games_json


def _game(title="Medieval Madness", tables=None, vpx="/g/MM/MM.vpx"):
    return SimpleNamespace(
        gameDirName=title, fullPathGame="/g/MM", fullPathVPXfile=vpx,
        pupPackExists=True, altColorExists=False, altSoundExists=False,
        creation_time=0,
        metaConfig={
            "Info": {"Title": title, "Manufacturer": "Williams", "Year": "1997",
                     "Type": "SS", "VPSId": "vps-mm", "Themes": ["Fantasy"]},
            "User": {"Rating": 5},
            # An explicit default, so which table collapses is stated rather than
            # falling out of filename order.
            "vpinfe": {"game_id": "mm00000001", "default_table": "t1"},
            **({"tables": tables} if tables is not None else {}),
        },
    )


TWO_TABLES = {
    "t1": {"id": "t1", "filename": "MM VPW.vpx", "version": "1.2", "rom": "mm_109c",
           "authors": ["VPW"], "detect_ssf": True},
    "t2": {"id": "t2", "filename": "MM JP.vpx", "version": "1.0", "rom": "mm_109c"},
}


class ContractOneTests(unittest.TestCase):
    """Unchanged, and it has to stay that way - see tests/test_parity.py."""

    def test_it_is_a_bare_array_of_rows(self) -> None:
        payload = json.loads(games_json(entries_for([_game(tables=TWO_TABLES)]),
                                        contract=1))

        self.assertIsInstance(payload, list)
        self.assertEqual(len(payload), 1, "one row per game, collapsed")
        # The contract 1 spellings, which is the whole point of the projection.
        self.assertIn("tableDirName", payload[0])
        self.assertIn("fullPathTable", payload[0])
        self.assertIn("VPXFile", payload[0]["meta"])
        self.assertNotIn("tables", payload[0]["meta"], "contract 1 never sees these")

    def test_a_game_with_several_tables_is_still_one_row(self) -> None:
        """Contract 1 predates a game offering more than one table."""
        payload = json.loads(games_json(entries_for([_game(tables=TWO_TABLES)]),
                                        contract=1))

        self.assertEqual(len(payload), 1)


class ContractTwoTests(unittest.TestCase):
    def _payload(self, games, **kwargs):
        return json.loads(games_json(entries_for(games, **kwargs), contract=2,
                                     collection="Friday Night",
                                     expanded=kwargs.get("expanded", False)))

    def test_it_says_which_collection_and_which_lens(self) -> None:
        body = self._payload([_game(tables=TWO_TABLES)])

        self.assertEqual(body["collection"], "Friday Night")
        self.assertFalse(body["expanded"])
        self.assertEqual(body["count"], len(body["entries"]))

    def test_an_entry_names_its_game_and_its_table(self) -> None:
        entry = self._payload([_game(tables=TWO_TABLES)])["entries"][0]

        self.assertEqual(entry["game"]["id"], "mm00000001")
        self.assertEqual(entry["game"]["name"], "Medieval Madness")
        self.assertEqual(entry["table"]["id"], "t1")
        self.assertEqual(entry["table"]["version"], "1.2")
        self.assertEqual(entry["siblings"], 2, "so a theme can offer a switcher")

    def test_detect_flags_lose_their_prefix(self) -> None:
        """`detects.ssf`, not `detect_ssf` - the prefix was storage, not vocabulary."""
        entry = self._payload([_game(tables=TWO_TABLES)])["entries"][0]

        self.assertTrue(entry["table"]["detects"]["ssf"])
        self.assertFalse(entry["table"]["detects"]["fleep"])

    def test_expanded_gives_one_entry_per_table(self) -> None:
        collapsed = self._payload([_game(tables=TWO_TABLES)])
        expanded = self._payload([_game(tables=TWO_TABLES)], expanded=True)

        self.assertEqual(collapsed["count"], 1)
        self.assertEqual(expanded["count"], 2)
        self.assertEqual([e["table"]["id"] for e in expanded["entries"]], ["t1", "t2"],
                         "the default first, then the rest by filename")

    def test_media_rides_on_the_entry(self) -> None:
        entry = self._payload([_game(tables=TWO_TABLES)])["entries"][0]

        self.assertIn("media", entry)
        self.assertIn("ManufacturerLogoPath", entry["media"])


class UnparsedGameTests(unittest.TestCase):
    """A folder no metadata build has touched still has to appear and launch."""

    def test_it_gets_an_entry_from_the_scan(self) -> None:
        offered = visible_entries(_game(tables=None))

        self.assertEqual(len(offered), 1)
        self.assertEqual(offered[0]["filename"], "MM.vpx")
        self.assertEqual(offered[0]["id"], "", "the id arrives with the parse")

    def test_a_game_with_no_vpx_at_all_offers_nothing(self) -> None:
        """Nothing to launch, so nothing in the play lens - by design."""
        self.assertEqual(visible_entries(_game(tables={}, vpx="")), [])


if __name__ == "__main__":
    unittest.main()
