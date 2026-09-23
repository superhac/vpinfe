"""A collection's panel in a real browser: rules as a draft, Locked, the limit's line.

Slow: boots a real instance and a real browser.
"""

from __future__ import annotations

import asyncio
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import quote

from tests.support.browser_session import BrowserSession, chromium_path
from tests.support.library import game_info, write_game
from tests.support.live_instance import LiveInstance

NAME = "Smart Bally"
OTHER = "Hand Picked"
GAMES = {"Alpha": ("Bally", "1992"), "Bravo": ("Bally", "1995"),
         "Charlie": ("Williams", "1993")}

INDEX_OF = ("(() => [...document.querySelectorAll(%s)]"
            ".findIndex(el => el.innerText.includes(%s)))()")
TEXT_OF = "(() => { const el = document.querySelector(%s); return el ? el.innerText : null; })()"
GRID_NAME = (".ag-row[row-id=" + json.dumps(NAME) + "] .ag-cell[col-id=\"name\"]")
OTHER_NAME = (".ag-row[row-id=" + json.dumps(OTHER) + "] .ag-cell[col-id=\"name\"]")
UNSAVED_IN_GRID = ("(() => { const el = document.querySelector('.nicegui-aggrid');"
                   " const row = getElement(el.id.slice(1)).api.getRowNode(%s);"
                   " return row ? row.data.unsaved : null; })()")


class CollectionPanelDrive(unittest.TestCase):
    seen: dict = {}

    @classmethod
    def setUpClass(cls) -> None:
        if not chromium_path():
            raise unittest.SkipTest("no Chromium on this machine")
        with TemporaryDirectory() as tmp:
            for title, (maker, year) in GAMES.items():
                tables = ({"t-a1": {"id": "t-a1", "filename": "Alpha 1.vpx", "version": "1"},
                           "t-a2": {"id": "t-a2", "filename": "Alpha 2.vpx", "version": "2"}}
                          if title == "Alpha" else None)
                info = game_info(title, vps_id="", game_id=title.lower(), tables=tables,
                                 Info={"Manufacturer": maker, "Year": year})
                if tables:
                    info["vpinfe"]["default_table"] = "t-a2"
                write_game(Path(tmp), title, info=info, vpx=not tables,
                           files={"Alpha 1.vpx": b"x", "Alpha 2.vpx": b"x"} if tables
                           else None)
            with LiveInstance(Path(tmp)) as instance:
                cls.seen = asyncio.run(cls._drive(instance))

    @classmethod
    async def _drive(cls, instance: LiveInstance) -> dict:
        seen: dict = {}
        instance.wait_for_api()
        instance.post("/api/v1/collections", {"name": NAME})
        instance.post("/api/v1/collections", {"name": OTHER, "games": ["bravo", "charlie"]})
        stored = f"/api/v1/collections/{quote(NAME)}"

        async with BrowserSession(chromium_path()) as browser:
            async def click_text(selector: str, text: str) -> None:
                at = await browser.wait_for(
                    f"(() => {{ const i = {INDEX_OF % (json.dumps(selector), json.dumps(text))};"
                    " return i >= 0 ? i + 1 : 0; })()")
                await browser.click(selector, nth=int(at) - 1)
                await asyncio.sleep(0.6)

            async def settled() -> None:
                await asyncio.sleep(2.5)

            await browser.navigate(instance.console_url(
                f"/console?view=collections&collection={quote(NAME)}"))
            await browser.wait_for("document.body.innerText.includes('Add a Rule')",
                                   timeout=90.0)
            seen["empty"] = await browser.evaluate(
                TEXT_OF % json.dumps(".console-section-work"))

            await click_text(".console-section-work button", "Add a Rule")
            await click_text(".q-menu .console-menu-item", "Manufacturer")
            await settled()
            await browser.click(".console-condition-value .q-field")
            await asyncio.sleep(0.8)
            seen["offered"] = await browser.evaluate(
                "[...document.querySelectorAll('.q-menu .q-item')].map(i => i.innerText)")
            await click_text(".q-menu .q-item", "Bally")
            seen["still_open"] = await browser.evaluate(
                "!!document.querySelector('.q-menu')")
            await browser.click(".console-workbench-title")
            await browser.wait_for("!!document.querySelector('.console-draft-bar')")
            await settled()
            seen["bar"] = await browser.evaluate(TEXT_OF % json.dumps(".console-draft-bar"))
            seen["marked"] = await browser.evaluate(TEXT_OF % json.dumps(GRID_NAME))
            seen["before_save"] = instance.api(stored)["filters"]

            await browser.click(OTHER_NAME)
            await browser.wait_for(TEXT_OF % json.dumps(".console-workbench-title")
                                   + " === " + json.dumps(OTHER))
            await settled()
            seen["marked_elsewhere"] = await browser.evaluate(UNSAVED_IN_GRID
                                                              % json.dumps(NAME))
            await browser.click(GRID_NAME)
            await browser.wait_for("!!document.querySelector('.console-draft-bar')")

            await click_text(".console-draft-bar button", "Save Rules")
            await settled()
            seen["saved"] = instance.api(stored)["filters"]["manufacturer"]
            seen["unmarked"] = await browser.evaluate(TEXT_OF % json.dumps(GRID_NAME))

            await click_text(".console-member-row .console-member-table-line", "2")
            await click_text(".q-menu .console-menu-item", "Lock to 1")
            await settled()
            members = instance.api(f"{stored}/members")["members"]
            seen["locked"] = [(one["game"], one["origin"], one["ref_table"])
                              for one in members if one["game"] == "alpha"]
            seen["lock_line"] = await browser.evaluate(
                TEXT_OF % json.dumps(".console-member-row .console-member-table-line"))

            await browser.click(".console-order-bar input[type=number]")
            await browser.send("Input.insertText", {"text": "1"})
            await browser.press("Enter", "Enter")
            await settled()
            seen["cut"] = await browser.evaluate(
                "[...document.querySelectorAll('.console-member-row.console-past-limit')]"
                ".map(r => r.querySelector('.console-member-name').innerText)")
            seen["cut_line"] = await browser.evaluate(
                TEXT_OF % json.dumps(".console-limit-line"))

            await browser.click(".console-condition .console-condition-remove")
            await settled()
            await click_text(".console-draft-bar button", "Save Rules")
            await browser.wait_for("!!document.querySelector('.q-dialog')")
            seen["question"] = await browser.evaluate(TEXT_OF % json.dumps(".q-dialog"))
            await click_text(".q-dialog .q-radio", "you added")
            await click_text(".q-dialog button", "Remove Rules")
            await settled()
            after = instance.api(stored)
            seen["kept"] = (after["type"], [one["game"] for one in instance.api(
                f"{stored}/members")["members"]])
        return seen

    def test_an_empty_collection_offers_both_ways_in(self) -> None:
        self.assertIn("Nothing in it yet", self.seen["empty"])
        self.assertIn("Add Games", self.seen["empty"])

    def test_values_say_how_many_games_hold_them_and_stay_open_while_picked(self) -> None:
        self.assertIn("Bally\n2", self.seen["offered"])
        self.assertTrue(self.seen["still_open"])

    def test_a_rule_waits_as_a_draft_and_the_grid_says_so(self) -> None:
        self.assertTrue(self.seen["bar"].startswith("2 games match · 2 join"), self.seen["bar"])
        self.assertIn("Not saved", self.seen["marked"])
        self.assertIsNone(self.seen["before_save"])

    def test_the_mark_stays_while_another_collection_is_open(self) -> None:
        self.assertIs(True, self.seen["marked_elsewhere"])

    def test_saving_writes_the_rule_and_clears_the_mark(self) -> None:
        self.assertEqual(["Bally"], self.seen["saved"])
        self.assertNotIn("Not saved", self.seen["unmarked"])

    def test_a_row_the_rule_found_can_be_locked_to_one_table(self) -> None:
        self.assertEqual([("alpha", "named", "t-a1")], self.seen["locked"])
        self.assertTrue(self.seen["lock_line"].startswith("lock\nLocked"),
                        self.seen["lock_line"])

    def test_a_limit_draws_the_rows_it_cuts_under_a_line(self) -> None:
        self.assertEqual(["Bravo"], self.seen["cut"])
        self.assertIn("limit 1", self.seen["cut_line"])

    def test_taking_the_last_rule_away_asks_what_to_keep(self) -> None:
        self.assertIn("Keep the 1 game it found", self.seen["question"])
        self.assertIn("Keep only the 1 you added", self.seen["question"])
        self.assertEqual(("manual", ["alpha"]), self.seen["kept"])


if __name__ == "__main__":
    unittest.main()
