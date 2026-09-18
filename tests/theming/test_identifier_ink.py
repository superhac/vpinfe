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


class IdentifierInkTests(unittest.TestCase):
    """Slow: boots a real instance and a real browser."""

    def _look(self, instance, unpin=False):
        async def run():
            async with BrowserSession(chromium_path()) as browser:
                await browser.navigate(instance.console_url("/console?view=games"))
                await browser.wait_for(
                    "document.querySelectorAll('.ag-cell').length > 2", timeout=90.0)
                await asyncio.sleep(3)
                if unpin:
                    await browser.evaluate(OPEN_MENU)
                    await asyncio.sleep(1.5)
                    await browser.click(".console-menu-item", nth=0)
                    await asyncio.sleep(2)
                return json.loads(await browser.evaluate(READ))
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
                seen = self._look(instance)
        self.assertIsNotNone(seen["marked"], "no column carries the identifier class")
        self.assertEqual(seen["ink"], seen["marked"])
        self.assertEqual(seen["ink2"], seen["plain"])
        self.assertNotEqual(seen["marked"], seen["plain"])

    def test_unpinning_it_does_not_take_its_ink_away(self) -> None:
        if not chromium_path():
            self.skipTest("no Chromium on this machine")
        with TemporaryDirectory() as tmp:
            with LiveInstance(self._instance(tmp)) as instance:
                seen = self._look(instance, unpin=True)
        self.assertFalse(seen["markedPinned"], "the column did not actually unpin")
        self.assertEqual(seen["ink"], seen["marked"])


if __name__ == "__main__":
    unittest.main()
