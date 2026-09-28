"""Two installs as separate processes, one with no library of its own.

This is the gate the residency work was built against: if a frontend holding no games
renders the other's, the split is real rather than vocabulary. Everything else can pass
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
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path

import requests

from tests.support.browser_session import BrowserSession, chromium_path
from tests.support.library import TempTree, write_game
from tests.support.live_instance import LiveInstance

TITLES = ("Attack from Mars", "Medieval Madness", "Twilight Zone")

# A 1x1 PNG, so the wheel has something to draw.
PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000001000000010806000000"
    "1f15c4890000000a49444154789c6300010000050001"
    "0d0a2db40000000049454e44ae426082")

# The titles the device's wheel holds, in order.
SHOWN = ("(async () => JSON.parse(await vpin.call('get_tables'))"
         ".entries.map(entry => entry.game.name))")
THREE_SHOWN = f"(async () => (await {SHOWN}()).length === 3)()"

_A_PUSH_LANDS_S = 0.5
_LIMIT_S = 30.0
_STARTED = "Press Ctrl+C to stop"


@dataclass(frozen=True)
class Until:
    """A step that waits up to `_LIMIT_S` for `expression` to hold in the page, and
    lets the steps after it report what it found if it never does."""
    expression: str

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


def _patch(url: str, body: dict) -> None:
    requests.patch(url, json=body, timeout=30).raise_for_status()


def _started(instance: LiveInstance) -> None:
    """Until the instance logs that its startup is done."""
    deadline = time.monotonic() + _LIMIT_S
    while _STARTED not in instance.output(tail=None):
        if time.monotonic() > deadline:
            raise AssertionError(f"the instance never logged {_STARTED!r}:\n"
                                 + instance.output())
        time.sleep(0.05)


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

    BOOTS_PER_TEST = ("Each test builds its own hub and devices - collections written to "
                      "the hub or to a device's own file, a second device, a hub that "
                      "stops - and a shared hub would carry one test's collections into "
                      "the next.")
    READY_TIMEOUT = 90.0

    def setUp(self) -> None:
        super().setUp()
        self.library_root = Path(self.root) / "console-library"
        self.device_root = Path(self.root) / "device-library"
        self.library_root.mkdir()
        self.device_root.mkdir()          # and nothing is ever written into it

        for title in TITLES:
            write_game(self.library_root, f"{title} (Bally 1995)", info=_info(title),
                       medias={"wheel.png": PNG, "table.png": PNG})

    def test_a_device_with_no_library_renders_the_hub_s(self) -> None:
        with LiveInstance(self.library_root) as library:
            library.wait_for_api()
            library_api = f"http://127.0.0.1:{library.ports['manager']}"
            self.assertEqual(_fetch(f"{library_api}/api/v1/library/entries")["count"],
                             len(TITLES),
                             "that install has to hold the library, or this proves nothing")

            with LiveInstance(self.device_root,
                              extra_settings={("network", "library_url"): library_api}) as device:
                device.wait_for_api()
                # What the launcher learns from the library's discovery document.
                device.library_files_port = library.ports["assets"]
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

        Both render the same library, so it really is serving two. Then one launches
        and the other must not report it - `launch_state` is a module-level singleton, and
        the question this answers is whether one per process is enough. It is, because a
        device is a process; a shared launch state would show up as the idle device
        claiming the other's game.
        """
        with LiveInstance(self.library_root) as library:
            library_api = f"http://127.0.0.1:{library.ports['manager']}"
            library.wait_for_api()

            with LiveInstance(self.device_root,
                              extra_settings={("network", "library_url"): library_api}) as one, \
                 LiveInstance(self.device_root,
                              extra_settings={("network", "library_url"): library_api}) as two:
                for device in (one, two):
                    device.wait_for_api()
                    device.library_files_port = library.ports["assets"]

                self.assertNotEqual(one.ports["manager"], two.ports["manager"],
                                    "two devices on one machine need their own ports")

                # Both draw the same library, neither holding a copy of it.
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
        with LiveInstance(self.library_root) as library:
            library.wait_for_api()
            library_api = f"http://127.0.0.1:{library.ports['manager']}"
            game_id = _fetch(f"{library_api}/api/v1/library/entries")["entries"][0]["game"]["id"]

            with LiveInstance(self.device_root,
                              extra_settings={("network", "library_url"): library_api}) as device:
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
        with LiveInstance(self.library_root) as library:
            library.wait_for_api()
            library_api = f"http://127.0.0.1:{library.ports['manager']}"
            game_id = _fetch(f"{library_api}/api/v1/library/entries")["entries"][0]["game"]["id"]

            # Same library root as the other install, which is what a shared mount looks like.
            with LiveInstance(self.library_root,
                              extra_settings={("network", "library_url"): library_api}) as device:
                device.wait_for_api()
                device_api = f"http://127.0.0.1:{device.ports['manager']}"
                known = _fetch(f"{device_api}/api/v1/games/{game_id}")
                status, code = _post(f"{device_api}/api/v1/games/{game_id}/launch")

        self.assertEqual(known["id"], game_id, "the reader resolves the library's game id")
        self.assertNotEqual(status, 404,
                            "the library is right there; a 404 would mean the route "
                            "cannot see a shared mount")
        self.assertEqual((status, code), (501, "feature_unavailable"),
                         "stopped on this machine having no VPX, not on the library")

    def test_an_install_registers_itself_and_nobody_else(self) -> None:
        """Nothing reports to anything any more.

        An install used to push itself into whichever registry `network.hub_url` named,
        which meant a machine that only launches games carrying the address of a machine
        that manages it. It announces itself on the network instead, and each install
        decides what to do with what it hears - so an install reading somebody's library
        writes nothing into that install's registry.

        Announcing is off in these instances: they get their own config dir so they
        cannot touch the developer's install, and appearing in its device list would be
        exactly that. What they hear is covered in `tests/api/test_discovery.py`.
        """
        with LiveInstance(self.library_root) as library:
            library.wait_for_api()
            library_api = f"http://127.0.0.1:{library.ports['manager']}"
            itself = _fetch(f"{library_api}/api/v1/devices")
            self.assertEqual(itself["count"], 1,
                             "an install knows itself before anyone says hello")
            mine = itself["devices"][0]
            self.assertTrue(mine["device_id"], "an install with no id is not an identity")
            self.assertTrue(mine["display_name"], mine)
            self.assertEqual(mine["kind"], "vpinfe", mine)

            with LiveInstance(
                    self.device_root,
                    extra_settings={("network", "library_url"): library_api}) as reader:
                reader.wait_for_api()
                _started(reader)
                time.sleep(_A_PUSH_LANDS_S)
                after = _fetch(f"{library_api}/api/v1/devices")

        self.assertEqual([d["device_id"] for d in after["devices"]],
                         [mine["device_id"]],
                         "reading a library is not registering with it")

    def test_a_device_picks_from_the_hub_s_collections(self) -> None:
        """What the device's picker lists is the hub's, drawn with the hub's art - and a
        collection only the device's own file holds is not among it."""
        with LiveInstance(self.library_root) as library:
            library.wait_for_api()
            library_api = f"http://127.0.0.1:{library.ports['manager']}"
            ids = [entry["game"]["id"] for entry in
                   _fetch(f"{library_api}/api/v1/library/entries")["entries"]]
            library.post("/api/v1/collections", {"name": "Hub Picks",
                                                 "games": [ids[2], ids[0]]})
            requests.put(f"{library_api}/api/v1/collections/Hub%20Picks/image",
                         files={"file": ("picks.png", PNG, "image/png")},
                         timeout=30).raise_for_status()
            offered = [row["name"] for row in
                       _fetch(f"{library_api}/api/v1/collections")["collections"]
                       if row["in_frontend"]]

            with LiveInstance(self.device_root,
                              extra_settings={("network", "library_url"): library_api}) as device:
                device.wait_for_api()
                device.library_files_port = library.ports["assets"]
                device.post("/api/v1/collections", {"name": "Only Here", "games": []})

                (items, drawn), failures = self._evaluate(device, (
                    "vpin.callInternal('get_collection_picker_items')",
                    """(async () => {
                         const items = await vpin.callInternal('get_collection_picker_items');
                         const load = url => new Promise(done => {
                           const img = new Image();
                           img.onload = () => done(img.naturalWidth);
                           img.onerror = () => done(0);
                           img.src = url;
                         });
                         const picks = items.find(item => item.name === 'Hub Picks');
                         const whole = items.find(item => item.name === '');
                         return Promise.all([picks.image_url, ...picks.game_wheel_urls,
                                             ...whole.game_wheel_urls].map(load));
                       })()"""))

        self.assertEqual([item["name"] for item in items], ["", *offered])
        self.assertIn("Hub Picks", offered)
        picks = next(item for item in items if item["name"] == "Hub Picks")
        self.assertEqual(picks["table_count"], 2)
        self.assertEqual(items[0]["table_count"], len(TITLES))
        self.assertEqual(drawn, [1] * (3 + len(TITLES)),
                         "the collection's image, its two wheels and every one of All "
                         "Games' load from the hub")
        self.assertEqual(failures, [])

    def test_a_device_shows_the_hub_s_collection_in_the_hub_s_order(self) -> None:
        """Picked on the device, the hub's hand-ordered collection arrives in that order
        and keeps it through a refresh - with a collection of the same name in the
        device's own file, ordered by title."""
        with LiveInstance(self.library_root) as library:
            library.wait_for_api()
            library_api = f"http://127.0.0.1:{library.ports['manager']}"
            ids = {entry["game"]["name"]: entry["game"]["id"] for entry in
                   _fetch(f"{library_api}/api/v1/library/entries")["entries"]}
            picks = [ids["Twilight Zone"], ids["Attack from Mars"]]
            library.post("/api/v1/collections", {"name": "Hub Picks", "games": picks})
            _patch(f"{library_api}/api/v1/collections/Hub%20Picks", {"order_by": "manual"})

            with LiveInstance(self.device_root,
                              extra_settings={("network", "library_url"): library_api}) as device:
                device.wait_for_api()
                device.library_files_port = library.ports["assets"]
                device_api = f"http://127.0.0.1:{device.ports['manager']}"
                device.post("/api/v1/collections", {"name": "Hub Picks", "games": []})

                def hub_adds_one_then_device_refreshes() -> None:
                    _patch(f"{library_api}/api/v1/collections/Hub%20Picks",
                           {"games": [*picks, ids["Medieval Madness"]]})
                    # Any write to the device's own collections sends its windows back
                    # for the payload.
                    _patch(f"{device_api}/api/v1/collections/Hub%20Picks",
                           {"description": "Only here"})

                (_, picked, _, _, refreshed), failures = self._evaluate(device, (
                    "vpin.call('set_tables_by_collection', 'Hub Picks')",
                    f"{SHOWN}()",
                    hub_adds_one_then_device_refreshes,
                    Until(THREE_SHOWN),
                    f"{SHOWN}()"))

        self.assertEqual(picked, ["Twilight Zone", "Attack from Mars"])
        self.assertEqual(refreshed, ["Twilight Zone", "Attack from Mars", "Medieval Madness"])
        self.assertEqual(failures, [])

    def test_a_device_s_filter_narrows_the_hub_s_library(self) -> None:
        with LiveInstance(self.library_root) as library:
            library.wait_for_api()
            library_api = f"http://127.0.0.1:{library.ports['manager']}"

            with LiveInstance(self.device_root,
                              extra_settings={("network", "library_url"): library_api}) as device:
                device.wait_for_api()
                device.library_files_port = library.ports["assets"]

                (count, shown), failures = self._evaluate(device, (
                    "vpin.callInternal('apply_filters', 'T', 'All', 'All', 'All', 'All',"
                    " 'All', false)",
                    f"{SHOWN}()"))

        self.assertEqual((count, shown), (1, ["Twilight Zone"]))
        self.assertEqual(failures, [])

    def test_a_device_s_filter_menu_offers_the_whole_hub_library(self) -> None:
        with LiveInstance(self.library_root) as library:
            library.wait_for_api()
            library_api = f"http://127.0.0.1:{library.ports['manager']}"
            ids = {entry["game"]["name"]: entry["game"]["id"] for entry in
                   _fetch(f"{library_api}/api/v1/library/entries")["entries"]}
            library.post("/api/v1/collections", {"name": "Hub Picks",
                                                 "games": [ids["Twilight Zone"]]})

            with LiveInstance(self.device_root,
                              extra_settings={("network", "library_url"): library_api}) as device:
                device.wait_for_api()
                device.library_files_port = library.ports["assets"]

                (_, letters), failures = self._evaluate(device, (
                    "vpin.call('set_tables_by_collection', 'Hub Picks')",
                    "vpin.call('get_filter_letters')"))

        self.assertEqual(letters, ["A", "M", "T"])
        self.assertEqual(failures, [])

    def test_a_hub_collection_deleted_while_shown_leaves_the_device_on_all_games(self) -> None:
        with LiveInstance(self.library_root) as library:
            library.wait_for_api()
            library_api = f"http://127.0.0.1:{library.ports['manager']}"
            ids = {entry["game"]["name"]: entry["game"]["id"] for entry in
                   _fetch(f"{library_api}/api/v1/library/entries")["entries"]}
            library.post("/api/v1/collections", {"name": "Hub Picks",
                                                 "games": [ids["Twilight Zone"]]})

            with LiveInstance(self.device_root,
                              extra_settings={("network", "library_url"): library_api}) as device:
                device.wait_for_api()
                device.library_files_port = library.ports["assets"]

                def hub_deletes_it_then_device_refreshes() -> None:
                    requests.delete(f"{library_api}/api/v1/collections/Hub%20Picks",
                                    timeout=30).raise_for_status()
                    device.post("/api/v1/collections", {"name": "Only Here", "games": []})

                (_, picked, _, _, after), failures = self._evaluate(device, (
                    "vpin.call('set_tables_by_collection', 'Hub Picks')",
                    f"{SHOWN}()",
                    hub_deletes_it_then_device_refreshes,
                    Until(THREE_SHOWN),
                    f"""(async () => [await vpin.call('get_current_collection'),
                                      await {SHOWN}()])()"""))

        self.assertEqual(picked, ["Twilight Zone"])
        self.assertEqual(after, ["None", list(TITLES)])
        self.assertEqual(failures, [])

    def test_a_filter_saved_on_a_device_is_the_hub_s_collection(self) -> None:
        with LiveInstance(self.library_root) as library:
            library.wait_for_api()
            library_api = f"http://127.0.0.1:{library.ports['manager']}"

            with LiveInstance(self.device_root,
                              extra_settings={("network", "library_url"): library_api}) as device:
                device.wait_for_api()
                device.library_files_port = library.ports["assets"]
                save = ("vpin.call('save_filter_collection', 'Saved Here', 'T', 'All',"
                        " 'All', 'All', 'All', 'year', 'All', false, 'asc')")

                (saved, picker, again), failures = self._evaluate(device, (
                    save, "vpin.call('get_collections')", save))
                on_hub = [row["name"] for row in
                          _fetch(f"{library_api}/api/v1/collections")["collections"]]
                held = _fetch(f"{library_api}/api/v1/collections/Saved%20Here")
                direct = requests.post(f"{library_api}/api/v1/collections",
                                       json={"name": "Saved Here", "games": []}, timeout=30)

        self.assertEqual(saved, {"success": True,
                                 "message": "Filter collection 'Saved Here' saved successfully"})
        self.assertIn("Saved Here", picker)
        self.assertIn("Saved Here", on_hub)
        self.assertEqual((held["type"], held["count"], held["order_by"], held["direction"]),
                         ("filter", 1, "year", "asc"))
        self.assertEqual(again, {"success": False,
                                 "message": direct.json()["error"]["message"]})
        self.assertEqual(failures, [])

    def test_a_device_asked_to_show_a_collection_with_the_hub_down_says_so(self) -> None:
        with LiveInstance(self.library_root) as library:
            library.wait_for_api()
            library_api = f"http://127.0.0.1:{library.ports['manager']}"
            library.post("/api/v1/collections", {"name": "Hub Picks", "games": []})

            with LiveInstance(self.device_root,
                              extra_settings={("network", "library_url"): library_api}) as device:
                device.wait_for_api()
                device.library_files_port = library.ports["assets"]
                device_api = f"http://127.0.0.1:{device.ports['manager']}"

                def hub_stops_then_device_is_asked() -> tuple[int, str]:
                    library._stop()
                    answer = requests.put(f"{device_api}/api/v1/frontend/collection",
                                          json={"name": "Hub Picks"}, timeout=30)
                    return answer.status_code, answer.json()["error"]["message"]

                (refused,), _ = self._evaluate(device, (hub_stops_then_device_is_asked,))

        self.assertEqual(refused,
                         (409, f"The library at {library_api} could not be reached"))

    def _evaluate(self, device: LiveInstance,
                  steps: tuple[str | Until | Callable[[], object], ...]):
        """Open the device's playfield window and take each step, in order, once the
        theme is ready: a string is evaluated in the page, an `Until` waited on there,
        and anything else is called here."""
        async def take(browser: BrowserSession, step):
            if isinstance(step, str):
                return await browser.evaluate(step)
            if isinstance(step, Until):
                with suppress(TimeoutError):
                    return await browser.wait_for(step.expression, timeout=_LIMIT_S)
                return None
            return await asyncio.to_thread(step)

        async def run():
            async with BrowserSession(chromium_path()) as browser:
                await browser.navigate(device.theme_url("playfield"))
                try:
                    await browser.wait_for("document.body.dataset.ready === 'true'",
                                           timeout=self.READY_TIMEOUT)
                except TimeoutError as exc:
                    raise AssertionError(self._diagnose(exc, browser, device)) from exc
                results = [await take(browser, step) for step in steps]
                return results, list(browser.failed_requests)

        return asyncio.run(run())

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
