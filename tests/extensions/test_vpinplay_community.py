"""VPinPlay's tables, as Community lists them."""

from __future__ import annotations

import importlib
import unittest
import urllib.error
from unittest.mock import patch

from fastapi import FastAPI
from starlette.testclient import TestClient

from common.extensions import host


def _module():
    registry = host.Registry()
    record = registry.load(host.BUNDLED_DIR / "vpinplay")
    registry.clear()
    assert record.state == host.LOADED, record.reason
    return importlib.import_module("vpinfe_ext_vpinplay.community")


def _item(name: str, **more: object) -> dict:
    return {"vpsId": f"id-{name}", "name": name, "manufacturer": "Bally", "year": 1995,
            "avgRating": 4.5, "ratingCount": 12, "startCountTotal": 40,
            "runTimeTotal": 90, "playerCount": 7, "lastRun": "2026-09-22T23:49:46",
            **more}


def _pages(total: int) -> object:
    def page(_endpoint: str, offset: int) -> dict:
        names = [f"T{index:05d}" for index in range(offset, min(offset + 100, total))]
        return {"items": [_item(one) for one in names],
                "pagination": {"total": total, "hasNext": offset + 100 < total}}
    return page


class Rows(unittest.TestCase):
    def setUp(self) -> None:
        self.community = _module()

    def test_a_row_is_in_this_list_s_words(self) -> None:
        row = self.community._row(_item("AFM"))

        self.assertEqual({"name": "AFM", "manufacturer": "Bally", "year": 1995,
                          "rating": 4.5, "average": 4.5, "authors": [],
                          "ratings": 12, "plays": 40, "hours": 1.5,
                          "players": 7, "last_played": "2026-09-22T23:49:46Z",
                          "vps_id": "id-AFM"}, row)

    def test_a_rating_is_to_one_place(self) -> None:
        self.assertEqual(3.3, self.community._row(_item("BK2K", avgRating=10 / 3))["rating"])

    def test_the_total_says_which_pages_to_read_and_they_keep_their_order(self) -> None:
        with patch.object(self.community, "_page", side_effect=_pages(250)) as asked:
            rows = self.community.tables("https://vpinplay.example")

        self.assertEqual([0, 100, 200],
                         sorted(call.args[1] for call in asked.call_args_list))
        self.assertEqual([f"T{index:05d}" for index in range(250)],
                         [one["name"] for one in rows])

    def test_a_list_past_five_thousand_is_read_whole(self) -> None:
        with patch.object(self.community, "_page", side_effect=_pages(5050)):
            rows = self.community.tables("https://vpinplay.example")

        self.assertEqual(5050, len(rows))

    def test_without_a_total_every_page_is_read_until_there_are_no_more(self) -> None:
        pages = [{"items": [_item("A")], "pagination": {"hasNext": True}},
                 {"items": [_item("B")], "pagination": {"hasNext": False}}]
        with patch.object(self.community, "_page", side_effect=pages) as asked:
            rows = self.community.tables("https://vpinplay.example")

        self.assertEqual((["A", "B"], [0, 100]),
                         ([one["name"] for one in rows],
                          [call.args[1] for call in asked.call_args_list]))

    def test_every_look_asks_the_service_again(self) -> None:
        with patch.object(self.community, "_page",
                          return_value={"items": [_item("A")], "pagination": {}}) as asked:
            self.community.tables("https://vpinplay.example")
            self.community.tables("https://vpinplay.example")

        self.assertEqual(2, asked.call_count)

    def _refused(self, failure: Exception) -> tuple[int, str]:
        app = FastAPI()
        app.include_router(self.community.router(lambda: "https://vpinplay.example"))
        with patch.object(self.community, "_page", side_effect=failure):
            response = TestClient(app).get("/community/tables")
        return response.status_code, response.json()["detail"]

    def test_a_server_that_does_not_answer_is_said_as_core_says_it(self) -> None:
        self.assertEqual(
            [(502, "Nothing answers at vpinplay.example"),
             (502, "vpinplay.example did not answer in time")],
            [self._refused(urllib.error.URLError(ConnectionRefusedError())),
             self._refused(TimeoutError("timed out"))])

    def test_an_answer_it_cannot_read_is_its_own_line(self) -> None:
        self.assertEqual((502, "vpinplay.example sent something VPinFE cannot read"),
                         self._refused(ValueError("Expecting value: line 1 column 1")))


class TheDeclaration(unittest.TestCase):
    def test_it_lists_its_tables_related_by_vps_entry(self) -> None:
        registry = host.Registry()
        self.addCleanup(registry.clear)
        record = registry.load(host.BUNDLED_DIR / "vpinplay")

        (said,) = record.lists()
        self.assertEqual(("tables", "VPinPlay", "vps_entry", "Top Rated"),
                         (said["key"], said["title"], said["relation"]["keys"],
                          said["views"][0]["name"]))

    def test_every_view_ranks(self) -> None:
        registry = host.Registry()
        self.addCleanup(registry.clear)
        (said,) = registry.load(host.BUNDLED_DIR / "vpinplay").lists()

        self.assertEqual(["rating", "plays", "hours", "last_played", "players"],
                         [one["key"] for one in said["views"] if one["ranks"]])


if __name__ == "__main__":
    unittest.main()
