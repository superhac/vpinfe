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


class Rows(unittest.TestCase):
    def setUp(self) -> None:
        self.community = _module()
        self.community._held.update(at=0.0, endpoint="", rows=[])

    def test_a_row_is_in_this_list_s_words(self) -> None:
        row = self.community._row(_item("AFM"))

        self.assertEqual({"name": "AFM", "manufacturer": "Bally", "year": 1995,
                          "rating": 4.5, "ratings": 12, "plays": 40, "hours": 1.5,
                          "players": 7, "last_played": "2026-09-22T23:49:46Z",
                          "vps_id": "id-AFM"}, row)

    def test_a_rating_is_to_one_place(self) -> None:
        self.assertEqual(3.3, self.community._row(_item("BK2K", avgRating=10 / 3))["rating"])

    def test_every_page_is_read_until_there_are_no_more(self) -> None:
        pages = [{"items": [_item("A")], "pagination": {"hasNext": True}},
                 {"items": [_item("B")], "pagination": {"hasNext": False}}]
        with patch.object(self.community, "_page", side_effect=pages) as asked:
            rows = self.community.tables("https://vpinplay.example")

        self.assertEqual((["A", "B"], [0, 100]),
                         ([one["name"] for one in rows],
                          [call.args[1] for call in asked.call_args_list]))

    def test_a_second_look_within_ten_minutes_asks_nothing(self) -> None:
        with patch.object(self.community, "_page",
                          return_value={"items": [_item("A")], "pagination": {}}) as asked:
            self.community.tables("https://vpinplay.example")
            self.community.tables("https://vpinplay.example")

        self.assertEqual(1, asked.call_count)

    def test_a_server_that_does_not_answer_is_said_as_such(self) -> None:
        app = FastAPI()
        app.include_router(self.community.router(lambda: "https://vpinplay.example"))
        with patch.object(self.community, "_page",
                          side_effect=urllib.error.URLError("refused")):
            response = TestClient(app).get("/community/tables")

        self.assertEqual(502, response.status_code)


class TheDeclaration(unittest.TestCase):
    def test_it_lists_its_tables_related_by_vps_entry(self) -> None:
        registry = host.Registry()
        self.addCleanup(registry.clear)
        record = registry.load(host.BUNDLED_DIR / "vpinplay")

        (said,) = record.community
        self.assertEqual(("tables", "VPinPlay", "vps_entry", "Top Rated"),
                         (said["key"], said["title"], said["relation"]["keys"],
                          said["views"][0]["name"]))


if __name__ == "__main__":
    unittest.main()
