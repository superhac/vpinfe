"""What VPinPlay is told about a library, built from what core hands over.

The version this replaces enumerated the library itself - the online client reaching
down into games, which the architecture notes named as the wrong direction. An extension
has no such reach and does not need one, so what is pinned here is that the same payload
comes out of the records the context already provides.

Every key below is the service's, asserted by name: a key they require that goes missing
refuses the whole request, and one they do not know is dropped in silence.
"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from common.extensions import host

host.Registry().load(host.BUNDLED_DIR / "vpinplay")

import vpinfe_ext_vpinplay  # noqa: E402
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


class LibraryScoreTests(unittest.TestCase):
    """Core publishes a machine's high score table as `high_scores`; the service files
    the reading shape the score parser gives."""

    HIGH_SCORES = {"rom": "afm_113b", "table_id": "t1", "read_at": "2026-09-27T12:00:00Z",
                   "state": "read", "reason": "", "sections": [
                       {"name": "GRAND CHAMPION", "entries": [
                           {"rank": None, "initials": "ABC", "score": 9999, "prefix": "",
                            "suffix": "", "text": "9,999", "new": False}]},
                       {"name": "MARTIAN CHAMPION", "entries": [
                           {"rank": None, "initials": "", "score": 20, "prefix": "",
                            "suffix": " MARTIANS", "text": "20 MARTIANS", "new": True}]},
                       {"name": "RULER", "entries": [
                           {"rank": 1, "initials": "OWN", "score": None, "prefix": "",
                            "suffix": "", "text": "INAUGURATED\n5 JAN, 2024", "new": False}]}]}

    def test_the_table_is_sent_as_a_reading_blanks_blank(self) -> None:
        game = {**GAME, "user": {**GAME["user"], "high_scores": self.HIGH_SCORES}}
        del game["user"]["score"]

        sent = sync.payload_for(sync.from_library(game), TABLE)["user"]["score"]

        self.assertEqual(sent["rom"], "afm_113b")
        self.assertEqual([(one["section"], one["initials"], one["score"])
                          for one in sent["entries"]],
                         [("GRAND CHAMPION", "ABC", 9999), ("MARTIAN CHAMPION", "", 20),
                          ("RULER", "OWN", None)])
        self.assertEqual(sent["entries"][1]["value_suffix"], "MARTIANS")
        self.assertEqual(sent["entries"][2]["extra_lines"], ["INAUGURATED", "5 JAN, 2024"])

    def test_nothing_read_is_no_score(self) -> None:
        game = {**GAME, "user": {**GAME["user"], "high_scores": None}}

        self.assertIsNone(sync.payload_for(sync.from_library(game), TABLE)["user"]["score"])


class EnvelopeTests(unittest.TestCase):
    def test_it_says_which_program_is_speaking(self) -> None:
        found = sync.envelope("u", "JD", "m1", [], "3.0.0", "2026-09-11T00:00:00Z")

        self.assertEqual(found["source"], {"program": "VPinFE",
                                           "programVersion": "3.0.0"})
        self.assertEqual(found["client"]["initials"], "JD")


class WireTests(unittest.TestCase):
    """What VPinPlay's request models require. Every other field in them is optional."""

    def setUp(self) -> None:
        self.sent = sync.envelope("u", "JD", "m" * 64, [sync.payload_for(GAME, TABLE)],
                                  "3.0.0", "2026-09-11T00:00:00Z")

    def assert_carries(self, found: dict, required: set[str]) -> None:
        self.assertLessEqual(required, set(found),
                             f"missing {sorted(required - set(found))}")

    def test_the_request_carries_what_they_require(self) -> None:
        self.assert_carries(self.sent, {"source", "client", "sentAt", "tables"})
        self.assert_carries(self.sent["source"], {"program", "programVersion"})
        self.assert_carries(self.sent["client"], {"userId", "initials", "machineId"})

    def test_each_game_carries_what_they_require(self) -> None:
        for game in (sync.payload_for(GAME, TABLE), sync.payload_for(GAME, None)):
            self.assert_carries(game, {"info", "user", "vpxFile", "vpinfe"})
            self.assert_carries(game["info"], {"vpsId"})
            self.assert_carries(game["vpxFile"],
                                {"filename", "filehash", "version", "vbsHash", "rom"})

    def test_the_machine_id_minted_here_is_the_length_they_take(self) -> None:
        self.assertEqual(len(vpinfe_ext_vpinplay._new_machine_id()), 64)


class SendTests(unittest.TestCase):
    def answer(self, status_code: int, body: dict) -> MagicMock:
        response = MagicMock(status_code=status_code, ok=200 <= status_code < 400,
                             text=str(body))
        response.json.return_value = body
        return response

    def test_a_refusal_with_a_200_is_not_ok(self) -> None:
        refused = self.answer(200, {"status": "error", "summary": {"errors": 1}})

        with patch.object(sync.requests, "post", return_value=refused):
            found = sync.send("http://vpinplay.test/api/v1/sync", {}, 1)

        self.assertFalse(found["ok"])

    def test_an_accepted_sync_is_ok(self) -> None:
        accepted = self.answer(200, {"status": "ok", "summary": {"errors": 0}})

        with patch.object(sync.requests, "post", return_value=accepted):
            found = sync.send("http://vpinplay.test/api/v1/sync", {}, 1)

        self.assertTrue(found["ok"])


PLAYED = {"Rating": 0, "LastRun": 1790422278, "StartCount": 1, "run_time_seconds": 1800,
          "Score": {"rom": "afm_113b", "entries": [
              {"initials": "ABC", "score": 5000}, {"initials": "OWN", "score": 9000}]}}


class GuestPayloadTests(unittest.TestCase):
    def test_their_rating_and_titles_are_kept(self) -> None:
        held = {"rating": 4, "alttitle": "Theirs", "altvpsid": "theirs-id"}

        found = sync.payload_for_guest(GAME, TABLE, PLAYED, held, "ABC")

        self.assertEqual(found["user"]["rating"], 4)
        self.assertEqual(found["vpinfe"], {"alttitle": "Theirs", "altvpsid": "theirs-id"})

    def test_nothing_of_this_librarys_record_goes_with_it(self) -> None:
        found = sync.payload_for_guest(GAME, TABLE, PLAYED, {}, "ABC")

        self.assertEqual(found["user"]["startCount"], 1)
        self.assertEqual(found["user"]["runTime"], 30)
        self.assertEqual(found["user"]["rating"], 0)
        self.assertEqual(found["vpinfe"], {"alttitle": "", "altvpsid": ""})

    def test_the_machines_table_goes_when_it_holds_their_entry(self) -> None:
        found = sync.payload_for_guest(GAME, TABLE, PLAYED, {}, "abc")

        self.assertEqual(found["user"]["score"], PLAYED["Score"])

    def test_their_score_is_kept_when_the_table_holds_none_of_theirs(self) -> None:
        held = {"score": {"rom": "afm_113b", "entries": [{"initials": "XYZ", "score": 1}]}}

        found = sync.payload_for_guest(GAME, TABLE, PLAYED, held, "XYZ")

        self.assertEqual(found["user"]["score"], held["score"])

    def test_a_reading_that_is_one_number_is_theirs(self) -> None:
        played = {**PLAYED, "Score": {"rom": "x", "value": 1234}}

        found = sync.payload_for_guest(GAME, TABLE, played, {}, "ABC")

        self.assertEqual(found["user"]["score"], {"rom": "x", "value": 1234})


class TheirRecordTests(unittest.TestCase):
    WHERE = "https://vpinplay.test/api/v1/sync"

    def ask(self, **answer: object) -> tuple[object, MagicMock]:
        with patch.object(sync.requests, "get", **answer) as get:
            found = sync.their_record(self.WHERE, "some one", "abcd1234", 1)
        return found, get

    def test_it_asks_for_that_user_and_table(self) -> None:
        found, get = self.ask(return_value=MagicMock(status_code=200, ok=True,
                                                     json=lambda: {"rating": 3}))

        self.assertEqual(found, {"rating": 3})
        self.assertEqual(get.call_args.args[0],
                         "https://vpinplay.test/api/v1/users/some%20one/tables/abcd1234")

    def test_a_record_they_do_not_hold_is_empty(self) -> None:
        found, _get = self.ask(return_value=MagicMock(status_code=404, ok=False))

        self.assertEqual(found, {})

    def test_a_server_that_cannot_answer_is_not_read_as_empty(self) -> None:
        down, _get = self.ask(side_effect=sync.requests.ConnectionError("down"))
        failing, _get = self.ask(return_value=MagicMock(status_code=500, ok=False))

        self.assertIsNone(down)
        self.assertIsNone(failing)


if __name__ == "__main__":
    unittest.main()
