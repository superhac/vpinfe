"""One collection in, one ordered list out.

The cases that matter are the ones the two old engines could not express: a game
appearing twice with different tables, a pin that outranks a filter, an exclusion that
outranks both, and `hidden` outranking everything.
"""

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

from common.games.collection_resolver import (
    UnresolvableCollectionError,
    resolve,
    visible_entries,
)
from common.games.collection_store import CollectionStore


def _game(gid, title, tables, manufacturer="", rating=0, last_run=0, default=""):
    """A game whose tables map is keyed by id, as storage has it."""
    return SimpleNamespace(
        gameDirName=title,
        creation_time=0,
        metaConfig={
            "Info": {"Title": title, "Manufacturer": manufacturer, "Year": "1995",
                     "Type": "SS", "Themes": []},
            "User": {"Rating": rating, "LastRun": last_run, "StartCount": 0, "RunTime": 0},
            "vpinfe": {"game_id": gid, **({"default_table": default} if default else {})},
            "tables": tables,
        },
    )


def _table(tid, filename, hidden=False):
    entry = {"id": tid, "filename": filename}
    if hidden:
        entry["hidden"] = True
    return entry


class ResolverTests(unittest.TestCase):
    def setUp(self) -> None:
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.path = Path(tmp.name) / "collections.json"
        self.collections = CollectionStore(str(self.path))

        self.mm = _game("mm", "Medieval Madness",
                        {"vpw": _table("vpw", "MM VPW.vpx"),
                         "jp": _table("jp", "MM JP.vpx")},
                        manufacturer="Williams", rating=5, last_run=200, default="vpw")
        self.afm = _game("afm", "Attack from Mars",
                         {"a1": _table("a1", "AFM.vpx"),
                          "vr": _table("vr", "AFM VR.vpx")},
                         manufacturer="Bally", rating=3, last_run=100, default="a1")
        self.taf = _game("taf", "The Addams Family",
                         {"t1": _table("t1", "TAF.vpx")},
                         manufacturer="Bally", rating=4, last_run=50)
        self.games = [self.mm, self.afm, self.taf]

    def _ids(self, entries):
        return [(e.game.metaConfig["vpinfe"]["game_id"], e.table_id) for e in entries]

    # --- the case the whole design exists for ------------------------------------

    def test_one_game_appears_twice_with_different_tables_in_a_curated_order(self) -> None:
        self.collections.add_collection("Friday Night")
        self.collections.set_order("Friday Night", "manual")
        self.collections.add_member("Friday Night", "mm", table_id="vpw")
        self.collections.add_member("Friday Night", "afm")
        self.collections.add_member("Friday Night", "mm", table_id="jp")

        entries = resolve("Friday Night", self.collections, self.games, expanded=True)

        self.assertEqual(self._ids(entries),
                         [("mm", "vpw"), ("afm", "a1"), ("afm", "vr"), ("mm", "jp")])

    def test_collapsing_keeps_the_first_entry_each_game_contributed(self) -> None:
        self.collections.add_collection("Friday Night")
        self.collections.set_order("Friday Night", "manual")
        self.collections.add_member("Friday Night", "mm", table_id="jp")
        self.collections.add_member("Friday Night", "afm")

        entries = resolve("Friday Night", self.collections, self.games)

        self.assertEqual(self._ids(entries), [("mm", "jp"), ("afm", "a1")],
                         "the curator's pick, then the followed game's default")

    def test_a_followed_game_expands_default_first(self) -> None:
        self.collections.add_collection("All")
        self.collections.add_member("All", "afm")

        entries = resolve("All", self.collections, self.games, expanded=True)

        self.assertEqual(self._ids(entries), [("afm", "a1"), ("afm", "vr")])

    # --- precedence ---------------------------------------------------------------

    def test_a_member_overrides_what_the_filter_would_have_taken(self) -> None:
        """Explicit beats implicit: naming a game says exactly what it contributes."""
        self.collections.add_filter_collection("Bally", manufacturer="Bally")
        self.collections.add_member("Bally", "afm", table_id="vr")

        entries = resolve("Bally", self.collections, self.games, expanded=True)

        self.assertIn(("afm", "vr"), self._ids(entries))
        self.assertNotIn(("afm", "a1"), self._ids(entries),
                         "the filter must not re-add the table the member excluded")

    def test_an_exclusion_overrules_a_filter(self) -> None:
        self.collections.add_filter_collection("Bally", manufacturer="Bally")
        self.collections.exclude("Bally", "taf")

        entries = resolve("Bally", self.collections, self.games, expanded=True)

        self.assertEqual({gid for gid, _ in self._ids(entries)}, {"afm"})

    def test_excluding_one_table_leaves_the_rest_of_the_game(self) -> None:
        self.collections.add_filter_collection("Bally", manufacturer="Bally")
        self.collections.exclude("Bally", "afm", table_id="vr")

        entries = resolve("Bally", self.collections, self.games, expanded=True)

        self.assertIn(("afm", "a1"), self._ids(entries))
        self.assertNotIn(("afm", "vr"), self._ids(entries))

    def test_hidden_beats_a_pin(self) -> None:
        """`hidden` is library-wide and exists so a patch base can stay on disk."""
        self.mm.metaConfig["tables"]["jp"]["hidden"] = True
        self.collections.add_collection("Friday Night")
        self.collections.add_member("Friday Night", "mm", table_id="jp")

        entries = resolve("Friday Night", self.collections, self.games, expanded=True)

        self.assertEqual(entries, [])

    def test_a_hidden_table_is_not_offered_to_a_follower(self) -> None:
        self.afm.metaConfig["tables"]["vr"]["hidden"] = True
        self.collections.add_collection("All")
        self.collections.add_member("All", "afm")

        entries = resolve("All", self.collections, self.games, expanded=True)

        self.assertEqual(self._ids(entries), [("afm", "a1")])

    # --- ordering -----------------------------------------------------------------

    def test_a_filter_collection_sorts_by_its_stored_criteria(self) -> None:
        """Titles sort as they are displayed, so a leading "The" is moved to the end -
        "The Addams Family" sorts under A. Long-standing behavior, kept."""
        self.collections.add_filter_collection("Everything", sort_by="Alpha",
                                               order_by="Ascending")

        entries = resolve("Everything", self.collections, self.games)

        self.assertEqual([e.game.gameDirName for e in entries],
                         ["The Addams Family", "Attack from Mars", "Medieval Madness"])

    def test_last_played_sorts_most_recent_first(self) -> None:
        self.collections.add_filter_collection("Recent", sort_by="LastRun")

        entries = resolve("Recent", self.collections, self.games)

        self.assertEqual([e.game.gameDirName for e in entries],
                         ["Medieval Madness", "Attack from Mars", "The Addams Family"])

    def test_two_resolutions_of_the_same_input_agree(self) -> None:
        """Peers that tie on the sort key must not shuffle between refreshes."""
        self.collections.add_filter_collection("Everything", sort_by="Alpha")

        first = resolve("Everything", self.collections, self.games, expanded=True)
        second = resolve("Everything", self.collections, self.games, expanded=True)

        self.assertEqual(self._ids(first), self._ids(second))

    # --- refusal ------------------------------------------------------------------

    def test_a_filter_this_build_cannot_read_refuses_by_name(self) -> None:
        """Resolving what is left would answer a different question, silently."""
        self.collections.add_filter_collection("VR Room")
        self.collections.set_filter("VR Room", "app", "VPX VR")

        with self.assertRaises(UnresolvableCollectionError) as caught:
            resolve("VR Room", self.collections, self.games)

        self.assertIn("app", caught.exception.axes)
        self.assertIn("VR Room", str(caught.exception))

    def test_a_member_the_library_does_not_hold_is_skipped_not_dropped(self) -> None:
        self.collections.add_collection("Fav")
        self.collections.add_member("Fav", "not-here")
        self.collections.add_member("Fav", "taf")

        entries = resolve("Fav", self.collections, self.games)

        self.assertEqual(self._ids(entries), [("taf", "t1")])
        self.assertEqual(self.collections.get_members("Fav"), ["not-here", "taf"],
                         "the membership stays on disk; the game may come back")


class VisibleEntryTests(unittest.TestCase):
    def test_a_game_with_no_tables_offers_nothing(self) -> None:
        self.assertEqual(visible_entries(_game("x", "Empty", {})), [])

    def test_every_table_hidden_offers_nothing(self) -> None:
        game = _game("x", "All Hidden", {"a": _table("a", "a.vpx", hidden=True)})
        self.assertEqual(visible_entries(game), [])


if __name__ == "__main__":
    unittest.main()


class OrderDefaultTests(unittest.TestCase):
    """A collection curated before curated order existed was shown alphabetically.
    Honouring its insertion order would reshuffle a list the user is used to, so
    `manual` is opt-in and everything else falls back to title."""

    def setUp(self) -> None:
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.collections = CollectionStore(str(Path(tmp.name) / "collections.json"))
        self.games = [
            _game("zz", "Zaccaria", {"a": _table("a", "z.vpx")}),
            _game("aa", "Apollo 13", {"b": _table("b", "a.vpx")}),
            _game("mm", "Medieval Madness", {"c": _table("c", "m.vpx")}),
        ]
        self.collections.add_collection("Favorites")
        for gid in ("zz", "mm", "aa"):
            self.collections.add_member("Favorites", gid)

    def _titles(self):
        return [e.game.gameDirName
                for e in resolve("Favorites", self.collections, self.games)]

    def test_a_manual_collection_defaults_to_title_order(self) -> None:
        self.assertEqual(self._titles(), ["Apollo 13", "Medieval Madness", "Zaccaria"])

    def test_saying_manual_uses_the_order_the_user_arranged(self) -> None:
        self.collections.set_order("Favorites", "manual")

        self.assertEqual(self._titles(), ["Zaccaria", "Medieval Madness", "Apollo 13"])

    def test_the_order_block_survives_a_round_trip(self) -> None:
        self.collections.set_order("Favorites", "manual")
        self.collections.save()

        reopened = CollectionStore(str(self.collections.path))
        self.assertEqual(reopened.get_order("Favorites"),
                         {"by": "manual", "direction": "asc"})

    def test_a_filter_collections_stored_sort_still_applies(self) -> None:
        """Read from where it has always been stored, in the new vocabulary."""
        self.collections.add_filter_collection("Recent", sort_by="LastRun",
                                               order_by="Descending")

        self.assertEqual(self.collections.get_order("Recent"),
                         {"by": "last_played", "direction": "desc"})
