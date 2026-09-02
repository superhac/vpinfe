"""What the catalog offers for a game's empty media slots.

The two vocabularies share names for different things, which is the whole of this:
`backglass` is a picture among media and a `.directb2s` among assets, and VPS lists the
second. Counted against the tile, the map would mark the picture with the count of a
file that is not a picture.
"""

from __future__ import annotations

import unittest
from unittest.mock import Mock

from hubui.data import Library

STATE = [
    {"kind": "b2sFiles", "ours": ["backglass"], "held_in": "asset",
     "held": True, "listed": 7, "obtainable": 7, "why_not": []},
    {"kind": "topperFiles", "ours": ["topper", "topper_video"], "held_in": "media",
     "held": False, "listed": 4, "obtainable": 3, "why_not": ["collection"]},
    {"kind": "povFiles", "ours": ["pov"], "held_in": "asset",
     "held": False, "listed": 2, "obtainable": 0, "why_not": ["collection"]},
    {"kind": "ruleFiles", "ours": ["rule_sheet"], "held_in": "media",
     "held": False, "listed": 2, "obtainable": 2, "why_not": []},
    {"kind": "wheelArtFiles", "ours": ["wheel"], "held_in": "media",
     "held": True, "listed": 11, "obtainable": 0, "why_not": ["collection"]},
]


class OfferedMediaTests(unittest.TestCase):
    def setUp(self) -> None:
        self.library = Library.__new__(Library)
        self.library._client = Mock(vps_state=Mock(return_value=STATE))

    def test_only_media_kinds_reach_the_map(self) -> None:
        """An asset kind sharing a media kind's name would mark the wrong tile."""
        offered = self.library.offered_media("g1")

        self.assertNotIn("backglass", offered)
        self.assertNotIn("pov", offered)

    def test_one_of_theirs_marks_both_of_ours(self) -> None:
        offered = self.library.offered_media("g1")

        self.assertEqual(offered["topper"], 3)
        self.assertEqual(offered["topper_video"], 3)

    def test_a_kind_the_catalog_only_has_as_a_folder_offers_nothing(self) -> None:
        """Eleven records and none of them a file. Marking a slot from `listed` would
        send somebody to a folder to rummage in and call it a download."""
        self.assertEqual(self.library.offered_media("g1")["wheel"], 0)

    def test_the_count_is_files_not_records(self) -> None:
        offered = self.library.offered_media("g1")

        self.assertEqual(offered["rule_sheet"], 2)


if __name__ == "__main__":
    unittest.main()
