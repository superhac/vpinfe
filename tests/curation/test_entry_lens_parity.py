"""The play lens answers the same thing over REST as it does to a theme.

`GET /collections/{name}/entries` was built as the play lens - "what a frontend would
show and the order it would show it in" - with the theme payload described as the same
resolution serialized differently. They resolved identically from the start; what they
did not do was *say* the same amount, so a frontend on another machine could not have
been built from the REST answer.

These assert the two serializations agree, and name every field where they deliberately
do not.
"""

from __future__ import annotations

import json
import unittest

from common.games import collection_resolver
from frontend import game_state
from httpapi.collections import _entry_resource
from tests.support.library import TempTree, fake_game, write_game

# Local filesystem paths. True only of the machine that answered, and the wire is read
# by machines that did not - so the theme payload keeps them and REST does not.
THEME_ONLY = {"game": {"path"}, "table": {"path"}, "top": set()}

# REST concerns. `rating` is also flat here because it shipped that way before it moved
# into `user`; `links` is a REST affordance a theme has no use for. `default` used to be
# here - a theme that lists a game's tables has to know which one the game defaults to,
# and deriving it a second way is how the two lenses would come to disagree.
WIRE_ONLY = {"game": {"rating"}, "table": set(), "top": {"links"}}

META = {
    "Info": {"Name": "Attack from Mars", "Title": "Attack from Mars",
             "Manufacturer": "Bally", "Year": "1995", "Type": "SS",
             "Themes": ["Space", "Aliens"], "VPSId": "vps-1"},
    "User": {"Rating": 4, "Favorite": 1, "StartCount": 7, "RunTime": 12},
    "vpinfe": {"game_id": "Aaaa111111"},
}


class EntryLensParityTests(TempTree):
    def setUp(self) -> None:
        super().setUp()
        folder = write_game(self.root, "Attack from Mars (Bally 1995)", info=META)
        game = fake_game(folder, "Attack from Mars (Bally 1995)", meta=META)
        for attribute in ("pupPackExists", "altColorExists", "altSoundExists"):
            setattr(game, attribute, False)
        self.entries = collection_resolver.entries_for([game])
        self.theme = json.loads(
            game_state.games_json(self.entries, contract=2))["entries"][0]
        self.wire = _entry_resource(self.entries[0])

    def test_the_two_lenses_carry_the_same_fields(self) -> None:
        """Every difference is one of the four listed above. A new field on either side
        that is not deliberate shows up here rather than as a remote frontend that
        renders half a wheel."""
        for half in ("game", "table"):
            with self.subTest(half=half):
                theme, wire = set(self.theme[half]), set(self.wire[half])
                self.assertEqual(theme - wire, THEME_ONLY[half])
                self.assertEqual(wire - theme, WIRE_ONLY[half])

        self.assertEqual(set(self.theme) - set(self.wire), THEME_ONLY["top"])
        self.assertEqual(set(self.wire) - set(self.theme), WIRE_ONLY["top"])

    def test_the_shared_fields_carry_the_same_values(self) -> None:
        """Agreeing on names and disagreeing on answers would be worse than either."""
        for half in ("game", "table"):
            shared = set(self.theme[half]) & set(self.wire[half])
            for field in sorted(shared):
                with self.subTest(field=f"{half}.{field}"):
                    self.assertEqual(self.theme[half][field], self.wire[half][field])

        for field in sorted(set(self.theme) & set(self.wire) - {"game", "table"}):
            with self.subTest(field=field):
                self.assertEqual(self.theme[field], self.wire[field])

    def test_no_filesystem_path_reaches_the_wire(self) -> None:
        """The one thing that cannot travel: it is true of one machine only."""
        serialized = json.dumps(self.wire)

        self.assertNotIn(str(self.root), serialized)
        self.assertNotIn("path", self.wire["game"])
        self.assertNotIn("path", self.wire["table"])

    def test_the_play_record_survives_the_trip(self) -> None:
        """It is what goes stale first, so it is what a remote frontend most needs."""
        self.assertEqual(self.wire["game"]["user"]["rating"], 4)
        self.assertTrue(self.wire["game"]["user"]["favorite"])
        self.assertEqual(self.wire["game"]["user"]["play_count"], 7)
        self.assertEqual(self.wire["game"]["rating"], 4,
                         "the flat field still answers for clients that read it")

    def test_the_wire_can_reproduce_the_newest_order(self) -> None:
        """The "Newest" sort is a stat of the hub's filesystem, so a client sorting its
        own copy has to be told rather than look. Newest-first off the wire answer has
        to land in the same order the hub resolves.
        """
        folders = [("Medieval Madness (Williams 1997)", 300.0),
                   ("Attack from Mars (Bally 1995)", 100.0),
                   ("Twilight Zone (Bally 1993)", 200.0)]
        games = []
        for name, created in folders:
            meta = {**META, "Info": {**META["Info"], "Title": name.split(" (")[0]}}
            game = fake_game(write_game(self.root, name, info=meta), name, meta=meta)
            game.creation_time = created
            games.append(game)

        entries = collection_resolver.entries_for(games)
        hub_order = [game_state.game_title(e.game) for e in
                     sorted(entries, key=collection_resolver._sort_key("added"))]
        wire = [_entry_resource(e) for e in entries]
        stamps = [row["game"]["created_at"] for row in wire]
        client_order = [game_state.game_title(e.game) for _, e in sorted(
            zip(stamps, entries, strict=True), key=lambda pair: pair[0],
            reverse=True)]

        self.assertEqual(client_order, hub_order)
        self.assertEqual(client_order, ["Medieval Madness", "Twilight Zone",
                                        "Attack from Mars"])
        # Three distinct stamps, so the order above is the timestamps deciding it. Drop
        # `created_at` from the wire and they collapse to one value and this fails.
        self.assertEqual(len(set(stamps)), 3)

    def test_media_is_named_not_located(self) -> None:
        """Kinds, so the bytes can be fetched from wherever the assets are served."""
        self.assertIsInstance(self.wire["media"], list)
        self.assertEqual(self.wire["media"], self.theme["media"])


if __name__ == "__main__":
    unittest.main()
