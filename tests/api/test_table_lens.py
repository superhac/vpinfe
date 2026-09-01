"""The library seen by launchable file, and the things you can do to one.

A game's row cannot tell its tables apart, which is what this lens is for. What is
asserted here is that a table can be identified without its filename - by version and
author, which come out of the .vpx itself - and that the two acts that are not deleting
it, choosing the default and taking it out of play, do what they say.
"""

from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from starlette.testclient import TestClient

import httpapi
from tests.support.library import TempTree, fake_game, write_game

GAME_ID = "Lens00000001"
FOLDER = "Cactus Canyon (Bally 1998)"
DESKTOP = f"{FOLDER}.vpx"
VR = f"{FOLDER} - VR.vpx"

INFO = {
    "Info": {"Name": "Cactus Canyon", "Manufacturer": "Bally", "Year": "1998"},
    "VPinFE": {"game_id": GAME_ID},
    "tables": {
        "tbl0000001": {"id": "tbl0000001", "filename": DESKTOP,
                       "version": "1.0", "authors": ["someone"]},
        "tbl0000002": {"id": "tbl0000002", "filename": VR,
                       "version": "2.1", "authors": ["someone else"]},
    },
}


class _Lens(TempTree):
    def setUp(self) -> None:
        super().setUp()
        self.folder = write_game(self.root, FOLDER, info=INFO, vpx=False,
                                 files={DESKTOP: b"vpx", VR: b"vpx"})
        game = fake_game(self.folder, FOLDER, meta=INFO)
        patcher = patch("httpapi.games._catalog", return_value={GAME_ID: game})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.client = TestClient(httpapi.create_api_app(), raise_server_exceptions=False)

    def _rows(self):
        response = self.client.get("/tables")
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()["tables"]

    def _info(self) -> dict:
        return json.loads((self.folder / f"{FOLDER}.info").read_text(encoding="utf-8"))


class TableLensTests(_Lens):
    def test_one_row_per_file_not_one_per_folder(self) -> None:
        """The whole point: two tables of one game are two rows, not one."""
        self.assertEqual(len(self._rows()), 2)

    def test_a_row_carries_its_game_so_it_reads_on_its_own(self) -> None:
        for row in self._rows():
            self.assertEqual(row["game"], "Cactus Canyon")
            self.assertEqual(row["game_id"], GAME_ID)

    def test_a_table_is_identified_without_its_filename(self) -> None:
        """Filenames of one game share forty characters and differ in two. Version and
        author come out of the .vpx and are what tell them apart."""
        by_version = {row["version"]: row["authors"] for row in self._rows()}
        self.assertEqual(by_version, {"1.0": ["someone"], "2.1": ["someone else"]})

    def test_the_apps_that_play_a_table_are_listed(self) -> None:
        body = self.client.get("/tables/apps").json()
        self.assertEqual([app["id"] for app in body["apps"]], ["vpx"])
        self.assertIn(".vpx", body["apps"][0]["suffixes"])

    def test_every_table_says_which_app_plays_it(self) -> None:
        self.assertEqual({row["app"] for row in self._rows()}, {"vpx"})


class DefaultTests(_Lens):
    def test_choosing_a_default_records_the_id_not_the_name(self) -> None:
        """Stored as an id so the choice survives a rename of the file."""
        response = self.client.put(f"/games/{GAME_ID}/default_table",
                                   json={"table": "tbl0000002"})

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(self._info()["vpinfe"]["default_table"], "tbl0000002")

    def test_the_choice_shows_up_on_the_table_it_names(self) -> None:
        self.client.put(f"/games/{GAME_ID}/default_table", json={"table": "tbl0000002"})
        by_id = {row["id"]: row["default"] for row in self._rows()}

        self.assertEqual(by_id, {"tbl0000001": False, "tbl0000002": True})

    def test_clearing_it_goes_back_to_resolving_from_the_folder(self) -> None:
        """Absent is not the same as a choice of the first one: it means nobody has an
        opinion, and the resolver is free to answer."""
        self.client.put(f"/games/{GAME_ID}/default_table", json={"table": "tbl0000002"})
        self.client.put(f"/games/{GAME_ID}/default_table", json={"table": ""})

        self.assertNotIn("default_table", self._info().get("vpinfe", {}))

    def test_a_table_this_game_does_not_have_is_refused(self) -> None:
        response = self.client.put(f"/games/{GAME_ID}/default_table",
                                   json={"table": "tbl0009999"})
        self.assertEqual(response.status_code, 404)


class HiddenTests(_Lens):
    def test_hiding_takes_it_out_of_play_without_touching_the_file(self) -> None:
        response = self.client.put(f"/games/{GAME_ID}/tables/tbl0000002/hidden",
                                   json={"hidden": True})

        self.assertEqual(response.status_code, 200, response.text)
        self.assertTrue(response.json()["hidden"])
        self.assertTrue((self.folder / VR).is_file(), "the .vpx must stay on disk")

    def test_unhiding_puts_it_back(self) -> None:
        self.client.put(f"/games/{GAME_ID}/tables/tbl0000002/hidden", json={"hidden": True})
        body = self.client.put(f"/games/{GAME_ID}/tables/tbl0000002/hidden",
                               json={"hidden": False}).json()

        self.assertFalse(body["hidden"])

    def test_hiding_one_leaves_the_other_alone(self) -> None:
        self.client.put(f"/games/{GAME_ID}/tables/tbl0000002/hidden", json={"hidden": True})
        by_id = {row["id"]: row["hidden"] for row in self._rows()}

        self.assertEqual(by_id, {"tbl0000001": False, "tbl0000002": True})


class TableScriptTests(_Lens):
    """The sidecar script. VPX runs a `<table>.vbs` in place of the one inside the .vpx,
    so this is not housekeeping - it decides which script the table plays with."""

    def _vbs(self):
        return self.folder / f"{VR[:-4]}.vbs"

    def test_a_sidecar_is_reported_as_the_script_that_resolves(self) -> None:
        self._vbs().write_text("' patched", encoding="utf-8")

        table = next(t for t in self._rows() if t["id"] == "tbl0000002")
        detail = self.client.get(f"/games/{GAME_ID}/tables").json()["tables"]
        script = next(t["assets"]["script"] for t in detail if t["id"] == table["id"])
        self.assertEqual(script["resolution"], "dedicated")

    def test_deleting_it_puts_the_table_back_on_its_own_script(self) -> None:
        self._vbs().write_text("' patched", encoding="utf-8")

        response = self.client.delete(f"/games/{GAME_ID}/tables/tbl0000002/script")

        self.assertEqual(response.status_code, 200, response.text)
        self.assertFalse(self._vbs().exists())
        self.assertEqual(response.json()["assets"]["script"]["resolution"], "none")

    def test_deleting_one_that_is_not_there_is_refused(self) -> None:
        """Not silently fine: a client that thinks it removed something did not."""
        response = self.client.delete(f"/games/{GAME_ID}/tables/tbl0000002/script")

        self.assertEqual(response.status_code, 404)

    def test_the_other_table_keeps_its_own(self) -> None:
        """Stem-named, with no folder fallback - one table's sidecar is not the
        game's."""
        self._vbs().write_text("' patched", encoding="utf-8")
        (self.folder / f"{DESKTOP[:-4]}.vbs").write_text("' other", encoding="utf-8")

        self.client.delete(f"/games/{GAME_ID}/tables/tbl0000002/script")

        self.assertTrue((self.folder / f"{DESKTOP[:-4]}.vbs").is_file())

    def test_extracting_where_there_is_no_launcher_says_so(self) -> None:
        """501, the answer /launch gives for the same condition: the table is fine, the
        machine cannot do the work. A 404 would say the table was not found."""
        response = self.client.post(f"/games/{GAME_ID}/tables/tbl0000002/script")

        self.assertEqual(response.status_code, 501, response.text)
        self.assertEqual(response.json()["error"]["code"], "feature_unavailable")


class TableFeatureTests(_Lens):
    """The library-wide rows list their fields by hand, so anything the hub reads there
    has to be named or it is silently dropped - which is how `rating` read as 0 twice."""

    def test_a_row_carries_what_the_script_uses(self) -> None:
        row = self._rows()[0]

        self.assertIn("features", row)
        self.assertIn("ssf", row["features"])

    def test_a_table_nobody_parsed_answers_null_not_false(self) -> None:
        """Three states. False here would report a clean bill of health for a script
        nothing has read."""
        row = self._rows()[0]

        self.assertIsNone(row["features"]["ssf"])


class TableRatingTests(_Lens):
    """A table's own rating - INFO-SCHEMA section 8.1's open UI call, answered by the
    hub's Tables grid: the row you rate is the file."""

    def test_rating_a_table_stores_it_against_that_table(self) -> None:
        response = self.client.put(f"/games/{GAME_ID}/tables/tbl0000002/rating",
                                   json={"rating": 4})

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["rating"], 4)

    def test_the_other_table_is_untouched(self) -> None:
        self.client.put(f"/games/{GAME_ID}/tables/tbl0000002/rating", json={"rating": 4})

        by_id = {row["id"]: row["rating"] for row in self._rows()}
        self.assertEqual(by_id, {"tbl0000001": 0, "tbl0000002": 4})

    def test_zero_clears_it(self) -> None:
        self.client.put(f"/games/{GAME_ID}/tables/tbl0000002/rating", json={"rating": 4})
        body = self.client.put(f"/games/{GAME_ID}/tables/tbl0000002/rating",
                               json={"rating": 0}).json()

        self.assertEqual(body["rating"], 0)

    def test_a_rating_outside_the_scale_is_refused(self) -> None:
        """Refused rather than clamped, the same as a game's - storing 5 for a caller
        that sent 9 hides its bug."""
        response = self.client.put(f"/games/{GAME_ID}/tables/tbl0000002/rating",
                                   json={"rating": 9})

        self.assertEqual(response.status_code, 422)

    def test_it_survives_a_reread_and_leaves_the_play_counters_alone(self) -> None:
        """The rating shares the table's `user` block with the counters, so writing one
        must not disturb the other - the block is created by whichever comes first."""
        self.client.put(f"/games/{GAME_ID}/tables/tbl0000002/rating", json={"rating": 2})

        stored = json.loads((self.folder / f"{FOLDER}.info").read_text())
        user = stored["tables"]["tbl0000002"]["user"]
        self.assertEqual(user["rating"], 2)
        self.assertEqual(user["start_count"], 0)
        self.assertIsNone(user["last_run"])


if __name__ == "__main__":
    unittest.main()
