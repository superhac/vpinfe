"""What VPinPlay is told about a library, built from what core hands over.

The version this replaces enumerated the library itself - the online client reaching
down into games, which the architecture notes named as the wrong direction. An extension
has no such reach and does not need one, so what is pinned here is that the same payload
comes out of the records the context already provides.

Every key below is the service's. Their models reject nothing they do not recognize, so
a name that drifts is dropped in silence rather than refused - which is why these are
asserted by name rather than by shape.
"""

from __future__ import annotations

import unittest

from common.extensions import host

host.Registry().load(host.BUNDLED_DIR / "vpinplay")

from vpinfe_ext_vpinplay import sync  # noqa: E402

GAME = {
    "vps_id": "abcd1234",
    "rom": "afm_113b",
    "manufacturer": "Bally",
    "year": "1995",
    "type": "SS",
    "user": {"rating": 4, "last_played": 1670739887, "play_count": 33,
             "play_time_seconds": 9191,
             # A reading off the hardware, which is a mapping of fields rather than one
             # number - a machine reports several and which is "the" score is its own.
             "score": {"player1": 1234, "grandChampion": 9999}},
    "overrides": {"alt_title": "AFM", "alt_vps_id": "other"},
}
TABLE = {
    "filename": "Attack from Mars.vpx",
    "file_hash": "aaa", "vbs_hash": "bbb", "version": "1.2",
    "release_date": "2020-01-01", "save_date": "2021-02-03", "save_rev": "7",
    "features": {"nfozzy": True, "fleep": False, "ssf": True, "lut": None,
                 "scorbit": True, "fastflips": False, "flexdmd": None},
}


class PayloadTests(unittest.TestCase):
    def test_it_carries_what_the_service_keys_on(self) -> None:
        found = sync.payload_for(GAME, TABLE)

        self.assertEqual(found["info"], {"vpsId": "abcd1234", "rom": "afm_113b"})

    def test_a_game_no_catalog_matched_is_skipped(self) -> None:
        """The service files by catalog id, so a game without one describes nothing it
        can put anywhere."""
        self.assertIsNone(sync.payload_for({**GAME, "vps_id": ""}, TABLE))

    def test_run_time_is_sent_in_their_units(self) -> None:
        """We keep seconds; they take minutes."""
        self.assertEqual(sync.payload_for(GAME, TABLE)["user"]["runTime"], 153)

    def test_a_rating_outside_their_bound_is_clamped(self) -> None:
        """One game outside it fails the whole request, not that game - so a rating
        nobody meant is not worth losing a sync over."""
        wild = {**GAME, "user": {**GAME["user"], "rating": 99}}

        self.assertEqual(sync.payload_for(wild, TABLE)["user"]["rating"], 5)

    def test_the_dates_a_catalog_tells_builds_apart_by(self) -> None:
        """A mod saved today can be a release from years ago."""
        found = sync.payload_for(GAME, TABLE)["vpxFile"]

        self.assertEqual(found["releaseDate"], "2020-01-01")
        self.assertEqual(found["saveDate"], "2021-02-03")
        self.assertEqual(found["saveRev"], "7")

    def test_their_spelling_of_the_features_is_used(self) -> None:
        """Scorbit is the product; the service spells its field Scorebit. A name that
        drifts is dropped in silence by their models rather than refused."""
        found = sync.payload_for(GAME, TABLE)["vpxFile"]

        self.assertTrue(found["detectScorebit"])
        self.assertTrue(found["detectNfozzy"])
        self.assertFalse(found["detectFleep"])

    def test_a_feature_nobody_parsed_is_sent_as_no(self) -> None:
        """Ours is three-valued; theirs is a boolean. Null has to become something and
        false is the only honest choice - claiming a feature nobody looked for is worse
        than under-reporting it."""
        found = sync.payload_for(GAME, TABLE)["vpxFile"]

        self.assertIs(found["detectLUT"], False)
        self.assertIs(found["detectFlex"], False)

    def test_a_game_with_no_table_still_describes_itself(self) -> None:
        """A keyed entry, or one whose file never came across."""
        found = sync.payload_for(GAME, None)

        self.assertEqual(found["info"]["vpsId"], "abcd1234")
        self.assertEqual(found["vpxFile"]["filename"], "")


    def test_only_a_reading_off_the_hardware_counts_as_a_score(self) -> None:
        """A machine that writes its display rather than its values gives a string, and
        sending that describes nothing their models can file."""
        said = {**GAME, "user": {**GAME["user"], "score": "not-a-reading"}}

        self.assertIsNone(sync.payload_for(said, TABLE)["user"]["score"])
        self.assertEqual(sync.payload_for(GAME, TABLE)["user"]["score"],
                         {"player1": 1234, "grandChampion": 9999})


class EnvelopeTests(unittest.TestCase):
    def test_it_says_which_program_is_speaking(self) -> None:
        found = sync.envelope("u", "CB", "m1", [], "3.0.0", "2026-09-11T00:00:00Z")

        self.assertEqual(found["source"], {"program": "VPinFE",
                                           "programVersion": "3.0.0"})
        self.assertEqual(found["client"]["initials"], "CB")


if __name__ == "__main__":
    unittest.main()
