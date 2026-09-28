"""The remote's shape: which machines it can aim at, and where it sends what it says."""

from __future__ import annotations

import ast
import json
import unittest
from pathlib import Path
from unittest import mock

from console import remote
from console.api import _lines, read_frames
from httpapi import events
from tests.support import trees


def _device(device_id: str, **rest) -> dict:
    return {"device_id": device_id, "kind": "vpinfe", "display_name": "",
            "features": ["library", "frontend"], "address": "10.0.0.9",
            "port": 8080} | rest


class TargetTests(unittest.TestCase):
    def test_a_machine_that_does_not_play_is_not_a_target(self) -> None:
        """It is a real device and belongs in the Console's list. Offering it here makes
        the picker a list of machines rather than a list of answers to "where"."""
        found = remote.targets(
            [_device("a"), _device("b", features=["library"])], "a")

        self.assertEqual([one["device_id"] for one in found], ["a"])

    def test_this_install_leads(self) -> None:
        """The one the person most likely means, and the only one certainly there - it
        is serving the page."""
        found = remote.targets([_device("far"), _device("here")], "here")

        self.assertEqual([one["device_id"] for one in found], ["here", "far"])

    def test_a_machine_with_an_address_and_no_port_is_not_offered(self) -> None:
        """An entry written before installs declared a port cannot be dialled, and a
        picker entry that cannot answer is worse than one that is not there."""
        found = remote.targets([_device("a", port=0)], "z")

        self.assertEqual(found, [])

    def test_a_row_with_no_address_is_this_machine(self) -> None:
        """Not a fallback for a broken entry - it is how this install looks in its own
        registry. There is no address it would reach itself on, every other row is
        written from one it was heard at, and a phone is refused without one."""
        here = _device("a", address="", port=0)

        self.assertTrue(remote.is_here(here, ""))
        self.assertIn("127.0.0.1", remote.base_url_of(here, ""))
        self.assertEqual([one["device_id"] for one in remote.targets([here], "")], ["a"])

    def test_an_install_that_reported_no_id_is_still_a_target(self) -> None:
        """Discovery reads the identity off the config file every time it is asked, and
        a read landing while that file is rewritten answers with no id. Keying only on
        the id made the surface say there was nothing to drive at all."""
        found = remote.targets([_device("a", address="", port=0)], "")

        self.assertEqual([one["device_id"] for one in found], ["a"])

    def test_this_install_is_reached_on_loopback(self) -> None:
        """Its registry entry holds the address *other* machines reach it on. Dialling
        that from here asks the network a question we can answer without it."""
        where = remote.base_url_of(_device("here", address="10.0.0.9"), "here")

        self.assertNotIn("10.0.0.9", where)
        self.assertIn("127.0.0.1", where)

    def test_another_install_is_reached_where_it_said(self) -> None:
        """The whole of the routing: a press reaches the windows of the machine that
        received it, so aiming somewhere else is a different base URL."""
        where = remote.base_url_of(_device("far", address="10.0.0.9", port=8080), "here")

        self.assertEqual(where, "http://10.0.0.9:8080")

    def test_a_device_that_named_itself_nothing_still_has_a_name(self) -> None:
        """A picker row with no words in it cannot be chosen between."""
        self.assertEqual(remote.target_name(_device("a")), "This device")
        self.assertEqual(remote.target_name(_device("a", display_name="Cab")), "Cab")


class LastPlayedTests(unittest.TestCase):
    """What Now says when nothing is playing, which is most of the time."""

    def _game(self, name: str, when) -> dict:
        return {"id": name, "name": name, "user": {"last_played": when}}

    def test_the_most_recent_one_wins(self) -> None:
        found = remote.last_played([self._game("old", "2026-01-01T00:00:00Z"),
                                    self._game("new", "2026-09-01T00:00:00Z"),
                                    self._game("mid", "2026-05-01T00:00:00Z")])

        self.assertEqual(found["name"], "new")

    def test_a_game_nobody_has_played_is_not_the_last_played(self) -> None:
        """`last_played` is null on a fresh library, and null sorts above a date in a
        plain max - which would have named an unplayed game as the one just finished."""
        found = remote.last_played([self._game("never", None),
                                    self._game("once", "2026-01-01T00:00:00Z")])

        self.assertEqual(found["name"], "once")

    def test_a_library_nobody_has_played_says_nothing(self) -> None:
        self.assertEqual(remote.last_played([self._game("never", None)]), {})
        self.assertEqual(remote.last_played([]), {})


class FindTests(unittest.TestCase):
    """The search field, which is the answer to a library longer than a screen."""

    LIBRARY = [
        {"id": "a", "name": "Attack from Mars", "manufacturer": "Bally", "year": "1995"},
        {"id": "b", "name": "Medieval Madness", "manufacturer": "Williams", "year": "1997"},
        {"id": "c", "name": "Monster Bash", "manufacturer": "Williams", "year": "1998"},
    ]

    def _names(self, said: str) -> list[str]:
        return [one["name"] for one in remote.matching(self.LIBRARY, said)]

    def test_nothing_typed_is_the_whole_library(self) -> None:
        self.assertEqual(len(remote.matching(self.LIBRARY, "")), 3)

    def test_the_maker_and_the_year_are_searched_too(self) -> None:
        """The three things somebody standing at a machine knows about it."""
        self.assertEqual(self._names("bally"), ["Attack from Mars"])
        self.assertEqual(self._names("1998"), ["Monster Bash"])

    def test_a_second_word_narrows_rather_than_widens(self) -> None:
        """Which is what a person means by typing one. Matching any word instead would
        make the list grow as they tried to shorten it."""
        self.assertEqual(self._names("williams 1997"), ["Medieval Madness"])

    def test_case_is_not_something_anybody_types(self) -> None:
        self.assertEqual(self._names("MEDIEVAL"), ["Medieval Madness"])

    def test_a_word_in_nothing_finds_nothing(self) -> None:
        self.assertEqual(self._names("zaccaria"), [])


class CollectionTests(unittest.TestCase):
    def test_only_lists_you_keep_can_be_added_to(self) -> None:
        """A filter collection is a rule. Pinning a game against a rule is a decision
        made with the rule in view, and that is desk work."""
        found = remote.manual_collections([
            {"name": "Mine", "type": "manual"},
            {"name": "Last Played", "type": "filter"},
            {"name": "", "type": "manual"},
        ])

        self.assertEqual(found, ["Mine"])

    def test_no_collection_chosen_leaves_the_library_alone(self) -> None:
        """None and empty are different answers: nothing chosen is the whole library,
        and a collection that resolves to nothing is an empty list."""
        games = [{"id": "a"}, {"id": "b"}]

        self.assertEqual(remote.in_collection(games, None), games)
        self.assertEqual(remote.in_collection(games, set()), [])
        self.assertEqual(remote.in_collection(games, {"b"}), [{"id": "b"}])


class FollowsTheCabinetTests(unittest.TestCase):
    def test_a_game_with_several_entries_is_listed_once(self) -> None:
        entries = [{"game": {"id": "a", "name": "A"}}, {"game": {"id": "b", "name": "B"}},
                   {"game": {"id": "a", "name": "A"}}]

        self.assertEqual([one["id"] for one in remote.offered_games(entries)], ["a", "b"])

    def test_a_collection_kept_out_of_the_frontend_is_not_offered(self) -> None:
        collections = [{"name": "Shown", "in_frontend": True},
                       {"name": "Kept off", "in_frontend": False}]

        self.assertEqual(remote.frontend_collections(collections), ["Shown"])

    def test_the_one_already_chosen_stays_whatever_the_switch_says(self) -> None:
        collections = [{"name": "Shown", "in_frontend": True},
                       {"name": "Kept off", "in_frontend": False}]

        self.assertEqual(remote.frontend_collections(collections, "Kept off"),
                         ["Shown", "Kept off"])


class FollowsTheFrontendTests(unittest.TestCase):
    SHOWING = {"running": True, "collection": "Mine",
               "game": {"id": "g1", "name": "Medieval Madness"}}

    def test_a_target_that_cannot_say_is_not_a_closed_frontend(self) -> None:
        """None is an install too old to report its frontend. Saying "closed" there
        would take the pad away from a phone that drives it fine."""
        self.assertFalse(remote.frontend_closed(None))
        self.assertFalse(remote.mirroring(None))
        self.assertTrue(remote.frontend_closed({"running": False}))
        self.assertTrue(remote.mirroring(self.SHOWING))

    def test_the_game_on_the_wheel_is_the_one_the_list_holds(self) -> None:
        games = [{"id": "g1", "name": "Medieval Madness", "year": "1997"}]

        self.assertEqual(remote.on_the_wheel(self.SHOWING, games), games[0])

    def test_a_game_the_list_does_not_hold_is_still_named(self) -> None:
        """The wheel can sit on a game the phone has filtered out; the strip still
        says what the screen shows."""
        self.assertEqual(remote.on_the_wheel(self.SHOWING, []),
                         {"id": "g1", "name": "Medieval Madness"})

    def test_an_empty_wheel_has_nothing_on_it(self) -> None:
        empty = self.SHOWING | {"game": None}

        self.assertEqual(remote.on_the_wheel(empty, [{"id": "g1"}]), {})
        self.assertEqual(remote.wheel_id(empty), "")
        self.assertEqual(remote.wheel_id(None), "")


class TakePictureTests(unittest.TestCase):
    PLAYING = {"launching": True, "game_name": "Example", "source": "frontend",
               "paused": False}
    UP = {"running": True, "collection": "", "game": None}

    def test_offered_while_a_table_is_played(self) -> None:
        self.assertTrue(remote.takes_pictures(self.PLAYING, self.UP))
        self.assertTrue(remote.takes_pictures(self.PLAYING | {"source": "remote"}, None))

    def test_not_while_nothing_is_played_or_a_recording_runs(self) -> None:
        self.assertFalse(remote.takes_pictures({"launching": False}, self.UP))
        self.assertFalse(remote.takes_pictures(self.PLAYING | {"source": "capture"},
                                               self.UP))

    def test_not_with_the_frontend_closed_since_nothing_would_hear_it(self) -> None:
        self.assertFalse(remote.takes_pictures(self.PLAYING, self.UP | {"running": False}))

    def test_its_press_is_the_input_action_of_that_name(self) -> None:
        from common import input_registry

        self.assertIn("take_picture", input_registry.IN_PLAY)
        self.assertIn("back", input_registry.IN_PLAY)
        self.assertIn("take_picture", remote.BUTTON_WORDS)


class ReadsTheEventStreamTests(unittest.TestCase):
    """The reader is held to the frames the install writes, not to a copy of them."""

    def _stream(self) -> list[str]:
        state = {"state": {"running": True, "collection": "Mine", "game": None}}
        return [f"retry: {events.RETRY_MS}\n\n",
                events._frame(events.HELLO_EVENT, json.dumps({"seq": 3, "resumed": False})),
                ": keepalive\n\n",
                events._frame("frontend.state_changed", json.dumps(state), 4),
                events._frame("frontend.state_changed", "not json", 5)]

    def _read(self, chunks: list[bytes]) -> list[tuple[str, dict]]:
        return list(read_frames(_lines(chunks)))

    def test_every_frame_the_install_writes_is_read(self) -> None:
        found = self._read(["".join(self._stream()).encode()])

        self.assertEqual([name for name, _ in found],
                         [events.HELLO_EVENT, "frontend.state_changed"])
        self.assertEqual(found[1][1]["state"]["collection"], "Mine")

    def test_a_frame_split_anywhere_reads_the_same(self) -> None:
        whole = "".join(self._stream()).encode()
        one_byte_at_a_time = [whole[at:at + 1] for at in range(len(whole))]

        self.assertEqual(self._read(one_byte_at_a_time), self._read([whole]))

    def test_a_carriage_return_does_not_reach_the_name(self) -> None:
        crlf = "".join(self._stream()).replace("\n", "\r\n").encode()

        self.assertEqual(self._read([crlf]), self._read(["".join(self._stream()).encode()]))


class WritesGoToTheTargetTests(unittest.TestCase):
    """A client with no base URL is this install. The Remote may use one only to read
    what this install knows about the network; everything else goes to the target."""

    ALLOWED = {("console/remote.py", "_read_here")}

    def _unaimed_clients(self, relative: str) -> list[tuple[str, int]]:
        tree = trees.tree_for(Path(__file__).resolve().parents[2] / relative)
        found = set()
        for function in ast.walk(tree):
            if not isinstance(function, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for node in ast.walk(function):
                if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                        and node.func.id == "ApiClient" and not node.args
                        and not node.keywords
                        and (relative, function.name) not in self.ALLOWED):
                    found.add((function.name, node.lineno))
        return sorted(found)

    def test_the_remote_writes_through_the_target(self) -> None:
        for relative in ("console/remote.py", "console/remote_record.py"):
            with self.subTest(relative):
                self.assertEqual(self._unaimed_clients(relative), [])


def _player(player_id: str, **rest) -> dict:
    return {"id": player_id, "name": "", "initials": "", "owner": False,
            "guest": False, "up": False} | rest


class IdentityTests(unittest.TestCase):
    """Who a phone is answering for: nobody said behaves as the owner, and everyone
    else is a rating and a favorite going to the wrong place away from that."""

    def test_nobody_said_is_not_someone_else(self) -> None:
        self.assertFalse(remote.is_someone_else(None))

    def test_the_owner_would_not_be_someone_else_either(self) -> None:
        # Never actually reached - the owner is always `None` here - but the function
        # itself should answer the same either way, not just for the identity the app
        # happens to produce.
        self.assertFalse(remote.is_someone_else(_player("own", owner=True)))

    def test_a_kept_player_and_a_guest_are_both_someone_else(self) -> None:
        self.assertTrue(remote.is_someone_else(_player("kid")))
        self.assertTrue(remote.is_someone_else(_player("vis", guest=True)))

    def test_a_stale_remembered_id_resolves_to_nobody(self) -> None:
        """A kept player removed, or a guest signed out, elsewhere leaves nothing for
        the id to resolve to - and a stale answer must not go on editing somebody's
        record once they are no longer on the roster."""
        with mock.patch.object(remote.remembered, "get", return_value={"player_id": "gone"}):
            found = remote.remembered_identity(_device("here"), [_player("kid")])

        self.assertIsNone(found)

    def test_a_held_id_still_on_the_roster_resolves(self) -> None:
        with mock.patch.object(remote.remembered, "get", return_value={"player_id": "kid"}):
            found = remote.remembered_identity(_device("here"), [_player("kid")])

        self.assertEqual(found["id"], "kid")

    def test_nothing_remembered_is_nobody_said(self) -> None:
        with mock.patch.object(remote.remembered, "get", return_value=None):
            found = remote.remembered_identity(_device("here"), [_player("kid")])

        self.assertIsNone(found)

    def test_storage_is_keyed_by_target_so_two_targets_hold_different_answers(self) -> None:
        self.assertNotEqual(remote._identity_key(_device("a")), remote._identity_key(_device("b")))


class HasInitialsTests(unittest.TestCase):
    """Whether the consent step offers Share: the extension's own `claim` refuses
    without initials."""

    def test_blank_initials_cannot_share(self) -> None:
        self.assertFalse(remote._has_initials(_player("vis", guest=True, initials="")))

    def test_whitespace_only_initials_cannot_share(self) -> None:
        self.assertFalse(remote._has_initials(_player("vis", guest=True, initials="   ")))

    def test_real_initials_can_share(self) -> None:
        self.assertTrue(remote._has_initials(_player("vis", guest=True, initials="VIS")))


class RatingOfTests(unittest.TestCase):
    """The stars shown while browsing: the library's for the owner, a player's own
    record for anyone else - never read from the field the other one writes."""

    GAME = {"id": "g1", "user": {"rating": 4}}

    def test_nobody_said_reads_the_librarys_rating(self) -> None:
        self.assertEqual(remote._rating_of("g1", self.GAME, None, {"g1": {"rating": 2}}), 4)

    def test_a_kept_player_reads_their_own_record_not_the_library(self) -> None:
        self.assertEqual(
            remote._rating_of("g1", self.GAME, _player("kid"), {"g1": {"rating": 2}}), 2)

    def test_a_game_not_in_their_record_is_unrated_to_them(self) -> None:
        self.assertEqual(remote._rating_of("g1", self.GAME, _player("kid"), {}), 0)


class VisibleUpTests(unittest.TestCase):
    """Which of who was up belongs on this phone's result card."""

    UP = [_player("own", owner=True), _player("kid"), _player("vis", guest=True)]

    def test_nobody_said_sees_everyone_in_order(self) -> None:
        self.assertEqual([p["id"] for p in remote._visible_up(None, self.UP)],
                         ["own", "kid", "vis"])

    def test_a_kept_player_sees_theirs_first_then_the_rest(self) -> None:
        found = remote._visible_up(_player("kid"), self.UP)

        self.assertEqual([p["id"] for p in found], ["kid", "own", "vis"])

    def test_a_guest_sees_only_theirs(self) -> None:
        found = remote._visible_up(_player("vis", guest=True), self.UP)

        self.assertEqual([p["id"] for p in found], ["vis"])

    def test_a_kept_player_not_part_of_this_play_sees_nothing(self) -> None:
        """The same reason a guest sees nothing of somebody else's - a household
        member's phone does not become a window onto a play they were not part of."""
        found = remote._visible_up(_player("someone_else"), self.UP)

        self.assertEqual(found, [])

    def test_a_guest_not_part_of_this_play_sees_nothing(self) -> None:
        found = remote._visible_up(_player("another_guest", guest=True), self.UP)

        self.assertEqual(found, [])


class SendStatusTests(unittest.TestCase):
    """What an account did with a game just played, from what it holds locally - never
    a fact this install's own books can settle by asking the far end again."""

    def test_an_account_not_sharing_says_nothing(self) -> None:
        self.assertEqual(
            remote._send_status({"share": False, "waiting": True}, credited=True,
                                several_up=False), "")

    def test_sharing_and_credited_and_nothing_waiting_is_sent(self) -> None:
        said = remote._send_status({"share": True, "waiting": False, "label": "VPinPlay"},
                                   credited=True, several_up=False)

        self.assertEqual(said, "Sent to VPinPlay")

    def test_sharing_and_waiting_is_waiting_even_if_credited(self) -> None:
        said = remote._send_status({"share": True, "waiting": True, "label": "VPinPlay"},
                                   credited=True, several_up=False)

        self.assertEqual(said, "Waiting to send")

    def test_alone_and_not_credited_is_still_sent(self) -> None:
        """Nobody else was up, so there was only one player this send could ever have
        been for - not being the one credited does not mean anything was refused."""
        said = remote._send_status({"share": True, "waiting": False, "label": "VPinPlay"},
                                   credited=False, several_up=False)

        self.assertEqual(said, "Sent to VPinPlay")

    def test_several_up_and_not_credited_is_not_sent(self) -> None:
        said = remote._send_status({"share": True, "waiting": False, "label": "VPinPlay"},
                                   credited=False, several_up=True)

        self.assertEqual(said, "Not sent: VPinPlay takes one player per game")

    def test_the_label_falls_back_to_the_extension_name(self) -> None:
        said = remote._send_status({"share": True, "waiting": False, "extension": "vpinplay"},
                                   credited=True, several_up=False)

        self.assertEqual(said, "Sent to vpinplay")


class PlayRecordedTests(unittest.IsolatedAsyncioTestCase):
    """`table.play_recorded`: the result card built for whoever of who was up belongs
    on this phone, with what each of their sharing accounts did with it."""

    def setUp(self) -> None:
        self.enterContext(mock.patch.object(remote.offload, "io", mock.AsyncMock(
            side_effect=lambda call, *a, **kw: call(*a, **kw))))
        self.accounts: dict[str, list[dict]] = {}
        self.redraw = mock.Mock()

    def _client(self):
        accounts = self.accounts

        class _C:
            def player_accounts(self, player_id: str) -> list[dict]:
                return accounts.get(player_id, [])

        return lambda: _C()

    async def _fire(self, state: dict, payload: dict) -> None:
        await remote._play_recorded(state, payload, self._client(), self.redraw)

    async def test_a_private_game_reports_no_send_status(self) -> None:
        self.accounts["kid"] = [{"share": True, "waiting": False, "label": "VPinPlay"}]
        state = {"identity": None, "screen": remote.NOW}

        await self._fire(state, {"up": [_player("kid")], "private": True,
                                 "new_entries": [], "game": {"id": "g1", "name": "Alpha"}})

        self.assertEqual(state["result"]["players"][0]["statuses"], [])

    async def test_a_credited_solo_play_carries_the_score_line_and_is_sent(self) -> None:
        self.accounts["kid"] = [{"share": True, "waiting": False, "label": "VPinPlay"}]
        state = {"identity": None, "screen": remote.NOW}
        entry = {"score": 12345, "text": "12,345"}

        await self._fire(state, {
            "up": [_player("kid")], "private": False,
            "new_entries": [{"player": {"id": "kid"}, "entries": [entry]}],
            "game": {"id": "g1", "name": "Alpha"}})

        row = state["result"]["players"][0]
        self.assertIn("12,345", row["entry"])
        self.assertEqual(row["statuses"], ["Sent to VPinPlay"])

    async def test_the_second_of_two_up_uncredited_is_not_sent(self) -> None:
        self.accounts["own"] = [{"share": True, "waiting": False, "label": "VPinPlay"}]
        self.accounts["kid"] = [{"share": True, "waiting": False, "label": "VPinPlay"}]
        state = {"identity": None, "screen": remote.NOW}

        await self._fire(state, {
            "up": [_player("own", owner=True), _player("kid")], "private": False,
            "new_entries": [{"player": {"id": "own"}, "entries": [{"score": 1, "text": "1"}]}],
            "game": {"id": "g1", "name": "Alpha"}})

        rows = {row["player"]["id"]: row for row in state["result"]["players"]}
        self.assertEqual(rows["own"]["statuses"], ["Sent to VPinPlay"])
        self.assertEqual(rows["kid"]["statuses"],
                         ["Not sent: VPinPlay takes one player per game"])

    async def test_a_guest_whose_own_phone_was_not_part_of_the_play_gets_no_card(self) -> None:
        state = {"identity": _player("someone_else", guest=True), "screen": remote.NOW}
        before = state.get("result")

        await self._fire(state, {"up": [_player("kid")], "private": False,
                                 "new_entries": [], "game": {"id": "g1", "name": "Alpha"}})

        self.assertEqual(state.get("result"), before)

    async def test_now_open_redraws_but_another_screen_does_not(self) -> None:
        state = {"identity": None, "screen": remote.PLAY}

        await self._fire(state, {"up": [_player("kid")], "private": False,
                                 "new_entries": [], "game": {"id": "g1", "name": "Alpha"}})

        self.assertIsNotNone(state.get("result"))
        self.redraw.assert_not_called()
