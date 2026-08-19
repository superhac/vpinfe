"""A hub and a device as separate processes, the device with no library of its own.

This is the gate the residency work was built against: if a frontend holding no games
renders the hub's, the split is real rather than vocabulary. Everything else can pass
with both halves in one process reading one disk, which is what makes running two worth
the seconds it costs.

Two real instances, each `main.py --headless` with its own config, ports and library
root. The device's root is empty on purpose - every game the browser draws came over
HTTP, because there is nowhere else it could have come from.
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
import unittest
import urllib.error
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


def _post(url: str) -> tuple[int, str]:
    """(status, error code) for a POST that is expected to be refused."""
    request = urllib.request.Request(url, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=30) as handle:
            return handle.status, ""
    except urllib.error.HTTPError as exc:
        return exc.code, (json.load(exc).get("error") or {}).get("code", "")


@unittest.skipIf(_UNSUPPORTED, "scoped to Linux and macOS, as the render smoke test is")
@unittest.skipIf(chromium_path() is None, "no Chromium on this machine")
class SeparationTests(TempTree):
    """Slow by nature: two processes, each booting a real instance, and a browser.

    Seen failing once in a full-suite run on 2026-08-11 and not reproduced since - six
    consecutive suite runs and four in isolation after it. Not diagnosed, so not fixed:
    recorded here rather than guessed at, and the timeouts were already generous enough
    that a slow machine is not the obvious answer. If it recurs, `_diagnose` prints the
    page's failed requests, its console and the device's log, which is what a real
    diagnosis would start from.
    """

    READY_TIMEOUT = 90.0

    def setUp(self) -> None:
        super().setUp()
        self.hub_root = Path(self.root) / "hub-library"
        self.device_root = Path(self.root) / "device-library"
        self.hub_root.mkdir()
        self.device_root.mkdir()          # and nothing is ever written into it

        for title in TITLES:
            write_game(self.hub_root, f"{title} (Bally 1995)", info=_info(title),
                       medias={"wheel.png": PNG, "table.png": PNG})

    def test_a_device_with_no_library_renders_the_hub_s(self) -> None:
        with LiveInstance(self.hub_root) as hub:
            hub.wait_for_api()
            hub_api = f"http://127.0.0.1:{hub.ports['manager']}"
            self.assertEqual(_fetch(f"{hub_api}/api/v1/library/entries")["count"],
                             len(TITLES),
                             "the hub has to hold the library, or this proves nothing")

            with LiveInstance(self.device_root,
                              extra_settings={("network", "hub_url"): hub_api}) as device:
                device.wait_for_api()
                # What the launcher learns from the hub's discovery document.
                device.hub_assets_port = hub.ports["assets"]
                device_api = f"http://127.0.0.1:{device.ports['manager']}"
                self.assertEqual(_fetch(f"{device_api}/api/v1/library/entries")["count"],
                                 0,
                                 "the device's own disk must be empty, or a game it "
                                 "renders might be one it already had")

                rendered, failures = self._render(device)

        self.assertEqual(rendered, str(len(TITLES)),
                         "the device drew a wheel of games it does not have a copy of")
        self.assertEqual(failures, [])

    def test_two_devices_share_one_hub_without_sharing_each_other(self) -> None:
        """The stronger version of the gate: anything assuming there is one device fails
        here and nowhere else.

        Both render the same library, so the hub really is serving two. Then one launches
        and the other must not report it - `launch_state` is a module-level singleton, and
        the question this answers is whether one per process is enough. It is, because a
        device is a process; a shared launch state would show up as the idle device
        claiming the other's game.
        """
        with LiveInstance(self.hub_root) as hub:
            hub_api = f"http://127.0.0.1:{hub.ports['manager']}"
            hub.wait_for_api()

            with LiveInstance(self.device_root,
                              extra_settings={("network", "hub_url"): hub_api}) as one, \
                 LiveInstance(self.device_root,
                              extra_settings={("network", "hub_url"): hub_api}) as two:
                for device in (one, two):
                    device.wait_for_api()
                    device.hub_assets_port = hub.ports["assets"]

                self.assertNotEqual(one.ports["manager"], two.ports["manager"],
                                    "two devices on one machine need their own ports")

                # Both draw the hub's library, neither holding a copy of it.
                for label, device in (("first", one), ("second", two)):
                    with self.subTest(device=label):
                        rendered, failures = self._render(device)
                        self.assertEqual(rendered, str(len(TITLES)))
                        self.assertEqual(failures, [])

                # Play state is answered per device, not read off a shared singleton.
                # Idle is what both report here, which on its own would pass whether or
                # not they are isolated - what makes it evidence is that each is asked.
                for label, device in (("first", one), ("second", two)):
                    with self.subTest(device=label):
                        state = _fetch(f"http://127.0.0.1:{device.ports['manager']}"
                                       "/api/v1/play/state")
                        self.assertEqual(state["launching"], False, label)
                        self.assertIsNone(state["game_name"], label)

    def test_a_device_holding_no_library_cannot_launch_from_it(self) -> None:
        """The `bundle` device kind, asserted so it is not mistaken for a broken route.

        `POST /games/{id}/launch` resolves the id against *this* install's catalog. A
        device whose library root is empty has nothing to resolve, so it renders a wheel
        it cannot launch from - correct, because the files genuinely are not there. The
        `remote` kind is the next test: same call, same route, its own mount.
        """
        with LiveInstance(self.hub_root) as hub:
            hub.wait_for_api()
            hub_api = f"http://127.0.0.1:{hub.ports['manager']}"
            game_id = _fetch(f"{hub_api}/api/v1/library/entries")["entries"][0]["game"]["id"]

            with LiveInstance(self.device_root,
                              extra_settings={("network", "hub_url"): hub_api}) as device:
                device.wait_for_api()
                status, code = _post(f"http://127.0.0.1:{device.ports['manager']}"
                                     f"/api/v1/games/{game_id}/launch")

        self.assertEqual((status, code), (404, "not_found"),
                         "a device with no files cannot launch, and says so by id")

    def test_a_device_sharing_the_library_can_reach_a_launch(self) -> None:
        """The `remote` device kind: already there, its own mount of the same share.

        Nothing new is needed to drive a chosen device over HTTP - the route resolves and
        gets as far as asking whether *this machine* can launch. It cannot here, because a
        test machine has no VPX, and that is the honest place to stop: the answer is about
        the device's own hardware rather than about the library.
        """
        with LiveInstance(self.hub_root) as hub:
            hub.wait_for_api()
            hub_api = f"http://127.0.0.1:{hub.ports['manager']}"
            game_id = _fetch(f"{hub_api}/api/v1/library/entries")["entries"][0]["game"]["id"]

            # Same library root as the hub, which is what a shared mount looks like here.
            with LiveInstance(self.hub_root,
                              extra_settings={("network", "hub_url"): hub_api}) as device:
                device.wait_for_api()
                device_api = f"http://127.0.0.1:{device.ports['manager']}"
                known = _fetch(f"{device_api}/api/v1/games/{game_id}")
                status, code = _post(f"{device_api}/api/v1/games/{game_id}/launch")

        self.assertEqual(known["id"], game_id, "the device resolves the hub's game id")
        self.assertNotEqual(status, 404,
                            "the library is right there; a 404 would mean the route "
                            "cannot see a shared mount")
        self.assertEqual((status, code), (501, "feature_unavailable"),
                         "stopped on this machine having no VPX, not on the library")

    def test_the_hub_learns_which_devices_it_is_serving(self) -> None:
        """A device registry is what turns the install_id on an event into a name someone
        recognizes. Two devices, so it is a device registry rather than a single-entry special
        case, and each has to arrive with its own identity."""
        with LiveInstance(self.hub_root) as hub:
            hub.wait_for_api()
            hub_api = f"http://127.0.0.1:{hub.ports['manager']}"
            self.assertEqual(_fetch(f"{hub_api}/api/v1/devices")["count"], 0,
                             "a hub knows nobody until someone says hello")

            with LiveInstance(self.device_root,
                              extra_settings={("network", "hub_url"): hub_api}) as one, \
                 LiveInstance(self.device_root,
                              extra_settings={("network", "hub_url"): hub_api}) as two:
                one.wait_for_api()
                two.wait_for_api()
                registry = self._registry_of(hub_api, expected=2,
                                             instances=(hub, one, two))

        self.assertEqual(len(registry), 2, "both devices, not one entry overwritten twice")
        ids = {device["install_id"] for device in registry}
        self.assertEqual(len(ids), 2, "each device announced its own identity")
        self.assertNotIn("", ids, "an install with no id is not an identity")
        for device in registry:
            self.assertTrue(device["display_name"], device)
            self.assertTrue(device["first_seen"], device)
            self.assertEqual(device["address"], "127.0.0.1",
                             "the hub records where it was reached from, not what it "
                             "was told")

    def _registry_of(self, hub_api: str, *, expected: int, timeout: float = 30.0,
                   instances=()) -> list:
        """The device registry once it holds `expected` devices. Polled because announcing is a
        background thread on each device - a fixed sleep would be a race either way.

        Failing here rather than returning a short registry, and failing with what each
        instance logged: this has timed out occasionally and "expected 2, got 1" says
        nothing about which device never announced or what stopped it. The logs exist;
        the assertion just was not reaching for them.
        """
        deadline = time.monotonic() + timeout
        devices = []
        while time.monotonic() < deadline:
            devices = _fetch(f"{hub_api}/api/v1/devices")["devices"]
            if len(devices) >= expected:
                return devices
            time.sleep(0.25)

        logs = "\n\n".join(f"--- instance {n} ---\n{inst.output(tail=3000)}"
                            for n, inst in enumerate(instances, 1))
        self.fail(f"{len(devices)} of {expected} devices announced within {timeout}s.\n"
                  f"registry: {devices}\n\n{logs}")

    def _render(self, device: LiveInstance):
        """Open the device's playfield window and read back what the theme drew."""
        async def run():
            async with BrowserSession(chromium_path()) as browser:
                await browser.navigate(device.theme_url("playfield"))
                try:
                    await browser.wait_for("document.body.dataset.ready === 'true'",
                                           timeout=self.READY_TIMEOUT)
                except TimeoutError as exc:
                    raise AssertionError(self._diagnose(exc, browser, device)) from exc
                data = await browser.body_data()
                return data.get("rendered"), list(browser.failed_requests)

        return asyncio.run(run())

    def _diagnose(self, exc, browser, instance) -> str:
        lines = [f"the device never finished starting: {exc}",
                 f"  failed requests: {browser.failed_requests[:6] or 'none'}",
                 "  console:"]
        lines += [f"    {line[:160]}" for line in browser.console[:15]] or ["    (silent)"]
        lines += ["  device log:"]
        lines += [f"    {line[:160]}" for line in instance.output().splitlines()[-15:]]
        return "\n".join(lines)


if __name__ == "__main__":
    unittest.main()
