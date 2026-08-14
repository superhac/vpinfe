"""Filtering and sorting answer the same on a wire entry as on the game it came from.

The axis registry and the sort keys are written against a `Game` and read `meta_config`
off it. A client holding a copy of the library has entries instead, so the same question
asked on either side has to get the same answer - otherwise a filtered view on another
machine quietly disagrees with the hub about what is in it.

These run every axis and every order against both, on one library, and compare.
"""

from __future__ import annotations

import unittest

from common.games import collection_filters, collection_resolver, wire_entry
from common.games.game_metadata import game_title, table_descriptor
from httpapi.collections import _entry_resource
from tests.support.entries import entries_for
from tests.support.library import TempTree, fake_game, write_game

# Varied on every axis the filters and sorts read, so a comparison can actually
# distinguish orders rather than pass on a library where everything ties.
LIBRARY = (
    # name, manufacturer, year, type, themes, rating, created, last run, secs, plays
    ("The Addams Family (Bally 1992)", "Bally", "1992", "SS", ["Movie"],
     3, 300.0, 1700000000, 120, 3),
    ("Attack from Mars (Bally 1995)", "Bally", "1995", "SS", ["Space", "Aliens"],
     5, 100.0, 1600000000, 900, 11),
    ("Medieval Madness (Williams 1997)", "Williams", "1997", "SS", ["Fantasy"],
     4, 200.0, 1800000000, 45, 7),
    ("Space Invaders (Bally 1980)", "Bally", "1980", "EM", ["Space"],
     0, 50.0, 0, 0, 0),
)

FILTERS = (
    {"manufacturer": "Bally"},
    {"year": "1995,1997"},
    {"game_type": "EM"},
    {"theme": "Space"},
    {"rating": "5"},
    {"letter": "A,M"},
    {"rating_or_higher": "1", "rating": "3"},
    {"played": True},
    {"played": False},
    {"manufacturer": "Bally", "theme": "Space"},
    {"theme": "Nothing Is Tagged This"},
    {},
)

ORDERS = ("title", "year", "rating", "added", "play_time_seconds", "last_played",
          "play_count")


class _WireEntry:
    """A sort key reads `.game` and `.table_id`; the table id is the hub's either way."""

    def __init__(self, game, table_id: str) -> None:
        self.game = game
        self.table_id = table_id


class WireEntryTests(TempTree):
    def setUp(self) -> None:
        super().setUp()
        games = []
        for (name, manufacturer, year, kind, themes,
             rating, created, last_run, seconds, plays) in LIBRARY:
            meta = {
                "Info": {"Title": name.split(" (")[0], "Manufacturer": manufacturer,
                         "Year": year, "Type": kind, "Themes": themes},
                "User": {"Rating": rating, "LastRun": last_run, "StartCount": plays},
                "vpinfe": {"game_id": name[:10].replace(" ", ""),
                           "run_time_seconds": seconds},
            }
            game = fake_game(write_game(self.root, name, info=meta), name, meta=meta)
            game.creation_time = created
            games.append(game)

        self.entries = entries_for(games)
        self.wire = [_WireEntry(wire_entry.game_of(_entry_resource(entry)), entry.table_id)
                     for entry in self.entries]

    def test_every_axis_matches_the_same_games(self) -> None:
        """A filtered view on another machine holds what the hub says it holds."""
        for stored in FILTERS:
            with self.subTest(filter=stored):
                hub = [collection_filters.matches(stored, e.game) for e in self.entries]
                wire = [collection_filters.matches(stored, e.game) for e in self.wire]
                self.assertEqual(wire, hub)

    def test_every_axis_is_covered(self) -> None:
        """So an axis added later is not silently left untested here."""
        exercised = {name for stored in FILTERS for name in stored}

        self.assertEqual({axis.name for axis in collection_filters.AXES} - exercised, set())

    def test_every_order_sorts_the_same(self) -> None:
        """Including the three that read a play record and the one that reads a stat."""
        for order in ORDERS:
            with self.subTest(order=order):
                hub = [game_title(e.game)
                       for e in collection_resolver._ordered(list(self.entries), order)]
                wire = [game_title(e.game)
                        for e in collection_resolver._ordered(list(self.wire), order)]
                self.assertEqual(wire, hub)

    def test_each_order_reads_the_field_it_claims_to(self) -> None:
        """The comparison above would hold on a wire entry carrying none of these, by
        falling back to the title tiebreak every time. Blanking each field has to move
        the order it belongs to, which is what says the value really crossed.
        """
        moved = {"added": "creation_time", "rating": ("User", "Rating"),
                 "last_played": ("User", "LastRun"), "play_count": ("User", "StartCount"),
                 "play_time_seconds": ("vpinfe", "run_time_seconds")}
        for order, field in moved.items():
            with self.subTest(order=order):
                before = [game_title(e.game)
                          for e in collection_resolver._ordered(list(self.wire), order)]
                blanked = [_WireEntry(wire_entry.game_of(_entry_resource(e)), e.table_id)
                           for e in self.entries]
                for entry in blanked:
                    if field == "creation_time":
                        entry.game.creation_time = None
                    else:
                        entry.game.meta_config[field[0]][field[1]] = 0
                after = [game_title(e.game)
                         for e in collection_resolver._ordered(blanked, order)]

                self.assertNotEqual(after, before)

    def test_a_title_the_hub_reordered_is_not_reordered_twice(self) -> None:
        """`name` arrives already resolved. Putting it back under `Info.Title` only works
        because moving a leading article in a title that has had one moved does nothing."""
        addams = next(e.game for e in self.wire
                      if game_title(e.game).startswith("Addams"))

        self.assertEqual(game_title(addams), "Addams Family, The")

    def test_a_table_survives_the_trip_field_for_field(self) -> None:
        """The wire names a table's fields for a consumer and storage names them for the
        parser. Handing the wire dict to code that reads storage keys does not fail - it
        answers false for every detect flag and loses the game's default. So the whole
        descriptor is compared, not a sample of it."""
        original = {
            "id": "Tbl1111111", "filename": "AFM.vpx", "version": "1.2",
            "rom": "afm_113b", "file_hash": "3a77427e", "default": True, "hidden": False,
            "release_date": "1995-06-01", "authors": ["Someone"],
            "detects": {"nfozzy": True, "fleep": False, "ssf": True, "lut": False,
                        "scorbit": False, "fastflips": False, "flex": False,
                        "pinmame": True},
            "user": {"last_played": "2026-08-01T20:14:00Z", "play_count": 12,
                     "play_time_seconds": 5400},
        }

        restored = wire_entry.table_of({"table": original})
        # The default comes back off the restored table, not from an id handed in here -
        # passing one would make `default` true whatever survived the trip.
        again = table_descriptor(
            restored, default_id=restored["id"] if restored.get("default") else "")

        self.assertEqual(again, original)
        self.assertIs(restored["default"], True)

    def test_a_hidden_table_stays_hidden_after_the_trip(self) -> None:
        """`hidden` is the user's choice not to be offered a table. A player that loses it
        would offer one the hub does not."""
        restored = wire_entry.table_of({"table": {"id": "T", "hidden": True}})

        self.assertIs(restored["hidden"], True)
        self.assertIs(table_descriptor(restored)["hidden"], True)

    def test_a_table_the_hub_never_parsed_says_so(self) -> None:
        """Null rather than "" so "not parsed" stays distinct from "parsed as blank"."""
        described = table_descriptor(
            wire_entry.table_of({"table": {"id": "T", "filename": "x.vpx"}}))

        self.assertIsNone(described["release_date"])

    def test_the_vpx_company_fields_are_not_published(self) -> None:
        """Measured across 162 real tables: companyname, companyyear and playfieldvariant
        are populated in none of them. The first two would also duplicate the game's, and
        playfieldvariant is a rendering mode rather than SS/EM - publishing it as `type`
        beside the game's `type` would put two unrelated meanings behind one word."""
        described = table_descriptor({"id": "T", "manufacturer": "Bally",
                                      "year": "1995", "type": "FSS"})

        for absent in ("manufacturer", "year", "type"):
            with self.subTest(field=absent):
                self.assertNotIn(absent, described)

    def test_a_game_with_nothing_recorded_reads_as_zero(self) -> None:
        """Absent is not an error, and must not sort as newest or most played."""
        bare = wire_entry.game_of({})

        self.assertEqual(game_title(bare), "")
        self.assertIsNone(bare.creation_time)
        self.assertEqual(bare.meta_config["User"]["Rating"], 0)
        self.assertEqual(bare.meta_config["User"]["LastRun"], 0)


if __name__ == "__main__":
    unittest.main()
