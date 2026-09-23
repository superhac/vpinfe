"""Rows dragged from the Games and Tables grids onto a collection, in a real browser: what
a drag carries, a drop at a place in a collection's list, the rail's collections while
rows are dragged, and a drop from another install refused.

The drag is started for real and intercepted, and its data dropped where the test says,
which is how a drop from another window arrives. Slow: boots a real instance and a real
browser.
"""

from __future__ import annotations

import asyncio
import json
import unittest
import urllib.request
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import parse_qs, quote, urlparse

from tests.support.browser_session import BrowserSession, chromium_path
from tests.support.library import game_info, write_game
from tests.support.live_instance import LiveInstance

HAND = "Hand Picked"
SMART = "Smart Bally"
GAMES = {"Alpha": ("Bally", "1992"), "Bravo": ("Bally", "1995"),
         "Charlie": ("Williams", "1993"), "Delta": ("Williams", "1980")}

API = ("(() => { const el = document.querySelector('.ag-root-wrapper')"
       ".closest('.nicegui-aggrid'); return getElement(Number(el.id.slice(1))).api; })()")
BOX = ("(() => { const el = document.querySelector(%s); if (!el) return null;"
       " const r = el.getBoundingClientRect();"
       " return [r.left + r.width / 2, r.top + r.height / 2, r.top, r.height]; })()")
NOTE = ("(() => { const n = [...document.querySelectorAll('.q-notification')]"
        ".find(n => n.innerText.includes(%s)); return n ? [n.innerText, n.className] : null;"
        " })()")
RAIL = ("[...document.querySelectorAll('.console-rail-drops .console-drop-target')]"
        ".map(e => [e.innerText.replace(/\\n+/g, ' / '), e.getBoundingClientRect().height > 0])")


class RowDragDrive(unittest.TestCase):
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
        instance.post("/api/v1/collections", {"name": HAND, "games": ["bravo", "charlie"]})
        urllib.request.urlopen(urllib.request.Request(
            instance.console_url(f"/api/v1/collections/{quote(HAND)}"),
            data=json.dumps({"order_by": "manual"}).encode(), method="PATCH",
            headers={"Content-Type": "application/json"}), timeout=10).close()
        instance.post("/api/v1/collections", {"name": SMART,
                                              "filters": {"manufacturer": ["Bally"]}})

        def refs(name: str) -> list:
            return [(one["game"], one["ref_table"], one["origin"]) for one in instance.api(
                f"/api/v1/collections/{quote(name)}/members")["members"]]

        async with BrowserSession(chromium_path()) as browser:
            caught: list[dict] = []
            heard = browser._on_event

            def hearing(method: str, params: dict) -> None:
                if method == "Input.dragIntercepted":
                    caught.append(params["data"])
                heard(method, params)

            browser._on_event = hearing  # type: ignore[method-assign]
            await browser.send("Input.setInterceptDrags", {"enabled": True})

            async def settled() -> None:
                await asyncio.sleep(1.5)

            async def mouse(kind: str, x: float, y: float) -> None:
                await browser.send("Input.dispatchMouseEvent",
                                   {"type": kind, "x": x, "y": y, "button": "left",
                                    "buttons": 0 if kind == "mouseReleased" else 1,
                                    "clickCount": 1})

            async def grab(row_id: str, column: str) -> dict:
                """Drag this row by its grip, and answer what the drag carries."""
                await browser.evaluate(API + ".ensureNodeVisible(" + API + ".getRowNode("
                                       + json.dumps(row_id) + "), 'middle')")
                await asyncio.sleep(0.4)
                cell = f'.ag-row[row-id="{row_id}"] .ag-cell[col-id="{column}"]'
                x, y, _top, _height = await browser.evaluate(BOX % json.dumps(cell))
                await browser.send("Input.dispatchMouseEvent",
                                   {"type": "mouseMoved", "x": x, "y": y, "button": "none"})
                await asyncio.sleep(0.3)
                gx, gy, _top, _height = await browser.evaluate(
                    BOX % json.dumps(cell + " .ag-drag-handle"))
                before = len(caught)
                await mouse("mousePressed", gx, gy)
                for step in range(1, 8):
                    await browser.send("Input.dispatchMouseEvent",
                                       {"type": "mouseMoved", "x": gx + step * 12,
                                        "y": gy + step * 6, "button": "left",
                                        "buttons": 1})
                    await asyncio.sleep(0.04)
                for _ in range(50):
                    if len(caught) > before:
                        break
                    await asyncio.sleep(0.05)
                await mouse("mouseReleased", gx + 84, gy + 42)
                return caught[-1]

            async def let_go(data: dict) -> None:
                """End an intercepted drag nowhere, as dropping outside the page does."""
                await browser.send("Input.dispatchDragEvent",
                                   {"type": "dragCancel", "x": 0, "y": 0, "data": data})
                await asyncio.sleep(0.3)

            async def drop(data: dict, x: float, y: float) -> None:
                for kind in ("dragEnter", "dragOver", "dragOver"):
                    await browser.send("Input.dispatchDragEvent",
                                       {"type": kind, "x": x, "y": y, "data": data})
                    await asyncio.sleep(0.15)
                seen.setdefault("lines", []).append(await browser.evaluate(
                    "!!document.querySelector('.console-drop-line')"))
                await browser.send("Input.dispatchDragEvent",
                                   {"type": "drop", "x": x, "y": y, "data": data})

            async def said(text: str) -> list:
                return await browser.wait_for(NOTE % json.dumps(text), timeout=15.0)

            await browser.navigate(instance.console_url("/console?view=games"))
            await browser.wait_for(API + ".getDisplayedRowCount() > 0", timeout=90.0)
            await settled()

            for game in ("alpha", "delta"):
                await browser.evaluate(API + f".getRowNode('{game}').setSelected(true)")
            both = await grab("delta", "name")
            seen["payload"] = {item["mimeType"]: item["data"] for item in both["items"]}
            await let_go(both)
            await browser.evaluate(API + ".deselectAll()")

            one = await grab("delta", "name")
            await browser.wait_for("document.querySelectorAll('.console-rail-drops"
                                   " .console-drop-target').length > 1")
            await asyncio.sleep(0.4)
            seen["rail"] = await browser.evaluate(RAIL)
            target = f'.console-rail-drops [data-drop-collection="{SMART}"]'
            x, y, _top, _height = await browser.evaluate(BOX % json.dumps(target))
            await drop(one, x, y)
            seen["rail_note"] = await said("exception")
            seen["rail_refs"] = refs(SMART)
            seen["rail_after"] = await browser.evaluate(
                "getComputedStyle(document.querySelector('.console-rail-drops')).display")

            await browser.navigate(instance.console_url("/console?view=tables"))
            await browser.wait_for(API + ".getDisplayedRowCount() > 0", timeout=60.0)
            await settled()
            table = await grab("t-a1", "game")
            await let_go(table)

            await browser.navigate(instance.console_url(
                f"/console?view=collections&collection={quote(HAND)}"))
            await browser.wait_for("document.body.innerText.includes('Add Games')",
                                   timeout=60.0)
            await settled()
            rows = "[data-drop-list] .console-member-row"
            x, _y, top, _height = await browser.evaluate(
                BOX.replace("querySelector(%s)", "querySelectorAll(%s)[1]")
                % json.dumps(rows))
            await drop(both, x, top + 4)
            seen["placed_note"] = await said("Added 2 games")
            seen["placed"] = refs(HAND)
            await settled()

            zone = "[data-drop-collection]"
            x, y, _top, _height = await browser.evaluate(BOX % json.dumps(zone))
            await drop(table, x, y)
            await said("Added to")
            await settled()
            seen["table_refs"] = refs(HAND)

            elsewhere = {"items": [{"mimeType": "text/uri-list",
                                    "data": "http://elsewhere.example:8001/console?view=games"
                                            "&game=bravo"}], "dragOperationsMask": 1}
            await drop(elsewhere, x, y)
            seen["refused"] = await said("another VPinFE")
        return seen

    def test_a_drag_carries_each_row_s_console_address(self) -> None:
        lines = self.seen["payload"]["text/uri-list"].split("\r\n")
        found = sorted(parse_qs(urlparse(line).query)["game"][0] for line in lines)
        self.assertEqual(["alpha", "delta"], found)
        self.assertTrue(all("view=games" in line for line in lines))
        self.assertEqual(2, len(json.loads(self.seen["payload"]["application/json"])["rows"]))

    def test_the_rail_opens_into_the_collections_while_rows_are_dragged(self) -> None:
        self.assertIn([f"settings_suggest / {SMART}", True], self.seen["rail"])
        self.assertIn([HAND, True], self.seen["rail"])
        self.assertEqual("none", self.seen["rail_after"])

    def test_a_drop_on_the_rail_adds_through_the_one_add(self) -> None:
        text, classes = self.seen["rail_note"]
        self.assertIn(f"Added to “{SMART}” as an exception to its rules", text)
        self.assertIn("bg-warning", classes)
        self.assertIn(("delta", "", "named"), self.seen["rail_refs"])

    def test_a_drop_in_a_list_kept_in_its_order_lands_where_it_was_let_go(self) -> None:
        self.assertTrue(self.seen["lines"][1])
        order = [game for game, _t, origin in self.seen["placed"] if origin == "named"]
        self.assertEqual("bravo", order[0])
        self.assertEqual({"alpha", "delta"}, set(order[1:3]))
        self.assertEqual("charlie", order[3])

    def test_a_dragged_table_goes_in_held_to_that_table(self) -> None:
        self.assertIn(("alpha", "t-a1", "named"), self.seen["table_refs"])

    def test_rows_from_another_install_are_refused(self) -> None:
        text, classes = self.seen["refused"]
        self.assertIn("nothing was added", text)
        self.assertIn("bg-warning", classes)


if __name__ == "__main__":
    unittest.main()
