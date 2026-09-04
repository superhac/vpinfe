"""Naming the VPS record a file is bound to, in the panel.

The id is what gets stored and it is not something to put on screen, so the panel
resolves it against the catalog it already has open. What this covers is the three
answers that resolution has, because two of them look like nothing going wrong.
"""

import unittest
from unittest.mock import Mock

from common.online import vps_kinds
from console import workbench

RECORD = "wheel_KtY1"

# Wheel art, not a backglass: `backglass` is a picture among media and a .directb2s
# among assets, so it is the one media kind name that must not reach a VPS listing.
WHEELS = [
    {"vps_file_id": RECORD, "version": "3.0", "authors": ["wildman", "hauntfreaks"]},
    {"vps_file_id": "wheel_Other", "version": "1.1", "authors": []},
]


def _context(releases=None, vps_id="mm_1997x"):
    library = Mock()
    library.vps_releases = Mock(
        return_value=list(WHEELS if releases is None else releases))
    return {"library": library, "game": {"vps_id": vps_id}, "game_id": "g1"}


class MatchLineTests(unittest.TestCase):
    def test_a_bound_file_is_named_by_what_a_person_can_compare(self) -> None:
        line = workbench._match_line(_context(), "wheel", RECORD)

        self.assertEqual(line, "Matched to 3.0 · wildman, hauntfreaks")

    def test_nothing_is_said_when_nobody_has_said_anything(self) -> None:
        """Absent is the ordinary state - almost every file is unbound, so a line here
        would be on nearly every slot and tell nobody anything."""
        self.assertEqual(workbench._match_line(_context(), "wheel", None), "")

    def test_a_record_the_catalog_dropped_still_says_so(self) -> None:
        """Silence here would read as unbound, and the difference matters: no update
        can ever be reported for a file bound to something no longer listed."""
        line = workbench._match_line(_context(releases=[]), "wheel", RECORD)

        self.assertEqual(line, "Matched to a file the catalog no longer lists")

    def test_a_kind_vps_does_not_publish_says_nothing(self) -> None:
        line = workbench._match_line(_context(), "playfield", RECORD)

        self.assertEqual(line, "")

    def test_the_backglass_picture_is_not_offered_the_backglass_asset(self) -> None:
        """The two vocabularies share the word. `backglass` is a picture among media
        and a .directb2s among assets, and VPS lists the second - so matching a media
        slot by name alone offered it the assets that view is explicitly not about."""
        self.assertIsNone(workbench._listed_as("backglass", vps_kinds.MEDIA))
        self.assertIsNotNone(workbench._listed_as("backglass", vps_kinds.ASSET))

    def test_the_media_kinds_vps_does_list_still_match(self) -> None:
        for kind in ("wheel", "topper", "rule_sheet"):
            with self.subTest(kind=kind):
                self.assertIsNotNone(workbench._listed_as(kind, vps_kinds.MEDIA))

    def test_the_records_asked_for_are_that_kind_s(self) -> None:
        """One entry answers a different list per kind, and the local kind is not the
        name to ask by - `topper` and `topper_video` are one list upstream."""
        context = _context()
        workbench._match_line(context, "topper", RECORD)

        context["library"].vps_releases.assert_called_once_with(
            "mm_1997x", "topperFiles")


class KindMapTests(unittest.TestCase):
    def test_every_local_kind_maps_back_to_the_listing_that_holds_it(self) -> None:
        for listing in vps_kinds.KINDS:
            for ours in listing.ours:
                with self.subTest(kind=ours):
                    self.assertIs(vps_kinds.BY_OURS[ours], listing)

    def test_two_of_ours_share_one_of_theirs(self) -> None:
        """The reason the map is needed at all: a local kind cannot address VPS."""
        self.assertIs(vps_kinds.BY_OURS["altcolor_serum"],
                      vps_kinds.BY_OURS["altcolor_vni"])


if __name__ == "__main__":
    unittest.main()
