"""A list an extension declares for Community, and the ones it may not."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from starlette.testclient import TestClient

import httpapi
from common import extensions
from common.extensions import host, store
from common.extensions.context import ContractError, ExtensionUI

ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "community"
WEEK = "https://challenge.example/week"

COLUMNS = [{"field": "name", "header": "Table"},
           {"field": "plays", "header": "Plays", "kind": "number"},
           {"field": "vpsId", "header": "VPS"}]


class TheDeclaration(unittest.TestCase):
    def setUp(self) -> None:
        self.ui = ExtensionUI("site", allowed=True)

    def test_a_list_is_recorded_as_data(self) -> None:
        self.ui.community("tables", "/community/tables", title="Site", columns=COLUMNS,
                          views=[{"key": "plays", "name": "Most played",
                                  "columns": ["name", "plays"],
                                  "sort": [{"field": "plays", "desc": True}]}],
                          relation={"field": "vpsId", "keys": "vps_entry"})

        (said,) = self.ui.community_lists
        self.assertEqual(("tables", ["text", "number", "text"],
                          [{"field": "plays", "desc": True}], "vps_entry"),
                         (said["key"], [one["kind"] for one in said["columns"]],
                          said["views"][0]["sort"], said["relation"]["keys"]))

    def test_a_kind_core_does_not_draw_is_refused(self) -> None:
        with self.assertRaises(ContractError):
            self.ui.community("tables", "/t", title="Site",
                              columns=[{"field": "art", "header": "Art", "kind": "html"}])

    def test_a_view_on_a_column_it_does_not_have_is_refused(self) -> None:
        with self.assertRaises(ContractError):
            self.ui.community("tables", "/t", title="Site", columns=COLUMNS,
                              views=[{"key": "top", "sort": [{"field": "rating"}]}])

    def test_a_view_with_no_key_is_refused(self) -> None:
        """The key is what its words are found by, in the extension's catalog."""
        with self.assertRaises(ContractError):
            self.ui.community("tables", "/t", columns=COLUMNS,
                              views=[{"name": "Top", "sort": [{"field": "plays"}]}])

    def test_a_line_under_the_first_column_is_kept(self) -> None:
        self.ui.community("tables", "/t", title="Site",
                          columns=[{**COLUMNS[0], "under": ["maker", "year"]}, *COLUMNS[1:]])

        self.assertEqual(["maker", "year"],
                         self.ui.community_lists[0]["columns"][0]["under"])

    def test_a_line_under_any_other_column_is_refused(self) -> None:
        with self.assertRaises(ContractError):
            self.ui.community("tables", "/t", title="Site",
                              columns=[COLUMNS[0], {**COLUMNS[1], "under": ["year"]}])

    def test_a_relation_by_anything_but_a_vps_id_is_refused(self) -> None:
        with self.assertRaises(ContractError):
            self.ui.community("tables", "/t", title="Site", columns=COLUMNS,
                              relation={"field": "name", "keys": "rom"})

    def test_a_tag_is_recorded_as_a_tag_would_be_stored(self) -> None:
        self.ui.community("tables", "/t", title="Site", columns=COLUMNS,
                          relation={"field": "vpsId", "keys": "vps_release"},
                          tag=" Weekly   Challenge ")

        self.assertEqual("Weekly Challenge", self.ui.community_lists[0]["tag"])

    def test_a_tag_on_a_list_that_relates_to_nothing_is_refused(self) -> None:
        """The tag lands on what the list relates to, so without a relation it would
        land nowhere and say nothing about why."""
        with self.assertRaises(ContractError):
            self.ui.community("tables", "/t", title="Site", columns=COLUMNS, tag="Challenge")

    def test_a_view_ranks_by_numbers_and_dates(self) -> None:
        self.ui.community("scores", "/t", title="Site",
                          columns=[*COLUMNS, {"field": "set", "kind": "date"}],
                          views=[{"key": "top", "ranks": True,
                                  "sort": [{"field": "plays", "desc": True},
                                           {"field": "set"}]},
                                 {"key": "all", "sort": [{"field": "name"}]}],
                          relation={"field": "vpsId", "keys": "vps_release"})

        self.assertEqual([True, False],
                         [one["ranks"] for one in self.ui.community_lists[0]["views"]])

    def test_a_ranked_view_sorting_on_text_is_refused(self) -> None:
        """A ranking is a number a game has; a name sorts but ranks nothing."""
        with self.assertRaises(ContractError):
            self.ui.community("tables", "/t", title="Site", columns=COLUMNS,
                              views=[{"key": "top", "ranks": True,
                                      "sort": [{"field": "plays", "desc": True},
                                               {"field": "name"}]}],
                              relation={"field": "vpsId", "keys": "vps_entry"})

    def test_a_ranked_view_with_no_sort_is_refused(self) -> None:
        with self.assertRaises(ContractError):
            self.ui.community("tables", "/t", title="Site", columns=COLUMNS,
                              views=[{"key": "top", "ranks": True}],
                              relation={"field": "vpsId", "keys": "vps_entry"})

    def test_a_ranked_view_of_a_list_that_relates_to_nothing_is_refused(self) -> None:
        with self.assertRaises(ContractError):
            self.ui.community("tables", "/t", title="Site", columns=COLUMNS,
                              views=[{"key": "top", "ranks": True,
                                      "sort": [{"field": "plays", "desc": True}]}])

    def test_it_needs_the_capability_to_draw(self) -> None:
        with self.assertRaises(ContractError):
            ExtensionUI("site", allowed=False).community("tables", "/t", columns=COLUMNS)

    def test_the_route_saying_how_it_stands_is_recorded_as_given(self) -> None:
        self.ui.community("tables", "/t", title="Site", columns=COLUMNS, about=" /t/about ")
        self.ui.community("scores", "/s", title="Site", columns=COLUMNS)

        self.assertEqual(["/t/about", ""],
                         [one["about"] for one in self.ui.community_lists])


class HowTheListStands(unittest.TestCase):
    """The fixture's Ratings list answers a line and its acts from its settings, through
    the routes core asks."""

    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.store = store.ExtensionStore(Path(tmp.name) / "extensions.json")
        self.registry = host.Registry(self.store)
        extensions.set_registry(self.registry)
        self.addCleanup(extensions.set_registry, host.Registry())
        self.addCleanup(self.registry.clear)
        self.registry.load_from(ROOT)
        self.client = TestClient(httpapi.create_api_app(), raise_server_exceptions=False)

    def about(self) -> dict:
        answer = self.client.get("/ext/challenge/ratings/about")
        answer.raise_for_status()
        return answer.json()

    def test_the_declaration_names_the_route_for_core(self) -> None:
        (found,) = [one for one in self.client.get("/extensions").json()["extensions"]
                    if one["name"] == "challenge"]

        self.assertEqual({"machines": "", "releases": "", "ratings": "/ratings/about",
                          "builds": ""},
                         {one["key"]: one["about"] for one in found["community"]})

    def test_a_line_and_the_acts_that_can_work_now(self) -> None:
        self.store.set_setting("challenge", "status", "Ends Sunday")
        self.store.set_setting("challenge", "status_to", "settings")
        self.store.set_setting("challenge", "waiting", "afm,mm")

        self.assertEqual({"status": {"text": "Ends Sunday", "to": "settings"},
                          "acts": [{"key": "post", "label": "Post Now"},
                                   {"key": "week", "label": "This Week", "url": WEEK}]},
                         self.about())

    def test_an_act_is_pressed_on_the_route_under_it(self) -> None:
        self.store.set_setting("challenge", "waiting", "afm,mm")

        said = self.client.post("/ext/challenge/ratings/about/acts/post")

        self.assertEqual((200, {"message": "Posted 2"}), (said.status_code, said.json()))
        self.assertEqual(["week"], [one["key"] for one in self.about()["acts"]])

    def test_a_stopped_extension_answers_neither(self) -> None:
        self.registry.disable("challenge", "switched off")

        self.assertEqual(
            (501, 501),
            (self.client.get("/ext/challenge/ratings/about").status_code,
             self.client.post("/ext/challenge/ratings/about/acts/post").status_code))


if __name__ == "__main__":
    unittest.main()
