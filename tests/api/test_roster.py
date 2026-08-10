"""The players a hub knows about.

Keyed by `install_id` because it is the only thing about a player that does not change:
a display name is meant to be renamed and an address moves with DHCP. A roster that
keyed on either would lose track of a player the first time somebody used the feature.

One entry is the degenerate case of many, so nothing here treats a single player
specially - building it single-entry-only would have taken deliberate effort.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from common.roster import Player, Roster


class RosterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.roster = Roster(Path(self.tmp.name) / "players.json")

    def test_a_hub_that_has_seen_nobody_has_an_empty_roster(self) -> None:
        self.assertEqual(self.roster.players(), [])
        self.assertIsNone(self.roster.get("anything"))
        self.assertFalse(self.roster.knows("anything"))

    def test_recording_a_player_makes_it_known(self) -> None:
        self.roster.record("Aaaa111111", display_name="basement cab",
                           roles=("hub", "player"))

        player = self.roster.get("Aaaa111111")
        self.assertEqual(player.display_name, "basement cab")
        self.assertEqual(player.roles, ("hub", "player"))
        self.assertTrue(self.roster.knows("Aaaa111111"))

    def test_a_player_heard_from_twice_is_still_one_player(self) -> None:
        """The whole point of keying on the id: a reconnect is not a second player."""
        self.roster.record("Aaaa111111", display_name="cab")
        self.roster.record("Aaaa111111", display_name="cab")

        self.assertEqual(len(self.roster.players()), 1)

    def test_a_rename_does_not_lose_the_player(self) -> None:
        """`display_name` addresses nothing, which is what makes renaming safe."""
        first = self.roster.record("Aaaa111111", display_name="old name")
        self.roster.record("Aaaa111111", display_name="new name")

        players = self.roster.players()
        self.assertEqual(len(players), 1)
        self.assertEqual(players[0].display_name, "new name")
        self.assertEqual(players[0].first_seen, first.first_seen,
                         "it is the same player, so it was first seen when it was")

    def test_what_the_install_owns_is_refreshed_and_what_we_own_is_not(self) -> None:
        """Name, roles and address are a cached copy of what that install last said.
        `first_seen` is ours, and is the one thing a later record must not move.

        The expected timestamp is pinned rather than read back from the first record:
        comparing two values the same code produced moves them together, so a
        `first_seen` that silently resets on every record would still look equal.
        """
        pinned = "2020-01-01T00:00:00Z"
        self.roster.record("Aaaa111111", display_name="a", roles=("player",),
                           address="192.168.1.10")
        self._rewrite_first_seen("Aaaa111111", pinned)

        later = self.roster.record("Aaaa111111", display_name="b", roles=("hub",),
                                   address="192.168.1.99")

        self.assertEqual((later.display_name, later.roles, later.address),
                         ("b", ("hub",), "192.168.1.99"))
        self.assertEqual(later.first_seen, pinned, "a re-record must not move it")
        self.assertNotEqual(later.last_seen, pinned, "but last_seen is now")

    def _rewrite_first_seen(self, install_id: str, when: str) -> None:
        """Put a known timestamp on disk, so the assertion has an outside witness."""
        payload = json.loads(self.roster.path.read_text())
        for entry in payload["players"]:
            if entry["install_id"] == install_id:
                entry["first_seen"] = when
        self.roster.path.write_text(json.dumps(payload), encoding="utf-8")

    def test_a_roster_holds_more_than_one(self) -> None:
        self.roster.record("Aaaa111111", display_name="cab")
        self.roster.record("Bbbb222222", display_name="desktop")

        self.assertEqual([p.install_id for p in self.roster.players()],
                         ["Aaaa111111", "Bbbb222222"])

    def test_a_player_with_no_id_is_refused(self) -> None:
        """An id is the entry's identity; without one there is nothing to key on."""
        self.assertIsNone(self.roster.record(""))
        self.assertIsNone(self.roster.record("   "))
        self.assertEqual(self.roster.players(), [])

    def test_forgetting_a_player_says_whether_there_was_one(self) -> None:
        self.roster.record("Aaaa111111")

        self.assertTrue(self.roster.forget("Aaaa111111"))
        self.assertFalse(self.roster.forget("Aaaa111111"))
        self.assertEqual(self.roster.players(), [])


class RosterStorageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "players.json"

    def test_it_survives_being_reopened(self) -> None:
        Roster(self.path).record("Aaaa111111", display_name="cab")

        self.assertEqual(Roster(self.path).get("Aaaa111111").display_name, "cab")

    def test_the_file_carries_its_own_schema(self) -> None:
        Roster(self.path).record("Aaaa111111")

        self.assertEqual(json.loads(self.path.read_text())["schema"], 1)

    def test_an_unreadable_roster_is_empty_rather_than_fatal(self) -> None:
        """A hub with a corrupt roster should still start. It has lost who it knew,
        which is recoverable; refusing to run is not."""
        self.path.write_text("{ not json", encoding="utf-8")

        self.assertEqual(Roster(self.path).players(), [])

    def test_a_field_a_newer_build_wrote_is_not_dropped(self) -> None:
        """A downgrade must not silently strip what it does not understand."""
        self.path.write_text(json.dumps({
            "schema": 99,
            "players": [{"install_id": "Aaaa111111", "something_new": "keep me"}],
        }), encoding="utf-8")

        roster = Roster(self.path)
        roster.record("Aaaa111111", display_name="cab")

        self.assertEqual(json.loads(self.path.read_text())["players"][0]["something_new"],
                         "keep me")

    def test_an_entry_with_no_id_is_skipped_rather_than_crashing(self) -> None:
        self.path.write_text(json.dumps({
            "schema": 1,
            "players": [{"display_name": "nameless"}, {"install_id": "Aaaa111111"}],
        }), encoding="utf-8")

        self.assertEqual([p.install_id for p in Roster(self.path).players()],
                         ["Aaaa111111"])


class PlayerTests(unittest.TestCase):
    def test_a_player_round_trips_through_its_dict(self) -> None:
        player = Player(install_id="Aaaa111111", display_name="cab",
                        roles=("hub", "player"), address="192.168.1.10",
                        first_seen="2026-01-01T00:00:00Z", last_seen="2026-01-02T00:00:00Z")

        self.assertEqual(Player.from_dict(player.as_dict()), player)


if __name__ == "__main__":
    unittest.main()
