"""Community: the lists extensions declare, drawn by core."""

from __future__ import annotations

import asyncio
import tempfile
import unittest
from collections.abc import Callable
from pathlib import Path
from typing import Any
from unittest.mock import Mock, patch

from nicegui import ui

from common import install_identity
from common.extensions import host
from common.i18n import t
from console import busy, community, page, verbs, views
from console.api import ApiError
from console.data import read_state

DECLARED = {"key": "tables", "title": "Site", "base": "/community/tables",
            "columns": [{"field": "name", "header": "Table", "kind": "text",
                         "under": ["maker", "year"]},
                        {"field": "plays", "header": "Plays", "kind": "number"},
                        {"field": "last", "header": "Last", "kind": "date"},
                        {"field": "vps_id", "header": "VPS", "kind": "text"}],
            "views": [{"key": "plays", "name": "Most played", "columns": ["name", "plays"],
                       "sort": [{"field": "plays", "desc": True}], "help": ""}],
            "relation": {"field": "vps_id", "keys": "vps_entry"}}
LOADED = {"name": "site", "state": "loaded", "community": [DECLARED]}


class TheNav(unittest.TestCase):
    def test_a_running_extension_s_list_sits_under_community(self) -> None:
        items = community.nav_items([LOADED, {**LOADED, "name": "off", "state": "failed"}],
                                    install_identity.CORE)
        groups = dict(page.nav_for(None, items))

        self.assertEqual(["community:site:tables"],
                         [one[0] for one in groups[page.NAV_COMMUNITY]])

    def test_community_sits_between_frontend_and_system(self) -> None:
        parents = [parent for parent, _items in page.NAV_GROUPS]

        self.assertEqual([page.NAV_FRONTEND, page.NAV_COMMUNITY, page.NAV_SYSTEM],
                         parents[-3:])

    def test_with_no_list_there_is_no_community(self) -> None:
        self.assertNotIn(page.NAV_COMMUNITY, dict(page.nav_for(None)))

    def test_a_view_finds_its_list(self) -> None:
        self.assertEqual((LOADED, DECLARED),
                         community.find("community:site:tables", [LOADED]))


class RankedOrders(unittest.TestCase):
    RANKED = {**DECLARED, "views": [{**DECLARED["views"][0], "ranks": True},
                                    {"key": "all", "name": "All", "columns": ["name"],
                                     "sort": [], "help": ""}]}

    def test_each_ranked_view_is_named_for_its_page_and_itself(self) -> None:
        offered = community.ranked_orders([{**LOADED, "community": [self.RANKED]},
                                           {**LOADED, "name": "off", "state": "failed",
                                            "community": [self.RANKED]}])

        self.assertEqual({"site/tables/plays": "Site: Most played"}, offered)

    def test_a_list_that_relates_to_nothing_offers_no_order(self) -> None:
        loose = {**self.RANKED, "relation": None}

        self.assertEqual({}, community.ranked_orders([{**LOADED, "community": [loose]}]))

    def test_the_smart_collection_in_a_view_s_order_is_the_one_it_opens(self) -> None:
        collections = [{"name": "Mine", "type": "manual", "order_by": "site/tables/plays"},
                       {"name": "Titles", "type": "filter", "order_by": "title"},
                       {"name": "Site: Most played", "type": "filter",
                        "order_by": "site/tables/plays"}]

        self.assertEqual("Site: Most played",
                         community.collection_ordered_by(collections, "site/tables/plays"))
        self.assertEqual("", community.collection_ordered_by(collections[:2],
                                                              "site/tables/plays"))

    def test_a_stored_order_no_running_extension_offers_names_the_extension(self) -> None:
        self.assertEqual("Site, not running",
                         community.ranked_label({"extension": "site", "display_name": "Site",
                                                 "offered": False}))


class TheGrid(unittest.TestCase):
    def test_the_first_column_is_scanned_by_and_in_library_follows(self) -> None:
        shown = community.columns(DECLARED)

        self.assertEqual(["name", "plays", "last", "vps_id", community.HELD],
                         [one["field"] for one in shown])
        self.assertIn("console-cell-identifier", shown[0]["cellClass"])
        self.assertEqual("numericColumn", shown[1]["type"])

    def test_a_view_keeps_its_sort_and_yours_keeps_only_what_is_held(self) -> None:
        presets = community.presets(DECLARED)

        self.assertEqual(({"colId": "plays", "sort": "desc", "sortIndex": 0},),
                         presets["plays"].sort)
        self.assertEqual({community.HELD: {"values": [True]}},
                         presets["console.community.yours"].filters)

    def test_a_view_is_kept_by_its_key_and_shown_by_the_name_it_was_sent(self) -> None:
        (plays, _yours) = views.builtins(community.presets(DECLARED))

        self.assertEqual((views.builtin_id("plays"), "Most played"), (plays.id, plays.name))

    def test_a_held_row_links_its_name_to_the_game(self) -> None:
        rows = community.rows([{"name": "AFM", "vps_id": "vps-afm", "last": ""},
                               {"name": "TAF", "vps_id": "vps-taf", "last": ""}], DECLARED,
                              {"vps-afm": {"game_id": "afm", "table_id": "",
                                           "name": "Attack from Mars"}})

        self.assertEqual([(True, "/console?view=games&game=afm"), (False, "")],
                         [(one[community.HELD], one["held_href"]) for one in rows])
        self.assertIn("last_ago", rows[0])

    def test_a_held_release_links_to_its_table(self) -> None:
        released = {**DECLARED, "relation": {"field": "vps_id", "keys": "vps_release"}}
        (row,) = community.rows([{"name": "AFM", "vps_id": "rel-1", "last": ""}], released,
                                {"rel-1": {"game_id": "afm", "table_id": "t1", "name": "AFM"}})

        self.assertEqual("/console?view=tables&game=afm&table=t1", row["held_href"])

    def test_another_version_says_which_and_links_to_the_release(self) -> None:
        released = {**DECLARED, "relation": {"field": "vps_id", "keys": "vps_release"}}
        (row,) = community.rows(
            [{"name": "AFM", "maker": "Bally", "vps_id": "rel-2", "last": ""}], released, {},
            {"rel-2": {"game_id": "afm", "table_id": "t1", "name": "AFM", "version": "1.2",
                       "url": "https://example.test/afm"}})

        self.assertEqual((False, "https://example.test/afm"),
                         (row[community.HELD], row["held_href"]))
        self.assertEqual("Bally · Different version - you have 1.2", row[community.UNDER])

    def test_the_fields_under_the_name_make_its_second_line(self) -> None:
        (row,) = community.rows([{"name": "AFM", "maker": "Bally", "year": 1995,
                                  "vps_id": "", "last": ""}], DECLARED, {})

        self.assertEqual("Bally 1995", row[community.UNDER])

    def test_in_library_is_not_a_column_of_any_view(self) -> None:
        for name, preset in community.presets(DECLARED).items():
            with self.subTest(view=name):
                self.assertNotIn(community.HELD, preset.columns)


def _answering(*rows: dict) -> Callable[[], dict]:
    return lambda: {"rows": list(rows)}


def _down() -> dict:
    raise ApiError("https://site.example did not answer")


class TheLastGoodRead(unittest.TestCase):
    def setUp(self) -> None:
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.kept = Path(folder.name)
        kept = patch("common.paths.COMMUNITY_KEPT_DIR", self.kept)
        kept.start()
        self.addCleanup(kept.stop)

    def test_a_fresh_read_is_kept_and_said_to_be_now(self) -> None:
        said = community.read("site", "tables", _answering({"name": "AFM"}))

        self.assertEqual(([{"name": "AFM"}], False, ""),
                         (said["rows"], said["stale"], said["error"]))
        self.assertEqual(["AFM"], [one["name"] for one in
                                   community.kept("site", "tables")["rows"]])
        self.assertTrue(said["read_at"])

    def test_an_outage_answers_with_the_last_good_list_said_to_be_stale(self) -> None:
        good = community.read("site", "tables", _answering({"name": "AFM"}))

        said = community.read("site", "tables", _down)

        self.assertEqual(([{"name": "AFM"}], True, good["read_at"]),
                         (said["rows"], said["stale"], said["read_at"]))
        self.assertIn("did not answer", said["error"])
        self.assertIn("Last good read", read_state(said))

    def test_an_outage_with_nothing_kept_has_no_list_to_show(self) -> None:
        said = community.read("site", "tables", _down)

        self.assertEqual((None, True), (said["rows"], said["stale"]))
        self.assertIsNone(community.kept("site", "tables")["rows"])

    def test_with_nothing_kept_the_answer_is_still_an_answer(self) -> None:
        """The page reads it through `offload.io`, which takes None for a shutdown."""
        self.assertEqual({"rows": None, "read_at": "", "stale": False, "error": ""},
                         community.kept("site", "tables"))

    def test_a_later_good_read_replaces_the_kept_one(self) -> None:
        community.read("site", "tables", _answering({"name": "AFM"}))
        community.read("site", "tables", _answering({"name": "TAF"}, {"name": "MM"}))

        self.assertEqual(["TAF", "MM"], [one["name"] for one in
                                         community.kept("site", "tables")["rows"]])

    def test_each_list_is_kept_apart_whatever_its_key_holds(self) -> None:
        community.read("site", "tables", _answering({"name": "AFM"}))
        community.read("site", "../tables", _answering({"name": "TAF"}))

        self.assertEqual((["AFM"], ["TAF"]),
                         tuple([one["name"] for one in community.kept("site", key)["rows"]]
                               for key in ("tables", "../tables")))
        self.assertEqual(["site"], [one.name for one in self.kept.iterdir()])


PLAIN = {"key": "tables", "title": "Site", "base": "/community/tables",
         "columns": [{"field": "name", "header": "Table", "kind": "text"}]}
KEPT = {"rows": [{"name": "AFM"}], "read_at": "2026-09-25T10:00:00+00:00", "stale": False,
        "error": ""}
SWITCHED_OFF = {**LOADED, "state": host.OFF, "reason": "Switched off",
                "reason_key": host.SWITCHED_OFF}


async def _here(callback: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    return callback(*args, **kwargs)


class ItsExtensionNotRunning(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        # Outside the test's task, which has no page to draw into.
        self.body = ui.column()

    async def fill(self, now: dict, kept: dict, *,
                   opened: bool = False) -> tuple[list[str], list[str], Mock]:
        """`_fill` drawn into the body, or the page `build` opens when `opened`."""
        self.held_when_read: list[bool] = []

        def reading(*_args: Any) -> dict:
            self.held_when_read.append(any(one.props.get("aria-busy")
                                           for one in self.body.descendants()))
            return kept

        read = self.enterContext(patch.object(community, "read", side_effect=reading))
        self.enterContext(patch.object(community.offload, "io", new=_here))
        self.enterContext(patch.object(community, "as_it_stands", return_value=now))
        self.enterContext(patch.object(community, "kept", return_value=kept))
        self.enterContext(patch("console.games.view_control",
                                return_value=(Mock(), Mock(), Mock(), Mock())))
        # The grid talks to a browser, which a unit test does not have.
        self.enterContext(patch.object(community.grid, "build",
                                       return_value=Mock(is_deleted=False)))
        self.enterContext(patch.object(community.grid, "replace_rows"))
        if opened:
            with self.body:
                with patch.object(busy.ui, "timer") as timer:
                    community.build(LOADED, PLAIN, Mock())
                await timer.call_args.args[1]()
        else:
            with self.body:
                await community._fill(LOADED, PLAIN, Mock(), self.body)
        # A kept list is read again after it is drawn, in a task of its own.
        await asyncio.gather(*(asyncio.all_tasks() - {asyncio.current_task()}))
        drawn = list(self.body.descendants())
        return ([str(getattr(one, "text", "")) for one in drawn],
                [str(one.props.get("icon")) for one in drawn if isinstance(one, ui.button)],
                read)

    async def test_switched_off_it_shows_what_was_kept_and_offers_no_read(self) -> None:
        said, icons, read = await self.fill(SWITCHED_OFF, KEPT)

        read.assert_not_called()
        self.assertNotIn(verbs.REFRESH, icons)
        self.assertIn(t("word.off"), said)
        self.assertTrue(any(one.startswith("Last good read") for one in said))

    async def test_stopped_it_says_so_with_its_reason(self) -> None:
        said, icons, read = await self.fill(
            {**LOADED, "state": host.DISABLED, "reason": "It threw",
             "reason_key": "extension.reason.failed_serving"}, KEPT)

        read.assert_not_called()
        self.assertNotIn(verbs.REFRESH, icons)
        self.assertIn(t("console.community.stopped"), said)
        self.assertIn("It threw", said)

    async def test_with_nothing_kept_it_says_the_extension_is_not_running(self) -> None:
        said, _icons, read = await self.fill(SWITCHED_OFF, {**KEPT, "rows": None})

        read.assert_not_called()
        self.assertIn(t("console.community.not_running", name="site",
                        reason="Switched off"), said)

    async def test_running_it_reads_again_and_offers_refresh(self) -> None:
        _said, icons, read = await self.fill(LOADED, KEPT)

        read.assert_called_once()
        self.assertIn(verbs.REFRESH, icons)

    async def test_with_nothing_kept_the_read_is_part_of_opening_the_page(self) -> None:
        await self.fill(LOADED, {**KEPT, "rows": None}, opened=True)

        self.assertEqual([True], self.held_when_read)

    async def test_a_kept_list_is_read_again_once_the_page_is_open(self) -> None:
        await self.fill(LOADED, KEPT, opened=True)

        self.assertEqual([False], self.held_when_read)


class AsItStands(unittest.TestCase):
    def test_the_api_s_answer_wins_over_what_the_rail_read(self) -> None:
        with patch.object(community, "ApiClient") as client:
            client.return_value.extensions.return_value = [SWITCHED_OFF]

            self.assertEqual(SWITCHED_OFF, community.as_it_stands(LOADED))

    def test_when_the_api_cannot_say_it_is_taken_as_given(self) -> None:
        with patch.object(community, "ApiClient") as client:
            client.return_value.extensions.side_effect = ApiError("down")

            self.assertEqual(LOADED, community.as_it_stands(LOADED))


if __name__ == "__main__":
    unittest.main()
