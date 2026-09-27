"""The column a row is scanned by renders at --ink, pinned or not.

Unpinning it is the defect this replaced: brightness used to come from
`.ag-pinned-left-cols-container`, and the header menu offers pinning on every
column.
"""

from __future__ import annotations

import asyncio
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from tests.support.browser_session import BrowserSession, chromium_path
from tests.support.console_walk import ConsoleWalk, clicked
from tests.support.library import write_game
from tests.support.live_instance import LiveInstance

GAME = "Attack from Mars"

# Compared against the palette as served, never against a literal.
READ = """(() => {
  const cs = getComputedStyle(document.documentElement);
  const hex = s => '#' + (s.match(/\\d+/g) || ['0','0','0']).slice(0, 3)
      .map(n => (+n).toString(16).padStart(2, '0')).join('');
  const marked = document.querySelector('.ag-cell.console-cell-identifier');
  const plain = [...document.querySelectorAll('.ag-cell:not(.console-cell-identifier)')]
      .find(c => (c.innerText || '').trim().length);
  return JSON.stringify({
    ink: cs.getPropertyValue('--ink').trim().toLowerCase(),
    ink2: cs.getPropertyValue('--ink-2').trim().toLowerCase(),
    marked: marked ? hex(getComputedStyle(marked).color) : null,
    markedPinned: marked ? !!marked.closest('.ag-pinned-left-cols-container') : null,
    plain: plain ? hex(getComputedStyle(plain).color) : null,
  });
})()"""

# Through the header menu, which is the only way a user can do this.
OPEN_MENU = """(() => {
  const id = document.querySelector('.ag-cell.console-cell-identifier')
      .getAttribute('col-id');
  const header = document.querySelector('.ag-header-cell[col-id="' + id + '"]');
  header.dispatchEvent(
      new MouseEvent('contextmenu', {bubbles: true, clientX: 320, clientY: 180}));
  return id;
})()"""
MENU_SHOWN = ("[...document.querySelectorAll('.console-menu-item')]"
              ".some(item => item.getClientRects().length > 0)")

# The identifier column's side as the grid holds it: "left", or null.
PINNED = """(async () => {
  const grid = document.querySelector('.ag-root-wrapper').closest('[id^=c]');
  const col = document.querySelector('.ag-cell.console-cell-identifier')
      .getAttribute('col-id');
  const state = await runMethod(Number(grid.id.slice(1)), 'run_grid_method',
                                ['getColumnState']);
  return (state.find(c => c.colId === col) || {}).pinned ?? null;
})()"""

WIDE ={"width": 1920, "height": 1080, "deviceScaleFactor": 1, "mobile": False}


class IdentifierInkTests(unittest.TestCase):
    """Slow: boots a real instance and a real browser."""

    def _look(self, instance) -> tuple[dict, dict]:
        """What the grid shows with the identifier column pinned, and once its header
        menu has unpinned it."""
        async def read(browser: BrowserSession) -> dict:
            return {**json.loads(await browser.evaluate(READ)),
                    "pinned": await browser.evaluate(PINNED)}

        async def run():
            async with BrowserSession(chromium_path()) as browser:
                await browser.send("Emulation.setDeviceMetricsOverride", WIDE)
                walk = ConsoleWalk(browser, instance)
                await walk.visit("/console?view=games")
                pinned = await read(browser)
                self.assertEqual(pinned["pinned"], "left",
                                 "the column is not pinned, so there is nothing to unpin")
                await walk.act(clicked(browser, OPEN_MENU), until=MENU_SHOWN)
                await walk.act(lambda: browser.click(".console-menu-item", nth=0),
                               until=f"(async () => (await {PINNED}) === null)()")
                return pinned, await read(browser)
        return asyncio.run(run())

    def _instance(self, tmp):
        root = Path(tmp)
        write_game(root, GAME)
        return root

    def test_the_marked_column_is_brighter_than_the_facts_beside_it(self) -> None:
        if not chromium_path():
            self.skipTest("no Chromium on this machine")
        with TemporaryDirectory() as tmp:
            with LiveInstance(self._instance(tmp)) as instance:
                states = self._look(instance)
        for name, seen in zip(("pinned", "unpinned"), states, strict=True):
            with self.subTest(name):
                self.assertIsNotNone(seen["marked"], "no column carries the identifier class")
                self.assertEqual(seen["ink"], seen["marked"])
                self.assertEqual(seen["ink2"], seen["plain"])
                self.assertNotEqual(seen["marked"], seen["plain"])

    def test_unpinning_it_does_not_take_its_ink_away(self) -> None:
        if not chromium_path():
            self.skipTest("no Chromium on this machine")
        with TemporaryDirectory() as tmp:
            with LiveInstance(self._instance(tmp)) as instance:
                pinned, seen = self._look(instance)
        self.assertTrue(pinned["markedPinned"], "the pinned column was drawn unpinned")
        self.assertIsNone(seen["pinned"])
        self.assertFalse(seen["markedPinned"], "the column did not actually unpin")
        self.assertEqual(seen["ink"], seen["marked"])


if __name__ == "__main__":
    unittest.main()
