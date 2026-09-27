"""What a grid writes to `ui-preferences.json`, in a real browser: nothing on a load,
a view switch or a column turned on, and the person's own layout when they change it.

Slow: boots a real instance and a real browser.
"""

from __future__ import annotations

import asyncio
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import quote

from console import collections, grid
from tests.support.browser_session import BrowserSession, chromium_path
from tests.support.library import game_info, write_game
from tests.support.live_instance import LiveInstance

COLLECTION = "Probe"
BY_LINK = (f"/console?view=collections&collection={quote(COLLECTION)}"
           "&section=collection_details")
SELECTION = "ag-Grid-SelectionColumn"
API = ("(() => { const el = document.querySelector('.nicegui-aggrid');"
       " return getElement(Number(el.id.slice(1))).api; })()")
PINNED_ON_SCREEN = ("Object.fromEntries(" + API + ".getColumnState()"
                    ".map(s => [s.colId, s.pinned]))")
# The handle's left edge: the last pinned column's handle hangs past the pinned area,
# which clips the half that does.
EDGE_OF = ("(() => { const el = document.querySelector("
           "'.ag-header-cell[col-id=\"%s\"] .ag-header-cell-resize');"
           " if (!el) return null; const box = el.getBoundingClientRect();"
           " return [box.left + 2, box.top + box.height / 2]; })()")
HEADER_OF = ("(() => { const el = document.querySelector("
             "'.ag-header-cell[col-id=\"%s\"]'); if (!el) return null;"
             " const box = el.getBoundingClientRect();"
             " return [box.left + box.width / 2, box.top + box.height / 2]; })()")
PICK = ("(() => { const i = [...document.querySelectorAll(%s)]"
        ".findIndex(el => el.innerText.trim() === %s); return i >= 0 ? i + 1 : 0; })()")


class GridLayoutDrive(unittest.TestCase):
    seen: dict = {}

    @classmethod
    def setUpClass(cls) -> None:
        if not chromium_path():
            raise unittest.SkipTest("no Chromium on this machine")
        with TemporaryDirectory() as tmp:
            for title in ("Alpha", "Bravo", "Charlie"):
                write_game(Path(tmp), title,
                           info=game_info(title, vps_id="", game_id=title.lower()))
            with LiveInstance(Path(tmp)) as instance:
                cls.seen = asyncio.run(cls._drive(instance))

    @classmethod
    async def _drive(cls, instance: LiveInstance) -> dict:
        seen: dict = {}
        instance.wait_for_api()
        instance.post("/api/v1/collections", {"name": COLLECTION, "games": ["alpha"]})
        stored = instance.config_dir / "ui-preferences.json"

        def stamp() -> tuple:
            if not stored.exists():
                return (None, None)
            return (stored.stat().st_mtime_ns, stored.read_bytes())

        def scopes() -> dict:
            return json.loads(stored.read_text())["scopes"] if stored.exists() else {}

        async with BrowserSession(chromium_path()) as browser:
            async def settled() -> None:
                await asyncio.sleep(4.0)

            async def load(path: str) -> None:
                await browser.navigate(instance.console_url(path))
                await browser.wait_for(API + ".getDisplayedRowCount() > 0", timeout=90.0)
                await settled()

            async def unchanged_by(step) -> bool:
                before = stamp()
                await step()
                return stamp() == before

            async def click_text(selector: str, text: str) -> None:
                at = await browser.wait_for(PICK % (json.dumps(selector), json.dumps(text)))
                await browser.click(selector, nth=int(at) - 1)

            async def mouse(kind: str, x: float, y: float, button: str = "left",
                            held: bool = False) -> None:
                await browser.send("Input.dispatchMouseEvent",
                                   {"type": kind, "x": x, "y": y, "button": button,
                                    "buttons": 1 if held else 0, "clickCount": 1})

            seen["first_load"] = await unchanged_by(
                lambda: load("/console?view=collections"))
            seen["by_link"] = await unchanged_by(lambda: load(BY_LINK))
            seen["assets"] = await unchanged_by(lambda: load("/console?view=assets"))

            async def turn_a_column_on() -> None:
                await load("/console?view=tables")
                await browser.click(".console-view-menu")
                await asyncio.sleep(0.8)
                at = await browser.evaluate(
                    "[...document.querySelectorAll('.q-menu .q-checkbox')]"
                    ".findIndex(c => c.getAttribute('aria-checked') === 'false')")
                await browser.click(".q-menu .q-checkbox", nth=int(at))
                await settled()

            seen["column_on"] = await unchanged_by(turn_a_column_on)
            seen["column_on_picker"] = await browser.evaluate(
                "document.querySelector('.console-view-picker').innerText")

            await browser.send("Emulation.setDeviceMetricsOverride",
                               {"width": 1024, "height": 720, "deviceScaleFactor": 1,
                                "mobile": False})
            seen["narrow"] = await unchanged_by(lambda: load(BY_LINK))
            seen["narrow_on_screen"] = await browser.evaluate(PINNED_ON_SCREEN)

            before = scopes()
            await browser.evaluate(API + ".ensureColumnVisible('name', 'end')")
            await asyncio.sleep(0.5)
            x, y = await browser.wait_for(EDGE_OF % "name")
            await mouse("mouseMoved", x, y)
            await mouse("mousePressed", x, y, held=True)
            for step in range(1, 9):
                await mouse("mouseMoved", x - 5 * step, y, held=True)
                await asyncio.sleep(0.05)
            await mouse("mouseReleased", x - 40, y)
            await settled()
            seen["resized"] = (before, scopes())
            seen["resized_on_screen"] = await browser.evaluate(PINNED_ON_SCREEN)

            await browser.evaluate(API + ".ensureColumnVisible('kind')")
            await asyncio.sleep(0.5)
            x, y = await browser.wait_for(HEADER_OF % "kind")
            for kind in ("mousePressed", "mouseReleased"):
                await mouse(kind, x, y, button="right")
            await click_text(".q-menu .console-menu-item", "Pin left")
            await settled()
            seen["pinned"] = scopes()
        return seen

    def _layout(self, held: dict) -> dict:
        found = [value for key, value in held.items()
                 if key.startswith("console.collections::")]
        self.assertEqual(1, len(found), sorted(held))
        return found[0]

    def test_a_load_writes_nothing(self) -> None:
        self.assertTrue(self.seen["first_load"])

    def test_opening_a_collection_by_link_writes_nothing(self) -> None:
        self.assertTrue(self.seen["by_link"])

    def test_the_assets_page_writes_no_widths_on_a_load(self) -> None:
        self.assertTrue(self.seen["assets"])

    def test_a_column_turned_on_marks_the_view_modified_and_writes_nothing(self) -> None:
        self.assertTrue(self.seen["column_on"])
        self.assertIn("modified", self.seen["column_on_picker"])

    def test_a_narrow_window_unpins_on_screen_and_writes_nothing(self) -> None:
        self.assertIsNone(self.seen["narrow_on_screen"][SELECTION])
        self.assertTrue(self.seen["narrow"])

    def test_a_resize_saves_that_width_and_not_the_unpins_a_narrow_window_made(self) -> None:
        before, after = self.seen["resized"]
        self.assertEqual({}, {k: v for k, v in before.items() if "::" in k})
        layout = self._layout(after)
        self.assertEqual(["widths"], sorted(layout))
        self.assertEqual(["name"], sorted(layout["widths"]))
        self.assertLess(layout["widths"]["name"], _declared("name"))
        self.assertIsNone(self.seen["resized_on_screen"][SELECTION])

    def test_pinning_from_the_header_menu_is_saved(self) -> None:
        layout = self._layout(self.seen["pinned"])
        self.assertEqual({"kind": "left"}, layout["pins"])


def _declared(field: str) -> int:
    """The width a fresh instance declares, which draws art in its lists."""
    return next(one["width"] for one in grid.with_art(collections.COLUMNS, True)
                if one["field"] == field)


if __name__ == "__main__":
    unittest.main()
