"""A hub and a player as separate processes, the player with no library of its own.

This is the gate the residency work was built against: if a frontend holding no games
renders the hub's, the split is real rather than vocabulary. Everything else can pass
with both halves in one process reading one disk, which is what makes running two worth
the seconds it costs.

Two real instances, each `main.py --headless` with its own config, ports and library
root. The player's root is empty on purpose - every game the browser draws came over
HTTP, because there is nowhere else it could have come from.
"""

from __future__ import annotations

import asyncio
import json
import sys
import unittest
import urllib.request
from pathlib import Path

from tests.support.browser_session import BrowserSession, chromium_path
from tests.support.library import TempTree, write_game
from tests.support.live_instance import LiveInstance

TITLES = ("Attack from Mars", "Medieval Madness", "Twilight Zone")

# A 1x1 PNG, so the wheel has something to draw.
PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000001000000010806000000"
    "1f15c4890000000a49444154789c6300010000050001"
    "0d0a2db40000000049454e44ae426082")

# Same scope as the render smoke test, and for the same reason recorded there.
_UNSUPPORTED = sys.platform.startswith("win")


def _info(title: str) -> dict:
    return {"Info": {"Title": title, "Manufacturer": "Bally", "Year": "1995",
                     "Type": "SS", "Themes": ["Space"]},
            "User": {"Rating": 4},
            "vpinfe": {"game_id": title[:10].replace(" ", "")}}


def _fetch(url: str):
    with urllib.request.urlopen(url, timeout=30) as handle:
        return json.load(handle)


@unittest.skipIf(_UNSUPPORTED, "scoped to Linux and macOS, as the render smoke test is")
@unittest.skipIf(chromium_path() is None, "no Chromium on this machine")
class SeparationTests(TempTree):
    """Slow by nature: two processes, each booting a real instance, and a browser.

    Seen failing once in a full-suite run on 2026-08-11 and not reproduced since - six
    consecutive suite runs and four in isolation after it. Not diagnosed, so not fixed:
    recorded here rather than guessed at, and the timeouts were already generous enough
    that a slow machine is not the obvious answer. If it recurs, `_diagnose` prints the
    page's failed requests, its console and the player's log, which is what a real
    diagnosis would start from.
    """

    READY_TIMEOUT = 90.0

    def setUp(self) -> None:
        super().setUp()
        self.hub_root = Path(self.root) / "hub-library"
        self.player_root = Path(self.root) / "player-library"
        self.hub_root.mkdir()
        self.player_root.mkdir()          # and nothing is ever written into it

        for title in TITLES:
            write_game(self.hub_root, f"{title} (Bally 1995)", info=_info(title),
                       medias={"wheel.png": PNG, "table.png": PNG})

    def test_a_player_with_no_library_renders_the_hub_s(self) -> None:
        with LiveInstance(self.hub_root) as hub:
            hub.wait_for_api()
            hub_api = f"http://127.0.0.1:{hub.ports['manager']}"
            self.assertEqual(_fetch(f"{hub_api}/api/v1/library/entries")["count"],
                             len(TITLES),
                             "the hub has to hold the library, or this proves nothing")

            with LiveInstance(self.player_root,
                              extra_settings={("network", "hub_url"): hub_api}) as player:
                player.wait_for_api()
                # What the launcher learns from the hub's discovery document.
                player.hub_assets_port = hub.ports["assets"]
                player_api = f"http://127.0.0.1:{player.ports['manager']}"
                self.assertEqual(_fetch(f"{player_api}/api/v1/library/entries")["count"],
                                 0,
                                 "the player's own disk must be empty, or a game it "
                                 "renders might be one it already had")

                rendered, failures = self._render(player)

        self.assertEqual(rendered, str(len(TITLES)),
                         "the player drew a wheel of games it does not have a copy of")
        self.assertEqual(failures, [])

    def _render(self, player: LiveInstance):
        """Open the player's playfield window and read back what the theme drew."""
        async def run():
            async with BrowserSession(chromium_path()) as browser:
                await browser.navigate(player.theme_url("playfield"))
                try:
                    await browser.wait_for("document.body.dataset.ready === 'true'",
                                           timeout=self.READY_TIMEOUT)
                except TimeoutError as exc:
                    raise AssertionError(self._diagnose(exc, browser, player)) from exc
                data = await browser.body_data()
                return data.get("rendered"), list(browser.failed_requests)

        return asyncio.run(run())

    def _diagnose(self, exc, browser, instance) -> str:
        lines = [f"the player never finished starting: {exc}",
                 f"  failed requests: {browser.failed_requests[:6] or 'none'}",
                 "  console:"]
        lines += [f"    {line[:160]}" for line in browser.console[:15]] or ["    (silent)"]
        lines += ["  player log:"]
        lines += [f"    {line[:160]}" for line in instance.output().splitlines()[-15:]]
        return "\n".join(lines)


if __name__ == "__main__":
    unittest.main()
