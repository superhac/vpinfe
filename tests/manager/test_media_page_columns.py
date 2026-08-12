"""The Media page's columns read fields that its rows actually carry.

The column list was written out by hand, and at the vocabulary rename five of its fields
stopped matching the keys the media scan produces - `has_table` against a row holding
`has_playfield`, and the same for FSS, both Real DMD kinds and Table Video. Such a column
renders empty for every game, which reads as missing media rather than a broken binding.
"""

from __future__ import annotations

import unittest

from common.games.media_service import MEDIA_TYPES
from managerui.pages.media import COLUMN_ORDER


def scanned_row_fields() -> set[str]:
    """The `has_*` keys `scan_media_games` puts on every row."""
    return {f"has_{key}" for key, _, _ in MEDIA_TYPES}


class MediaPageColumnTests(unittest.TestCase):
    def test_every_column_field_exists_on_a_scanned_row(self) -> None:
        available = scanned_row_fields()
        missing = sorted(f"has_{key}" for key in COLUMN_ORDER
                         if f"has_{key}" not in available)
        self.assertEqual(missing, [], f"columns bound to fields no row carries: {missing}")

    def test_column_order_covers_the_media_kinds_exactly(self) -> None:
        """A new kind has to be placed deliberately, not dropped by omission."""
        self.assertEqual(sorted(COLUMN_ORDER), sorted(key for key, _, _ in MEDIA_TYPES))

    def test_the_renamed_kinds_are_the_canonical_ones(self) -> None:
        """The five that broke: the page must use the media key, not the old UI name."""
        for key in ("playfield", "playfield_fss", "real_dmd",
                    "real_dmd_color", "playfield_video"):
            self.assertIn(key, COLUMN_ORDER)
        for stale in ("table", "fss", "realdmd", "realdmd_color", "game_video"):
            self.assertNotIn(stale, COLUMN_ORDER)
