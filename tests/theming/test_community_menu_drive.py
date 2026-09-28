"""Community › VPinPlay and VPinPlay's own page, driven as a person would: the page opened
by its address and reloaded onto, the list's line for no account, an account not sharing
and one sharing, its link to Players, the menu with and without games waiting, Send Now,
and Share turned off in Players dropping what waited.

Slow: boots a real instance and a real browser. VPinPlay talks to a stand-in served here,
which lists one table and takes or refuses a send as the test says.
"""

from __future__ import annotations

import asyncio
import json
import threading
import unittest
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from tests.support.browser_session import BrowserSession, chromium_path
from tests.support.console_walk import DRAWN, MARK, ConsoleWalk, notice
from tests.support.library import game_info, write_game
from tests.support.live_instance import LiveInstance

GAME = "alpha"
VPS_ID = "vps-alpha"
USER_ID = "owner-id"
LIST = "/console?view=community:vpinplay:tables"
PAGE = "/console?view=extensions:vpinplay"

SHOWN = "(el => el.getClientRects().length > 0)"
HEADING = ("(el => el ? el.innerText.trim() : null)(document.querySelector("
           "'.console-workbench-title.console-panel-heading'))")
FIELDS = ("[...document.querySelectorAll('.console-fact-label')].filter"
          f"({SHOWN}).map(el => el.innerText.trim())")
# The line first in the bar's end: its words, and where it links.
LINE = ("(() => { const end = document.querySelector("
        "'.console-grid-bar .console-bar-foot .console-bar-end');"
        " const el = end && end.firstElementChild; if (!el || !el.innerText.trim())"
        " return null; const a = el.querySelector('a');"
        " return [el.innerText.trim(), a ? a.getAttribute('href') : null]; })()")
MENU_BUTTON = ("document.querySelector('.console-page-title').parentElement"
               ".querySelector('.q-btn')")
ITEM = ".q-menu .console-menu-item"
# Each item: its words, where it goes, whether a new tab, and the mark after it.
MENU = (f"[...document.querySelectorAll('{ITEM}')].map(e => {{"
        " const copy = e.cloneNode(true); copy.querySelectorAll('.q-icon')"
        ".forEach(i => i.remove()); const mark = e.querySelector('.q-icon');"
        " return [copy.innerText.trim(), e.getAttribute('href'), e.getAttribute('target'),"
        " mark ? mark.innerText.trim() : null]; })")
SHARE = ("(() => { const label = [...document.querySelectorAll("
         "'.console-section-work .console-fact-label')]"
         ".find(el => el.innerText.trim() === 'Share');"
         " return label ? label.nextElementSibling : null; })()")


class _VPinPlay(BaseHTTPRequestHandler):
    """One table listed, a user holding nothing, and a send taken or refused."""

    refusing = True
    sent: list[dict] = []

    def _answer(self, status: int, body: dict) -> None:
        said = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(said)))
        self.end_headers()
        self.wfile.write(said)

    def do_GET(self) -> None:
        if self.path.startswith("/api/v1/tables-plus/search"):
            self._answer(200, {"items": [{
                "name": "Alpha", "vpsId": VPS_ID, "manufacturer": "Bally", "year": 1992,
                "avgRating": 4.2, "ratingCount": 3, "startCountTotal": 10,
                "runTimeTotal": 120, "playerCount": 2, "lastRun": "2026-09-01T00:00:00Z"}],
                "pagination": {"total": 1}})
            return
        self._answer(404, {"detail": "none"})

    def do_POST(self) -> None:
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])) or b"{}")
        if type(self).refusing:
            self._answer(503, {"status": "error", "message": "down"})
            return
        type(self).sent.append(body)
        self._answer(200, {"status": "ok"})

    def log_message(self, *_args: Any) -> None:
        return


def _call(instance: LiveInstance, method: str, path: str, body: dict) -> dict:
    request = urllib.request.Request(instance.console_url(path), method=method,
                                     data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=10) as answer:
        return json.load(answer)


class CommunityMenuDrive(unittest.TestCase):
    seen: dict = {}

    @classmethod
    def setUpClass(cls) -> None:
        if not chromium_path():
            raise unittest.SkipTest("no Chromium on this machine")
        server = ThreadingHTTPServer(("127.0.0.1", 0), _VPinPlay)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            with TemporaryDirectory() as tmp:
                write_game(Path(tmp), "Alpha", info=game_info("Alpha", vps_id=VPS_ID,
                                                              game_id=GAME))
                instance = LiveInstance(Path(tmp))
                settings = instance.config_dir / "extension_settings"
                settings.mkdir(parents=True, exist_ok=True)
                (settings / "vpinplay.json").write_text(json.dumps(
                    {"endpoint": f"http://127.0.0.1:{server.server_address[1]}"}),
                    encoding="utf-8")
                with instance:
                    cls.seen = asyncio.run(cls._drive(instance))
        finally:
            server.shutdown()
            server.server_close()

    @classmethod
    async def _drive(cls, instance: LiveInstance) -> dict:
        seen: dict = {}
        instance.wait_for_api()
        owner = instance.api("/api/v1/players")["players"][0]["id"]
        store = instance.config_dir / "extension_settings" / "vpinplay.json"

        def account() -> dict:
            return instance.api(f"/api/v1/players/{owner}/accounts/vpinplay")

        async def until_account(says: Any) -> dict:
            for _ in range(200):
                held = account()
                if says(held):
                    return held
                await asyncio.sleep(0.05)
            raise AssertionError(f"the account never came to it: {account()}")

        async def waiting() -> None:
            await until_account(lambda held: held["status"] == "1 game waiting to send")

        async with BrowserSession(chromium_path()) as browser:
            await browser.send("Emulation.setDeviceMetricsOverride",
                               {"width": 1600, "height": 1000, "deviceScaleFactor": 1,
                                "mobile": False})
            walk = ConsoleWalk(browser, instance)

            async def reload() -> None:
                await browser.evaluate("window.__walkLeft = true")
                await browser.send("Page.reload", {})
                await browser.wait_for(f"!window.__walkLeft && {DRAWN}", 90)
                await walk.drawn()

            async def the_list() -> tuple[Any, list]:
                await walk.visit(LIST)
                line = await browser.wait_for(LINE)
                return line, await menu()

            async def menu() -> list:
                await browser.wait_for(f"!document.querySelector('{ITEM}')")
                await browser.wait_for(f"!!({MENU_BUTTON})")
                await browser.evaluate(f"({MENU_BUTTON}).setAttribute('data-drive', 'menu')")
                await walk.act(lambda: browser.click("[data-drive=menu]"),
                               until=f"!!document.querySelector('{ITEM}')")
                items = await browser.evaluate(MENU)
                await browser.click(".console-page-title")
                await browser.wait_for(f"!document.querySelector('{ITEM}')")
                return items

            # The extension's page by its address, and again after a reload.
            await walk.visit(PAGE)
            seen["page"] = [await browser.wait_for(HEADING), await browser.evaluate(FIELDS)]
            await reload()
            seen["reloaded"] = [await browser.wait_for(HEADING),
                                await browser.evaluate("location.search")]

            # Opened from the list and gone back from, the address following each.
            await walk.visit("/console?view=extensions")
            await browser.evaluate(
                "[...document.querySelectorAll('.console-card')].find(card =>"
                " card.innerText.startsWith('VPinPlay')).querySelector('.q-btn.q-btn--flat')"
                ".setAttribute('data-drive', 'open')")
            await walk.act(lambda: browser.click("[data-drive=open]"),
                           until="location.search === '?view=extensions:vpinplay'")
            seen["opened"] = await browser.wait_for(HEADING)
            await browser.evaluate(
                "[...document.querySelectorAll('.q-btn')].find(b =>"
                " b.innerText.trim() === 'arrow_back').setAttribute('data-drive', 'back')")
            await walk.act(lambda: browser.click("[data-drive=back]"),
                           until="location.search === '?view=extensions'")
            seen["back"] = await browser.evaluate(HEADING)

            # Nobody holds a VPinPlay account.
            seen["no_account"] = await the_list()

            # The owner holds one, with Share off.
            _call(instance, "PATCH", f"/api/v1/players/{owner}", {"initials": "OWN"})
            _call(instance, "PUT", f"/api/v1/players/{owner}/accounts/vpinplay",
                  {"values": {"user_id": USER_ID}})
            seen["share_off"] = await the_list()

            # Share on.
            _call(instance, "PUT", f"/api/v1/players/{owner}/accounts/vpinplay/share",
                  {"share": True})
            seen["sharing"] = await the_list()

            # A rating on a game already sent, refused by VPinPlay, waits.
            held = json.loads(store.read_text(encoding="utf-8"))
            held["accounts"][owner]["sent"] = GAME
            store.write_text(json.dumps(held), encoding="utf-8")
            _call(instance, "PUT", f"/api/v1/games/{GAME}/rating", {"rating": 3})
            await waiting()
            seen["waiting"] = await the_list()

            # Send Now from the list's menu, VPinPlay taking it this time.
            _VPinPlay.refusing = False
            await browser.evaluate(f"({MENU_BUTTON}).setAttribute('data-drive', 'menu')")
            await walk.act(lambda: browser.click("[data-drive=menu]"),
                           until=f"!!document.querySelector('{ITEM}')")
            await browser.wait_for(f"document.querySelector('{ITEM}').getBoundingClientRect()"
                                   ".width > 0")
            await walk.act(lambda: browser.click(ITEM, nth=0), mark=MARK,
                           until=notice("Sent"))
            seen["sent_said"] = await browser.evaluate(notice("Sent"))
            seen["after_send"] = await menu()
            seen["vpinplay_got"] = [(one["client"]["userId"],
                                     [table["info"]["vpsId"] for table in one["tables"]])
                                    for one in _VPinPlay.sent]
            seen["account_after_send"] = account()["status"]

            # Another refused, then Share turned off in Players drops it.
            _VPinPlay.refusing = True
            _call(instance, "PUT", f"/api/v1/games/{GAME}/rating", {"rating": 4})
            await waiting()
            await walk.visit(f"/console?view=players&player={owner}")
            await browser.evaluate(
                "[...document.querySelectorAll('.console-section-row')].find(el =>"
                " el.innerText.trim().startsWith('VPinPlay'))"
                ".setAttribute('data-drive', 'section')")
            await walk.act(lambda: browser.click("[data-drive=section]"),
                           until=f"!!({SHARE})")
            seen["share_before"] = await browser.evaluate(
                f"({SHARE}).getAttribute('aria-checked')")
            await browser.evaluate(f"({SHARE}).setAttribute('data-drive', 'share')")
            await browser.click("[data-drive=share]")
            await browser.wait_for(f"({SHARE}).getAttribute('aria-checked') === 'false'")
            seen["account_after_off"] = await until_account(lambda held: not held["share"])
            seen["books_after_off"] = json.loads(store.read_text(
                encoding="utf-8"))["accounts"][owner]
            seen["off_again"] = await the_list()

            # The line's link lands on Players.
            await browser.evaluate(
                "document.querySelector('.console-grid-bar .console-bar-foot"
                " .console-bar-end a').setAttribute('data-drive', 'line')")
            await browser.evaluate("window.__walkLeft = true")
            await browser.click("[data-drive=line]")
            await browser.wait_for(f"!window.__walkLeft && {DRAWN}", 90)
            seen["landed"] = await browser.evaluate("location.search")
            seen["console"] = [line for line in browser.console if "error" in line.lower()]
        return seen

    # -- the extension's page ------------------------------------------------------

    def test_the_page_opens_by_its_address(self) -> None:
        heading, fields = self.seen["page"]
        self.assertEqual(heading, "VPinPlay")
        self.assertIn("Server", fields)

    def test_a_reload_keeps_it(self) -> None:
        self.assertEqual(self.seen["reloaded"], ["VPinPlay", "?view=extensions:vpinplay"])

    def test_opening_it_and_going_back_write_the_address(self) -> None:
        self.assertEqual(self.seen["opened"], "VPinPlay")
        self.assertIsNone(self.seen["back"])

    # -- the line ------------------------------------------------------------------

    def test_no_account_says_so_and_links_to_players(self) -> None:
        line, _menu = self.seen["no_account"]
        self.assertEqual(line, ["Not sharing - no player has a VPinPlay account",
                                "/console?view=players"])

    def test_an_account_not_sharing_says_share_is_off(self) -> None:
        line, _menu = self.seen["share_off"]
        self.assertEqual(line, ["Not sharing - Share is off", "/console?view=players"])

    def test_a_sharing_account_is_named_by_its_initials(self) -> None:
        line, _menu = self.seen["sharing"]
        self.assertEqual(line, ["Sharing as OWN", None])

    def test_the_line_s_link_opens_players(self) -> None:
        self.assertEqual(self.seen["landed"], "?view=players")

    # -- the menu ------------------------------------------------------------------

    def test_with_no_account_the_menu_is_the_site_and_settings(self) -> None:
        _line, menu = self.seen["no_account"]
        self.assertEqual(menu, [
            ["Open VPinPlay", "https://www.vpinplay.com", "_blank", "open_in_new"],
            ["Settings", "/console?view=extensions:vpinplay", None, None]])

    def test_your_page_is_offered_once_the_owner_has_a_user_id(self) -> None:
        _line, menu = self.seen["share_off"]
        self.assertEqual([one[0] for one in menu], ["Open VPinPlay", "Your Page", "Settings"])
        self.assertEqual(menu[1][1:], [f"https://www.vpinplay.com/players.html?userid={USER_ID}",
                                       "_blank", "open_in_new"])

    def test_send_now_is_offered_only_while_something_waits(self) -> None:
        self.assertNotIn("Send Now", [one[0] for one in self.seen["sharing"][1]])
        self.assertEqual(self.seen["waiting"][1][0], ["Send Now", None, None, None])
        self.assertNotIn("Send Now", [one[0] for one in self.seen["after_send"]])

    def test_send_now_sends_what_waited(self) -> None:
        text, _classes = self.seen["sent_said"]
        self.assertIn("Sent 1 game", text)
        self.assertEqual(self.seen["vpinplay_got"], [(USER_ID, [VPS_ID])])
        self.assertEqual(self.seen["account_after_send"], "Sent just now")

    # -- Share off -----------------------------------------------------------------

    def test_share_off_in_players_drops_what_waited(self) -> None:
        self.assertEqual(self.seen["share_before"], "true")
        account = self.seen["account_after_off"]
        self.assertFalse(account["share"])
        self.assertTrue(account["status"].startswith("Sent"), account["status"])
        self.assertNotIn("send_now", [one["key"] for one in account["acts"]])
        self.assertNotIn("waiting", self.seen["books_after_off"])
        self.assertEqual(self.seen["books_after_off"]["sent"], GAME)

    def test_the_list_says_so_after(self) -> None:
        line, menu = self.seen["off_again"]
        self.assertEqual(line, ["Not sharing - Share is off", "/console?view=players"])
        self.assertNotIn("Send Now", [one[0] for one in menu])

    def test_nothing_failed_in_the_browser(self) -> None:
        self.assertEqual(self.seen["console"], [])


if __name__ == "__main__":
    unittest.main()
