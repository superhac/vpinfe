"""Who plays on an install, and who the next game counts for.

Each test builds a fresh roster on a temporary file. A new `Roster` on the same path is
what a restart looks like: the kept players come back, the guests and who is up do not.
"""

from __future__ import annotations

import json
import unittest
from configparser import ConfigParser
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from common import events, service_errors
from common.extensions import store as extension_store
from common.players import OWNER_MIGRATION, Roster, same_initials


def _config(initials: str | None = None) -> ConfigParser:
    parser = ConfigParser()
    parser.add_section("vpinplay")
    if initials is not None:
        parser.set("vpinplay", "initials", initials)
    return parser


SCHEMA_1_FILE = {
    "schema": 1,
    "players": [{"install_id": "Aaaa111111", "display_name": "basement cab",
                 "roles": ["player"], "address": "testclient",
                 "first_seen": "2026-08-12T02:18:46Z", "last_seen": "2026-08-12T02:18:46Z"}],
}


class _RosterCase(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "players.json"
        self.roster = Roster(self.path)

    def _file(self) -> dict:
        return json.loads(self.path.read_text(encoding="utf-8"))

    def _restart(self) -> Roster:
        self.roster = Roster(self.path)
        return self.roster


class SameInitialsTests(unittest.TestCase):
    def test_case_and_padding_do_not_matter(self) -> None:
        self.assertTrue(same_initials("OWN", "own"))
        self.assertTrue(same_initials(" own ", "OWN"))
        self.assertTrue(same_initials("Jd", "jD "))

    def test_different_initials_differ(self) -> None:
        self.assertFalse(same_initials("OWN", "OWM"))
        self.assertFalse(same_initials("OW", "OWW"))

    def test_blank_matches_nothing_not_even_blank(self) -> None:
        self.assertFalse(same_initials("", ""))
        self.assertFalse(same_initials("  ", None))
        self.assertFalse(same_initials("", "OWN"))

    def test_the_duplicate_check_and_attribution_agree_on_case(self) -> None:
        with TemporaryDirectory() as folder:
            roster = Roster(Path(folder) / "players.json")
            roster.add_player("Jordan", "OWN")

            with self.assertRaises(service_errors.RefusedError):
                roster.add_player("Other", "own")
            self.assertEqual(roster.whose(" own").name, "Jordan")


class FileTests(_RosterCase):
    def test_no_file_is_an_empty_roster(self) -> None:
        self.assertEqual(self.roster.players(), [])
        self.assertEqual(self.roster.up(), [])
        self.assertIsNone(self.roster.owner())

    def test_a_schema_1_file_is_not_ours_and_the_first_write_replaces_it(self) -> None:
        self.path.write_text(json.dumps(SCHEMA_1_FILE), encoding="utf-8")

        self.assertEqual(self.roster.players(), [], "an install is not a player")

        owner = self.roster.ensure_owner(_config("OWN"))

        stored = self._file()
        self.assertEqual(stored["schema"], 2)
        self.assertEqual(stored["players"], [
            {"id": owner.player_id, "name": "", "initials": "OWN", "owner": True}])
        self.assertNotIn("install_id", json.dumps(stored))

    def test_a_file_with_no_schema_is_not_ours(self) -> None:
        self.path.write_text(json.dumps({"players": [{"id": "Pppp111111", "owner": True}]}),
                             encoding="utf-8")

        self.assertEqual(self.roster.players(), [])

    def test_an_unreadable_file_is_an_empty_roster(self) -> None:
        self.path.write_text("{not json", encoding="utf-8")

        with self.assertLogs("vpinfe.common.players", "WARNING"):
            self.assertEqual(self.roster.players(), [])

    def test_kept_players_come_back_after_a_restart(self) -> None:
        self.roster.ensure_owner(_config("OWN"))
        added = self.roster.add_player("Alex", "abc")

        again = self._restart()

        self.assertEqual([(p.name, p.initials, p.owner) for p in again.players()],
                         [("", "OWN", True), ("Alex", "ABC", False)])
        self.assertEqual(again.get(added.player_id), added)

    def test_what_a_newer_build_wrote_is_carried_through(self) -> None:
        self.path.write_text(json.dumps({
            "schema": 3, "migrations": [OWNER_MIGRATION], "later": {"kept": True},
            "players": [{"id": "Pppp111111", "name": "Jordan", "initials": "OWN",
                         "owner": True, "share": {"vpinplay": False}}]}), encoding="utf-8")

        self.roster.add_player("Alex", "ABC")

        stored = self._file()
        self.assertEqual(stored["schema"], 3, "never stamped down")
        self.assertEqual(stored["later"], {"kept": True})
        self.assertEqual(stored["players"][0]["share"], {"vpinplay": False})

    def test_a_hand_edit_with_two_owners_keeps_the_first(self) -> None:
        self.path.write_text(json.dumps({"schema": 2, "players": [
            {"id": "Pppp111111", "initials": "OWN", "owner": True},
            {"id": "Pppp222222", "initials": "ABC", "owner": True}]}), encoding="utf-8")

        self.assertEqual([p.owner for p in self.roster.players()], [True, False])
        self.roster.remove("Pppp222222")
        self.assertEqual([p.player_id for p in self.roster.players()], ["Pppp111111"])

    def test_the_owner_is_listed_first_wherever_it_is_filed(self) -> None:
        self.path.write_text(json.dumps({"schema": 2, "players": [
            {"id": "Pppp222222", "initials": "ABC"},
            {"id": "Pppp111111", "initials": "OWN", "owner": True}]}), encoding="utf-8")

        self.assertEqual([p.player_id for p in self.roster.players()],
                         ["Pppp111111", "Pppp222222"])


class OwnerTests(_RosterCase):
    def test_the_owner_takes_the_2x_initials(self) -> None:
        owner = self.roster.ensure_owner(_config(" own "))

        self.assertTrue(owner.owner)
        self.assertEqual(owner.initials, "OWN")
        self.assertEqual(self.roster.owner(), owner)
        self.assertEqual(self._file()["migrations"], [OWNER_MIGRATION])

    def test_shorter_2x_initials_are_kept_as_they_are(self) -> None:
        owner = self.roster.ensure_owner(_config("OW"))

        self.assertEqual(owner.initials, "OW")

    def test_no_initials_anywhere_makes_an_owner_with_none(self) -> None:
        owner = self.roster.ensure_owner(_config())

        self.assertEqual(owner.initials, "")
        self.assertEqual(self.roster.up(), [owner])

    def test_it_runs_once(self) -> None:
        first = self.roster.ensure_owner(_config("OWN"))

        self.assertIsNone(self._restart().ensure_owner(_config("OWN")))
        self.assertEqual(self.roster.players(), [first])

    def test_initials_cleared_afterwards_are_not_brought_back(self) -> None:
        owner = self.roster.ensure_owner(_config("OWN"))
        self.roster.update_player(owner.player_id, initials="")

        self._restart().ensure_owner(_config("OWN"))

        self.assertEqual(self.roster.owner().initials, "")

    def test_an_owner_lost_after_the_first_start_comes_back_without_2x_initials(self) -> None:
        self.roster.ensure_owner(_config("OWN"))
        stored = self._file()
        stored["players"] = []
        self.path.write_text(json.dumps(stored), encoding="utf-8")

        owner = self._restart().ensure_owner(_config("OWN"))

        self.assertEqual(owner.initials, "")
        self.assertEqual(self._file()["migrations"], [OWNER_MIGRATION])

    def test_the_vpinplay_extensions_own_store_is_never_read(self) -> None:
        held = extension_store.ExtensionStore(Path(self.tmp.name) / "extensions.json")
        held.set_setting("vpinplay", "initials", "ZZZ")

        with mock.patch.object(extension_store, "_store", held):
            owner = self.roster.ensure_owner(_config())

        self.assertEqual(owner.initials, "")

    def test_the_owner_cannot_be_removed(self) -> None:
        owner = self.roster.ensure_owner(_config("OWN"))

        with self.assertRaises(service_errors.RefusedError):
            self.roster.remove(owner.player_id)
        self.assertEqual(self.roster.players(), [owner])


class KeptPlayerTests(_RosterCase):
    def setUp(self) -> None:
        super().setUp()
        self.owner = self.roster.ensure_owner(_config("OWN"))

    def test_initials_are_held_upper_case(self) -> None:
        self.assertEqual(self.roster.add_player(" Alex ", " abc ").initials, "ABC")
        self.assertEqual(self.roster.players()[-1].name, "Alex")

    def test_initials_that_are_not_three_characters_are_refused(self) -> None:
        for wrong in ("AB", "ABCD", "A"):
            with self.subTest(wrong=wrong), self.assertRaises(service_errors.RefusedError):
                self.roster.add_player("Alex", wrong)
        self.assertEqual(len(self.roster.players()), 1, "nothing was written")

    def test_initials_another_kept_player_has_are_refused_with_who(self) -> None:
        with self.assertRaises(service_errors.RefusedError) as caught:
            self.roster.add_player("Alex", "own")

        self.assertIn("OWN", str(caught.exception), "the owner has no name, so it says whose")

    def test_the_refusal_names_the_player_by_name(self) -> None:
        self.roster.add_player("Alex", "ABC")

        with self.assertRaises(service_errors.RefusedError) as caught:
            self.roster.add_player("Other", "abc")

        self.assertIn("Alex", str(caught.exception))

    def test_a_player_with_no_initials_clashes_with_nobody(self) -> None:
        self.roster.add_player("Alex")
        self.roster.add_player("Sam")

        self.assertEqual(len(self.roster.players()), 3)

    def test_a_rename_leaves_shorter_held_initials_alone(self) -> None:
        self.path.unlink()
        owner = self._restart().ensure_owner(_config("OW"))

        renamed = self.roster.update_player(owner.player_id, name="Jordan", initials="ow")

        self.assertEqual((renamed.name, renamed.initials), ("Jordan", "OW"))

    def test_changing_initials_is_checked_like_adding(self) -> None:
        alex = self.roster.add_player("Alex", "ABC")

        with self.assertRaises(service_errors.RefusedError):
            self.roster.update_player(alex.player_id, initials="AB")
        with self.assertRaises(service_errors.RefusedError):
            self.roster.update_player(alex.player_id, initials="Own")
        self.assertEqual(self.roster.update_player(alex.player_id, initials="xyz").initials,
                         "XYZ")

    def test_a_kept_player_is_removed(self) -> None:
        alex = self.roster.add_player("Alex", "ABC")

        self.assertEqual(self.roster.remove(alex.player_id), alex)

        self.assertEqual(self._restart().players(), [self.owner])

    def test_an_unknown_id_is_not_found(self) -> None:
        for call in (lambda: self.roster.remove("nobody"),
                     lambda: self.roster.update_player("nobody", name="X"),
                     lambda: self.roster.set_up("nobody")):
            with self.assertRaises(service_errors.NotFoundError):
                call()

    def test_adding_a_kept_player_does_not_put_them_up(self) -> None:
        self.roster.add_player("Alex", "ABC")

        self.assertEqual(self.roster.up(), [self.owner])


class GuestTests(_RosterCase):
    def setUp(self) -> None:
        super().setUp()
        self.owner = self.roster.ensure_owner(_config("OWN"))

    def test_a_guest_is_never_written(self) -> None:
        guest = self.roster.add_guest("abc")

        self.assertTrue(guest.guest)
        self.assertEqual(guest.initials, "ABC")
        self.assertNotIn(guest.player_id, json.dumps(self._file()))
        self.assertEqual(self._restart().players(), [self.owner], "gone when VPinFE closes")

    def test_a_guest_needs_initials(self) -> None:
        for wrong in ("", "  ", "AB"):
            with self.subTest(wrong=wrong), self.assertRaises(service_errors.RefusedError):
                self.roster.add_guest(wrong)

    def test_joining_makes_the_guest_up_alone(self) -> None:
        guest = self.roster.add_guest("ABC")

        self.assertEqual(self.roster.up(), [guest])
        self.assertEqual(self.roster.one_up(), guest)

    def test_the_owner_goes_back_up_for_a_game_together(self) -> None:
        guest = self.roster.add_guest("ABC")

        self.roster.set_up(self.owner.player_id)

        self.assertEqual(self.roster.up(), [self.owner, guest])
        self.assertIsNone(self.roster.one_up(), "with several up, nobody is the one")

    def test_when_the_last_guest_leaves_up_returns_to_the_owner(self) -> None:
        guest = self.roster.add_guest("ABC")

        self.roster.remove(guest.player_id)

        self.assertEqual(self.roster.up(), [self.owner])

    def test_a_kept_player_up_beside_the_last_guest_stays_up_when_they_leave(self) -> None:
        """Kid and a visitor are up and the visitor leaves: Kid's next game is Kid's."""
        kid = self.roster.add_player("Kid", "KID")
        visitor = self.roster.add_guest("ABC")
        self.roster.set_up(kid.player_id)

        self.roster.remove(visitor.player_id)

        self.assertEqual(self.roster.up(), [kid])

    def test_a_guest_who_was_not_up_leaving_changes_nobody_up(self) -> None:
        kid = self.roster.add_player("Kid", "KID")
        visitor = self.roster.add_guest("ABC")
        self.roster.set_who_is_up([kid.player_id])

        self.roster.remove(visitor.player_id)

        self.assertEqual(self.roster.up(), [kid])

    def test_a_guest_leaving_while_another_stays_keeps_the_other_up(self) -> None:
        first = self.roster.add_guest("ABC")
        second = self.roster.add_guest("XYZ")
        self.roster.set_up(first.player_id)

        self.roster.remove(first.player_id)

        self.assertEqual(self.roster.up(), [second])

    def test_a_guest_with_a_kept_players_initials_joins_and_both_are_marked(self) -> None:
        guest = self.roster.add_guest("own")

        rows = {row["id"]: row for row in self.roster.state()["players"]}
        self.assertEqual(rows[guest.player_id]["shares_initials_with"], [self.owner.player_id])
        self.assertEqual(rows[self.owner.player_id]["shares_initials_with"], [guest.player_id])
        self.assertIsNone(self.roster.whose("OWN"), "shared initials name nobody")

        self.roster.remove(guest.player_id)

        self.assertEqual(self.roster.whose("own"), self.owner)

    def test_a_guests_initials_do_not_stop_a_kept_player_either(self) -> None:
        self.roster.add_guest("ABC")

        self.assertEqual(self.roster.add_player("Alex", "ABC").initials, "ABC")


class UpTests(_RosterCase):
    def setUp(self) -> None:
        super().setUp()
        self.owner = self.roster.ensure_owner(_config("OWN"))
        self.alex = self.roster.add_player("Alex", "ABC")

    def test_the_owner_is_up_by_default(self) -> None:
        self.assertEqual(self.roster.up(), [self.owner])
        self.assertEqual(self.roster.one_up(), self.owner)

    def test_up_is_per_process_and_not_written(self) -> None:
        self.roster.set_up(self.alex.player_id)
        self.roster.set_up(self.owner.player_id, False)

        self.assertEqual(self.roster.up(), [self.alex])
        self.assertEqual(self._restart().up(), [self.owner])

    def test_taking_down_the_last_one_up_leaves_the_owner_up(self) -> None:
        self.roster.set_up(self.alex.player_id)
        self.roster.set_up(self.owner.player_id, False)

        self.roster.set_up(self.alex.player_id, False)

        self.assertEqual(self.roster.up(), [self.owner])

    def test_removing_a_player_who_is_up_takes_them_down(self) -> None:
        self.roster.set_up(self.alex.player_id)
        self.roster.set_up(self.owner.player_id, False)

        self.roster.remove(self.alex.player_id)

        self.assertEqual(self.roster.up(), [self.owner])

    def test_the_whole_set_can_be_named_at_once(self) -> None:
        guest = self.roster.add_guest("XYZ")

        up = self.roster.set_who_is_up([guest.player_id, self.alex.player_id,
                                        guest.player_id])

        self.assertEqual(up, [self.alex, guest], "in roster order, each once")
        self.assertEqual(self.roster.up(), [self.alex, guest])

    def test_naming_nobody_up_leaves_the_owner_up(self) -> None:
        self.roster.set_who_is_up([self.alex.player_id])

        self.assertEqual(self.roster.set_who_is_up([]), [self.owner])

    def test_a_set_naming_someone_unknown_changes_nothing(self) -> None:
        with self.assertRaises(service_errors.NotFoundError):
            self.roster.set_who_is_up([self.alex.player_id, "Nobody0000"])

        self.assertEqual(self.roster.up(), [self.owner])

    def test_whose_is_by_initials_up_or_not(self) -> None:
        self.assertEqual(self.roster.whose("abc"), self.alex)
        self.assertIsNone(self.roster.whose(""))
        self.assertIsNone(self.roster.whose("ZZZ"))


class ChangedEventTests(_RosterCase):
    def setUp(self) -> None:
        super().setUp()
        self.heard: list[dict] = []
        handler = events.subscribe(events.PLAYERS_CHANGED,
                                   lambda **payload: self.heard.append(payload["state"]))
        self.addCleanup(events.unsubscribe, events.PLAYERS_CHANGED, handler)

    def test_every_change_carries_the_whole_roster(self) -> None:
        owner = self.roster.ensure_owner(_config("OWN"))
        guest = self.roster.add_guest("ABC")

        self.assertEqual(len(self.heard), 2)
        self.assertEqual(self.heard[-1], self.roster.state())
        self.assertEqual(self.heard[-1]["players"], [
            {"id": owner.player_id, "name": "", "initials": "OWN", "owner": True,
             "guest": False, "up": False, "shares_initials_with": []},
            {"id": guest.player_id, "name": "", "initials": "ABC", "owner": False,
             "guest": True, "up": True, "shares_initials_with": []},
        ])

    def test_each_kind_of_change_is_announced(self) -> None:
        owner = self.roster.ensure_owner(_config("OWN"))
        alex = self.roster.add_player("Alex", "ABC")
        self.roster.update_player(alex.player_id, name="Alexandra")
        self.roster.set_up(alex.player_id)
        guest = self.roster.add_guest("XYZ")
        self.roster.remove(guest.player_id)
        self.roster.remove(alex.player_id)

        self.assertEqual(len(self.heard), 7)
        self.assertEqual([row["id"] for row in self.heard[-1]["players"]], [owner.player_id])

    def test_nothing_that_changes_nothing_is_announced(self) -> None:
        owner = self.roster.ensure_owner(_config("OWN"))
        self.heard.clear()

        self.roster.ensure_owner(_config("OWN"))
        self.roster.set_up(owner.player_id)
        self.roster.set_up(owner.player_id, False)
        self.roster.update_player(owner.player_id, initials="own")

        self.assertEqual(self.heard, [])

    def test_a_refused_change_is_not_announced(self) -> None:
        self.roster.ensure_owner(_config("OWN"))
        self.heard.clear()

        with self.assertRaises(service_errors.RefusedError):
            self.roster.add_player("Alex", "OWN")

        self.assertEqual(self.heard, [])


if __name__ == "__main__":
    unittest.main()
