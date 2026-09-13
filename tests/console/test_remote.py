"""The remote's shape: which machines it can aim at, and where it sends what it says."""

from __future__ import annotations

import unittest

from console import remote


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

    def test_a_machine_that_named_itself_nothing_still_has_a_name(self) -> None:
        """A picker row with no words in it cannot be chosen between."""
        self.assertEqual(remote.target_name(_device("a")), "This machine")
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
