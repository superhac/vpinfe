"""The frontend's own browser says what it plays, over the real channel, into the route."""

from __future__ import annotations

import asyncio
import sys
import time
import unittest

from common.paths import bundled
from tests.support.browser_session import BrowserSession, chromium_path
from tests.support.library import TempTree, write_game
from tests.support.live_instance import LiveInstance

# The page probes three seconds after it starts, then decodes two clips.
REPORT_TIMEOUT = 45.0
READY_TIMEOUT = 90.0
# How often the route is asked whether the page's report has arrived.
POLL_S = 0.1


def _is_bundled(path: str | None) -> bool:
    return bool(path) and str(path).startswith(str(bundled("chromium")))


@unittest.skipIf(sys.platform.startswith("win"), "the drive tests are scoped to Linux and macOS")
@unittest.skipIf(chromium_path() is None, "no Chromium on this machine")
class BrowserProbeDriveTests(TempTree):
    BOOTS_PER_TEST = ("One test, and what it waits for is the first report a fresh instance "
                      "has ever had from this browser.")

    def setUp(self) -> None:
        super().setUp()
        write_game(self.root, "Alpha Table",
                   info={"Info": {"Name": "Alpha Table"}, "VPinFE": {}, "User": {}})

    def _report(self) -> dict:
        async def run(instance: LiveInstance) -> dict:
            async with BrowserSession(chromium_path()) as browser:
                await browser.navigate(instance.theme_url("playfield"))
                await browser.wait_for("document.body.dataset.ready === 'true'",
                                       timeout=READY_TIMEOUT)
                deadline = time.time() + REPORT_TIMEOUT
                while time.time() < deadline:
                    found = instance.api("/api/v1/frontend/browser")
                    if found["state"] != "unknown":
                        return found
                    await asyncio.sleep(POLL_S)
                raise AssertionError("the page never reported what it plays:\n"
                                     + "\n".join(browser.console[-15:]))

        with LiveInstance(self.root) as instance:
            instance.wait_for_api()
            return asyncio.run(run(instance))

    def test_the_page_reports_what_this_browser_plays(self) -> None:
        found = self._report()
        self.assertIsInstance(found["formats"]["h264"], bool)
        self.assertIsInstance(found["formats"]["vp9"], bool)
        self.assertTrue(found["browser"])
        self.assertIsNotNone(found["reported_at"])
        if _is_bundled(chromium_path()):
            self.assertEqual((found["state"], found["formats"]["h264"], found["formats"]["vp9"]),
                             ("no_h264", False, True))
