"""Guides: what the catalog offers, what a 2.x file carries in, what a theme still reads."""

from __future__ import annotations

import unittest

from common.games.game_metadata import contract_1_tutorial, vps_details_differ
from common.games.info_file import GUIDES_KEY, PINBALL_PRIMER_PREFIX, guides_from_vps
from common.games.info_migration import migrate


def _entry(*tutorials: dict) -> dict:
    return {"id": "abc", "name": "Example", "tutorialFiles": list(tutorials)}


class FromTheCatalog(unittest.TestCase):
    def test_a_nested_urls_list_is_one_guide_each(self) -> None:
        found = guides_from_vps(_entry(
            {"title": "Two", "urls": [{"url": "https://a/"}, {"url": "https://b/"}]}))
        self.assertEqual(["https://a/", "https://b/"], [one["url"] for one in found])

    def test_a_record_with_only_a_video_is_kept(self) -> None:
        found = guides_from_vps(_entry({"title": "V", "url": None, "youtubeId": "xyz"}))
        self.assertEqual([("", "xyz")],
                         [(one["url"], one["youtube_id"]) for one in found])

    def test_a_record_naming_nothing_is_dropped(self) -> None:
        self.assertEqual([], guides_from_vps(_entry({"title": "Nothing"})))

    def test_authors_survive(self) -> None:
        found = guides_from_vps(_entry(
            {"title": "T", "url": "https://a/", "authors": ["Kongedam", "Odradek"]}))
        self.assertEqual(["Kongedam", "Odradek"], found[0]["authors"])

    def test_nothing_at_all_is_not_an_error(self) -> None:
        self.assertEqual([], guides_from_vps(None))
        self.assertEqual([], guides_from_vps({}))


class FromA2xFile(unittest.TestCase):
    def test_the_old_key_becomes_a_guide(self) -> None:
        out = migrate({"Info": {"PinballPrimerTut": "https://pinballprimer.github.io/x"},
                       "VPinFE": {"altvpsid": "1"}})
        self.assertNotIn("PinballPrimerTut", out["Info"])
        self.assertEqual([("tutorial", "https://pinballprimer.github.io/x")],
                         [(one["kind"], one["url"]) for one in out[GUIDES_KEY]])

    def test_running_it_twice_adds_nothing(self) -> None:
        once = migrate({"Info": {"PinballPrimerTut": "https://pinballprimer.github.io/x"},
                        "VPinFE": {"altvpsid": "1"}})
        self.assertEqual(once[GUIDES_KEY], migrate(once)[GUIDES_KEY])

    def test_a_file_with_no_tutorial_grows_no_block(self) -> None:
        self.assertNotIn(GUIDES_KEY, migrate({"Info": {}, "VPinFE": {"altvpsid": "1"}}))


class WhatAThemeReads(unittest.TestCase):
    """`entry.tutorial` is proxied by the frontend, and that proxy allows one host."""

    def test_the_primer_guide_is_the_contract_1_value(self) -> None:
        config = {GUIDES_KEY: [
            {"kind": "tutorial", "url": "https://www.youtube.com/watch?v=a"},
            {"kind": "tutorial", "url": PINBALL_PRIMER_PREFIX + "x.html"}]}
        self.assertEqual(PINBALL_PRIMER_PREFIX + "x.html", contract_1_tutorial(config))

    def test_a_guide_the_proxy_would_refuse_is_not_offered(self) -> None:
        config = {GUIDES_KEY: [
            {"kind": "tutorial", "url": "https://vpuniverse.com/files/file/1"},
            {"kind": "tutorial", "url": "", "youtube_id": "xyz"}]}
        self.assertEqual("", contract_1_tutorial(config))

    def test_no_guides_is_an_empty_string_not_a_failure(self) -> None:
        self.assertEqual("", contract_1_tutorial({}))
        self.assertEqual("", contract_1_tutorial({GUIDES_KEY: []}))


class RefreshedLikeEveryOtherCatalogFact(unittest.TestCase):
    def test_a_changed_catalog_is_reported_as_a_difference(self) -> None:
        config = {"Info": {"Title": "Example"},
                  GUIDES_KEY: [{"kind": "tutorial", "title": "Old", "authors": [],
                                "url": "https://a/", "youtube_id": ""}]}
        found = vps_details_differ(config, _entry({"title": "New", "url": "https://b/"}))
        self.assertIn("guides", found)
        self.assertEqual(["https://b/"], [one["url"] for one in found["guides"][1]])

    def test_an_unchanged_catalog_reports_nothing(self) -> None:
        entry = _entry({"title": "T", "url": "https://a/"})
        config = {"Info": {"Title": "Example"}, GUIDES_KEY: guides_from_vps(entry)}
        self.assertNotIn("guides", vps_details_differ(config, entry))

    def test_a_record_that_has_none_yet_is_a_gap_being_filled(self) -> None:
        found = vps_details_differ({"Info": {"Title": "Example"}},
                                   _entry({"title": "T", "url": "https://a/"}))
        self.assertTrue(found["guides"][2])



class WhatTheDifferSays(unittest.TestCase):
    def test_guides_read_as_a_count_not_a_record(self) -> None:
        from common.games.game_ops import _said
        from common.i18n import t

        guides = [{"kind": "tutorial", "title": "A", "url": "https://a/"},
                  {"kind": "tutorial", "title": "B", "url": "https://b/"}]
        said = _said(guides, "guides")
        self.assertEqual(t("said.guides", count=2), said)
        self.assertNotIn("{", said)

    def test_no_guides_reads_as_nothing(self) -> None:
        from common.games.game_ops import _said

        self.assertEqual("", _said([], "guides"))

class OnTheWire(unittest.TestCase):
    def test_each_guide_says_where_it_lives(self) -> None:
        from common.games.game_metadata import guides_on_wire

        config = {GUIDES_KEY: [
            {"kind": "tutorial", "url": PINBALL_PRIMER_PREFIX + "x.html"},
            {"kind": "tutorial", "url": "", "youtube_id": "abc"},
            {"kind": "tutorial", "url": "https://example.org/rules"}]}
        self.assertEqual(["Pinball Primer", "YouTube", "example.org"],
                         [one["source"] for one in guides_on_wire(config)])

    def test_no_guides_is_an_empty_list(self) -> None:
        from common.games.game_metadata import guides_on_wire

        self.assertEqual([], guides_on_wire({}))


if __name__ == "__main__":
    unittest.main()
