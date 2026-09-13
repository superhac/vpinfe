"""The Media page's columns read fields that its rows actually carry, and only those.

The column list was written out by hand, and at the vocabulary rename five of its fields
stopped matching the kinds the media scan produces - `has_table` against a row holding
`has_playfield`, and the same for FSS, both Real DMD kinds and Table Video. Such a column
renders empty for every game, which reads as missing media rather than a broken binding.

The labels now come from the registry, which holds every kind VPinFE resolves rather than
the thirteen this page shows. So the set of columns is pinned here: adding one changes what
every user sees, and it should cost an edit to this file.
"""

from __future__ import annotations

import unittest

from common.media_specs import MEDIA_SPECS
from managerui.pages.media import COLUMN_ORDER

# What the Media page has always shown, in no particular order.
PAGE_KINDS = {
    "backglass", "scoreview", "playfield", "playfield_fss", "wheel", "cab", "flyer",
    "real_dmd", "real_dmd_color", "playfield_video", "backglass_video",
    "scoreview_video", "audio",
}


def scanned_row_fields() -> set[str]:
    """The `has_*` keys `scan_media_games` puts on every row."""
    return {f"has_{spec.kind}" for spec in MEDIA_SPECS}


class MediaPageColumnTests(unittest.TestCase):
    def test_every_column_field_exists_on_a_scanned_row(self) -> None:
        available = scanned_row_fields()
        missing = sorted(f"has_{kind}" for kind in COLUMN_ORDER
                         if f"has_{kind}" not in available)
        self.assertEqual(missing, [], f"columns bound to fields no row carries: {missing}")

    def test_the_page_shows_exactly_the_kinds_it_has_always_shown(self) -> None:
        """Deriving the labels from the registry must not put seven new columns on screen."""
        self.assertEqual(sorted(COLUMN_ORDER), sorted(PAGE_KINDS))
        self.assertEqual(len(COLUMN_ORDER), len(set(COLUMN_ORDER)), "a column is listed twice")

    def test_the_registry_holds_kinds_the_page_leaves_out(self) -> None:
        """Guards the test above: if the registry ever shrank to the page's set, that
        assertion would pass while saying nothing."""
        left_out = {spec.kind for spec in MEDIA_SPECS} - PAGE_KINDS
        self.assertEqual(
            sorted(left_out),
            ["audio_launch", "instruction_card", "loading", "logo", "rule_sheet",
             "topper", "topper_video"])

    def test_the_renamed_kinds_are_the_canonical_ones(self) -> None:
        """The five that broke: the page must use the media kind, not the old UI name."""
        for kind in ("playfield", "playfield_fss", "real_dmd",
                     "real_dmd_color", "playfield_video"):
            self.assertIn(kind, COLUMN_ORDER)
        for stale in ("table", "fss", "realdmd", "realdmd_color", "game_video"):
            self.assertNotIn(stale, COLUMN_ORDER)


if __name__ == "__main__":
    unittest.main()
