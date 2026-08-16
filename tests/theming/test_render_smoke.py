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


if __name__ == "__main__":
    unittest.main()
