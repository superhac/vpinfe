"""A real theme, in a real browser, against a real backend.

Every other test in this suite asserts on a piece. The breaks that reached the cabinet
were between the pieces, and all of them were only visible by looking: two hardcoded
`(bg|dmd|table)` lists meant no contract 2 theme could run at all while 907 Python and 95
JavaScript tests stayed green, and the next session found six more the same way.

So this starts `main.py --headless` against a throwaway library, opens the harness theme
in headless Chromium, and asserts the things a screenshot would have shown: the wheel
rendered, every request the page made returned a status, the media a theme asks for by
kind resolves, and moving the wheel moves it.

Skipped where there is no browser, so it never becomes the reason a Windows build fails.
"""

from __future__ import annotations

import asyncio
import sys
import unittest

from tests.support.browser_session import BrowserSession, chromium_path
from tests.support.library import TempTree, write_game
from tests.support.live_instance import LiveInstance

# A 1x1 PNG. Real bytes, because the point is that the browser fetches and decodes it.
PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
    "890000000a49444154789c6360000002000100fd5c9a6b0000000049454e44ae426082")

GAMES = ("Alpha Table", "Beta Table", "Gamma Table")


def _info(name: str) -> dict:
    return {"Info": {"Name": name, "Manufacturer": "Test", "Year": "1999"},
            "VPinFE": {}, "User": {}}


# Windows is out by design, not by accident. This was scoped to Linux from the start and
# a cabinet is not a Windows box - but the honest reason is that the runner kills the
# test process partway through with no summary and no traceback, and I have not found out
# why. Diagnosing it costs a push per attempt for a platform this test was never meant to
# gate. Recorded rather than quietly excluded: if VPinFE ever needs this on Windows, that
# is the thing to work out first.
_UNSUPPORTED = sys.platform.startswith("win")


@unittest.skipIf(_UNSUPPORTED, "the render smoke test is scoped to Linux and macOS")
@unittest.skipIf(chromium_path() is None, "no Chromium on this machine")
class RenderSmokeTests(TempTree):
    """Each test boots its own instance: they assert on different windows and a
    shared one would let the first test's state decide the second's result."""

    def setUp(self) -> None:
        super().setUp()
        for name in GAMES:
            write_game(self.root, name, info=_info(name),
                       medias={"wheel.png": PNG, "table.png": PNG})

    # CI runs several times slower than a laptop, and this waits on a real app booting
    # and a real browser rendering. Generous rather than tuned: a flaky timeout would
    # teach everyone to ignore this test, which is worse than it being slow.
    READY_TIMEOUT = 90.0

    async def _open(self, browser: BrowserSession, instance: LiveInstance, window: str):
        """Open a window and wait for the theme to say it finished starting."""
        await browser.navigate(instance.theme_url(window))
        try:
            await browser.wait_for("document.body.dataset.ready === 'true'",
                                   timeout=self.READY_TIMEOUT)
        except TimeoutError as exc:
            raise AssertionError(self._diagnose(exc, browser, instance, window)) from exc

    def _diagnose(self, exc, browser, instance, window) -> str:
        """Say what the page and the instance were doing. A bare timeout sent the last
        CI failure back to guesswork, and guessing costs a push per attempt."""
        lines = [f"{window} never finished starting: {exc}",
                 f"  failed requests: {browser.failed_requests[:6] or 'none'}",
                 "  console:"]
        lines += [f"    {line[:160]}" for line in browser.console[:15]] or ["    (silent)"]
        lines += ["  instance log:"]
        lines += [f"    {line[:160]}" for line in instance.output().splitlines()[-15:]]
        return "\n".join(lines)

    def _drive(self, window: str = "playfield"):
        """Boot, open the window, and hand back what the page and the browser saw."""
        async def run(instance: LiveInstance):
            async with BrowserSession(chromium_path()) as browser:
                await self._open(browser, instance, window)
                data = await browser.body_data()
                return data, browser, list(browser.failed_requests)

        with LiveInstance(self.root) as instance:
            return asyncio.run(run(instance))

    # -- the assertions a screenshot would have made ------------------------

    def test_the_wheel_renders_every_game(self) -> None:
        data, _browser, _failed = self._drive()
        self.assertEqual(data.get("rendered"), str(len(GAMES)),
                         f"the page rendered {data.get('rendered')} entries, not "
                         f"{len(GAMES)}; body was {data}")

    def test_the_theme_reports_no_failure_of_its_own(self) -> None:
        """The harness writes what went wrong into the body rather than throwing into a
        console nobody reads - a theme that throws at startup renders nothing, which
        looks exactly like a blank screen."""
        data, _browser, _failed = self._drive()
        self.assertIsNone(data.get("failures"), data.get("failures"))

    def test_nothing_the_page_asked_for_was_missing(self) -> None:
        """The 404 from the bootstrap that reached the cabinet is exactly this."""
        _data, _browser, failed = self._drive()
        self.assertEqual(failed, [])

    def test_the_window_knows_which_window_it_is(self) -> None:
        """`unknown` from name detection was the second half of that same break."""
        data, _browser, _failed = self._drive("playfield")
        self.assertEqual(data.get("window"), "playfield")

    def test_a_secondary_window_renders_too(self) -> None:
        """Blank backglass and scoreview is the break the next session found."""
        data, _browser, failed = self._drive("backglass")
        self.assertEqual(data.get("rendered"), str(len(GAMES)))
        self.assertEqual(failed, [])

    def test_moving_the_wheel_moves_it(self) -> None:
        async def run(instance: LiveInstance):
            async with BrowserSession(chromium_path()) as browser:
                await self._open(browser, instance, "playfield")
                before = (await browser.body_data()).get("selected")
                await browser.press("ArrowRight", "ArrowRight")
                after = await browser.wait_for(
                    f"document.body.dataset.selected !== '{before}' "
                    f"&& document.body.dataset.selected")
                return before, after

        with LiveInstance(self.root) as instance:
            before, after = asyncio.run(run(instance))
        self.assertNotEqual(before, after)

    # -- the main menu, driven the way a player drives it --------------------
    #
    #
    # Nothing loaded `mainmenu.js` before this. The JS suite covers core's overlay
    # plumbing - opening, closing, which one owns the actions - and stops at the
    # iframe boundary, so the menu's own cursor had no coverage at all.

    # Same-origin, so the menu's own document is readable from the host page.
    SELECTED = ("(document.getElementById('menu-frame')?.contentDocument"
                "?.querySelector('.menu-item.selected')?.id) || ''")

    # What the page looked like when no item was selected. Splits "the menu never
    # opened" from "it opened empty" - a bare timeout names neither, and the answer
    # costs a push per guess.
    MENU_STATE = """JSON.stringify((() => {
      const frame = document.getElementById('menu-frame');
      const doc = frame && frame.contentDocument;
      return {frame: !!frame,
              display: frame ? frame.style.display : null,
              src: frame ? frame.getAttribute('src') : null,
              readyState: doc ? doc.readyState : null,
              items: doc ? doc.querySelectorAll('.menu-item').length : null};
    })())"""

    async def _open_menu(self, browser, instance):
        await self._open(browser, instance, "playfield")
        await browser.press("m", "KeyM")
        try:
            return await browser.wait_for(self.SELECTED, timeout=self.READY_TIMEOUT)
        except TimeoutError as exc:
            state = await browser.evaluate(self.MENU_STATE)
            report = self._diagnose(exc, browser, instance, "the menu")
            raise AssertionError(f"{report}\n  menu: {state}") from exc

    def test_the_menu_opens_with_something_selected(self) -> None:
        async def run(instance):
            async with BrowserSession(chromium_path()) as browser:
                return await self._open_menu(browser, instance), list(browser.console)

        with LiveInstance(self.root) as instance:
            selected, console = asyncio.run(run(instance))
        self.assertTrue(selected, "the menu opened with no item selected")
        self.assertEqual([line for line in console if "Uncaught" in line], [])

    def test_the_menu_cursor_moves(self) -> None:
        async def run(instance):
            async with BrowserSession(chromium_path()) as browser:
                first = await self._open_menu(browser, instance)
                await browser.press("ArrowDown", "ArrowDown")
                moved = await browser.wait_for(
                    f"({self.SELECTED}) && ({self.SELECTED}) !== '{first}'")
                return first, moved

        with LiveInstance(self.root) as instance:
            first, moved = asyncio.run(run(instance))
        self.assertNotEqual(first, moved)

    def test_the_menu_cursor_wraps(self) -> None:
        """Stepping back from the first item lands on the last, not on nothing."""
        async def run(instance):
            async with BrowserSession(chromium_path()) as browser:
                first = await self._open_menu(browser, instance)
                await browser.press("ArrowUp", "ArrowUp")
                wrapped = await browser.wait_for(
                    f"({self.SELECTED}) && ({self.SELECTED}) !== '{first}'")
                return first, wrapped

        with LiveInstance(self.root) as instance:
            first, wrapped = asyncio.run(run(instance))
        self.assertNotEqual(first, wrapped)

    def test_back_closes_the_menu(self) -> None:
        async def run(instance):
            async with BrowserSession(chromium_path()) as browser:
                await self._open_menu(browser, instance)
                await browser.press("b", "KeyB")
                return await browser.wait_for(
                    "document.getElementById('menu-frame')?.style.display === 'none'")

        with LiveInstance(self.root) as instance:
            self.assertTrue(asyncio.run(run(instance)))



    # -- the collection menu, which carries a second cursor inside the first ---
    #
    # Its dropdown is a list inside a list: the rows navigate, and selecting one opens
    # a popup that navigates on the same keys. Nothing covered either.

    POPUP = ("(() => { const d = document.getElementById('collection-menu-frame')"
             "?.contentDocument; if (!d) return ''; "
             "const p = d.getElementById('dropdown-popup'); "
             "return (p && p.style.display === 'block') "
             "? (p.querySelector('.popup-option.selected')?.textContent || 'open') : ''; })()")

    COLLECTION_ROW = ("(document.getElementById('collection-menu-frame')?.contentDocument"
                      "?.querySelector('li.menu-item.selected')?.id) || ''")

    async def _open_collection_menu(self, browser, instance):
        await self._open(browser, instance, "playfield")
        await browser.press("c", "KeyC")
        return await browser.wait_for(self.COLLECTION_ROW)

    def test_the_collection_menu_opens_with_a_row_selected(self) -> None:
        async def run(instance):
            async with BrowserSession(chromium_path()) as browser:
                return await self._open_collection_menu(browser, instance)

        with LiveInstance(self.root) as instance:
            self.assertTrue(asyncio.run(run(instance)))

    def test_the_collection_menu_cursor_moves(self) -> None:
        async def run(instance):
            async with BrowserSession(chromium_path()) as browser:
                first = await self._open_collection_menu(browser, instance)
                await browser.press("ArrowDown", "ArrowDown")
                moved = await browser.wait_for(
                    f"({self.COLLECTION_ROW}) && ({self.COLLECTION_ROW}) !== '{first}'")
                return first, moved

        with LiveInstance(self.root) as instance:
            first, moved = asyncio.run(run(instance))
        self.assertNotEqual(first, moved)

    def test_the_dropdown_opens_and_its_own_cursor_moves(self) -> None:
        """The inner list. Selecting a row opens a popup that navigates on the same
        keys, and it kept a second hand-rolled cursor to do it."""
        async def run(instance):
            async with BrowserSession(chromium_path()) as browser:
                await self._open_collection_menu(browser, instance)
                await browser.press("Enter", "Enter")
                first = await browser.wait_for(self.POPUP)
                await browser.press("ArrowDown", "ArrowDown")
                moved = await browser.wait_for(
                    f"({self.POPUP}) && ({self.POPUP}) !== '{first}'")
                return first, moved

        with LiveInstance(self.root) as instance:
            first, moved = asyncio.run(run(instance))
        self.assertNotEqual(first, moved)

    def test_the_menu_says_what_a_page_press_will_do(self) -> None:
        """The only place this is visible. A page press moves by the sort's groups or by
        a count, and which one depends on the collection - so it is told, not guessed."""
        async def run(instance):
            async with BrowserSession(chromium_path()) as browser:
                await self._open_collection_menu(browser, instance)
                return await browser.wait_for(
                    "(document.getElementById('collection-menu-frame')?.contentDocument"
                    "?.getElementById('paging-state')?.textContent) || ''")

        with LiveInstance(self.root) as instance:
            said = asyncio.run(run(instance))
        self.assertTrue(said.startswith("Pages "), f"the menu said {said!r}")

    def test_back_closes_the_dropdown_before_the_menu(self) -> None:
        """Two nested lists, so back has to unwind one at a time."""
        async def run(instance):
            async with BrowserSession(chromium_path()) as browser:
                await self._open_collection_menu(browser, instance)
                await browser.press("Enter", "Enter")
                await browser.wait_for(self.POPUP)
                await browser.press("b", "KeyB")
                closed = await browser.wait_for(f"!({self.POPUP})")
                still_open = await browser.evaluate(
                    "document.getElementById('collection-menu-frame')?.style.display")
                return closed, still_open

        with LiveInstance(self.root) as instance:
            closed, still_open = asyncio.run(run(instance))
        self.assertTrue(closed)
        self.assertEqual(still_open, "block", "back closed the whole menu, not the popup")

    # -- what a frame throws reaches the log -------------------------------
    #
    # An overlay is an iframe with its own console, and nothing reads it on a cabinet.
    # A ReferenceError in the menu left it not responding to any key with a clean log;
    # the only clue was pressing a button and watching nothing happen.

    def test_an_overlay_that_throws_says_so_in_the_log(self) -> None:
        async def run(instance):
            async with BrowserSession(chromium_path()) as browser:
                await self._open_menu(browser, instance)
                # eval inside the frame, so the closure belongs to the frame's realm.
                # Passing a parent-defined callback to contentWindow.setTimeout reports
                # the error on the *parent* - which passes this test while proving
                # nothing about the overlay path it is named for.
                await browser.evaluate(
                    'document.getElementById("menu-frame").contentWindow.eval('
                    '"setTimeout(function () { throw new Error(\'menu exploded\'); }, 0)")')
                await asyncio.sleep(1.5)

        with LiveInstance(self.root) as instance:
            asyncio.run(run(instance))
            log = instance.output()
        self.assertIn("[playfield/menu] threw", log,
                      "the fault has to name the overlay, or it reads as the theme's")
        self.assertIn("menu exploded", log)

    def test_the_theme_page_reports_its_own_throws(self) -> None:
        async def run(instance):
            async with BrowserSession(chromium_path()) as browser:
                await self._open(browser, instance, "playfield")
                await browser.evaluate(
                    "setTimeout(() => { throw new Error('theme exploded'); }, 0)")
                await asyncio.sleep(1.5)

        with LiveInstance(self.root) as instance:
            asyncio.run(run(instance))
            log = instance.output()
        self.assertIn("theme exploded", log)


if __name__ == "__main__":
    unittest.main()
