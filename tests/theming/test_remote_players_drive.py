"""The Remote's part in Players, driven at phone width as a visitor's phone would be:
Join by Just Initials, the identity sheet's Sign Out, Share with VPinPlay and Save Card,
This Is Me and Not Me changing who a rating and Favorite are for, and Now's up switches.

Slow: boots a real instance and a real browser. VPinPlay runs, pointed at a port nothing
answers on, so sharing a card never reaches it.
"""

from __future__ import annotations

import asyncio
import json
import unittest
import urllib.request
from pathlib import Path
from tempfile import TemporaryDirectory

from common.i18n import t
from tests.support.browser_session import BrowserSession, chromium_path
from tests.support.console_walk import ConsoleWalk
from tests.support.library import game_info, write_game
from tests.support.live_instance import LiveInstance

NOWHERE = "http://127.0.0.1:9"
USER_ID = "visitor-one"
CARD_FILE = f"vpinplay-{USER_ID}.svg"
KID_NAME = "Kid"
KID_INITIALS = "KID"
GUEST_INITIALS = "VIS"

# The index of the first element under `selector` with a line of text equal to `text`.
# By line, because a Quasar button's text begins with its icon's ligature.
INDEX_OF = ("[...document.querySelectorAll(%s)].findIndex(el => el.innerText.split('\\n')"
            ".map(line => line.trim()).includes(%s))")
SHEET_OPEN = "!!document.querySelector('.remote-sheet')"
NOTHING_OPEN = "!document.querySelector('.remote-sheet')"
DIALOG_FOOTER = ".console-dialog-footer .q-btn"
# A dialog that has finished sliding or scaling in: Quasar animates it, and a click on
# the way in lands somewhere else. Not a `.remote-sheet` - those are covered by
# `SHEET_OPEN`, and one closing behind this dialog must not be counted as it.
DIALOG_READY = ("[...document.querySelectorAll('.q-dialog .q-card')].some(card =>"
                " !card.classList.contains('remote-sheet') &&"
                " getComputedStyle(card.closest('.q-dialog__inner')).transform === 'none'"
                " && card.getBoundingClientRect().width > 0)")
NO_DIALOG = "!document.querySelector('.q-dialog')"


def _call(instance: LiveInstance, method: str, path: str, body: dict | None = None):
    request = urllib.request.Request(
        instance.console_url(path), method=method,
        data=None if body is None else json.dumps(body).encode(),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=10) as handle:
        raw = handle.read()
    return json.loads(raw) if raw else None


async def _saved(path: Path) -> str:
    """The file a download wrote, once the browser has finished writing it."""
    for _ in range(600):
        if path.exists() and path.stat().st_size and not Path(f"{path}.crdownload").exists():
            return path.read_text(encoding="utf-8")
        await asyncio.sleep(0.05)
    raise TimeoutError(f"never saved: {path}")


class RemotePlayersDrive(unittest.TestCase):
    seen: dict = {}

    @classmethod
    def setUpClass(cls) -> None:
        if not chromium_path():
            raise unittest.SkipTest("no Chromium on this machine")
        with TemporaryDirectory() as tmp, TemporaryDirectory() as saved:
            write_game(Path(tmp), "Alpha", info=game_info("Alpha", vps_id="", game_id="alpha"))
            instance = LiveInstance(Path(tmp))
            settings = instance.config_dir / "extension_settings"
            settings.mkdir(parents=True, exist_ok=True)
            (settings / "vpinplay.json").write_text(json.dumps(
                {"endpoint": NOWHERE, "sync_on_exit": "false"}), encoding="utf-8")
            with instance:
                cls.seen = asyncio.run(cls._drive(instance, Path(saved)))

    @classmethod
    async def _drive(cls, instance: LiveInstance, saved: Path) -> dict:
        instance.wait_for_api()
        # A kept player from the start, so This Is Me has someone to choose and the
        # up-toggle list has more than the owner to show.
        kid = _call(instance, "POST", "/api/v1/players",
                   {"name": KID_NAME, "initials": KID_INITIALS})["id"]
        seen: dict = {}

        def roster() -> dict[str, dict]:
            return {one["id"]: one for one in _call(instance, "GET", "/api/v1/players")
                    ["players"]}

        async with BrowserSession(chromium_path()) as browser:
            await browser.send("Emulation.setDeviceMetricsOverride",
                               {"width": 390, "height": 844, "deviceScaleFactor": 2,
                                "mobile": True})
            await browser.send("Page.setDownloadBehavior",
                               {"behavior": "allow", "downloadPath": str(saved)})
            walk = ConsoleWalk(browser, instance)

            async def click_text(selector: str, text: str) -> None:
                at = await browser.wait_for(
                    f"(() => {{ const i = {INDEX_OF % (json.dumps(selector), json.dumps(text))};"
                    " return i >= 0 ? i + 1 : 0; })()")
                await browser.click(selector, nth=int(at) - 1)

            async def type_into(selector: str, text: str) -> None:
                await browser.click(selector)
                await browser.send("Input.insertText", {"text": text})

            async def open_identity() -> None:
                await browser.click(".remote-identity")
                await browser.wait_for(SHEET_OPEN)
                await walk.drawn()

            async def sheet_closed() -> None:
                await browser.wait_for(NOTHING_OPEN)
                await walk.drawn()

            async def open_game_sheet() -> None:
                for _attempt in range(3):
                    await click_text(".remote-row", "Alpha")
                    try:
                        await browser.wait_for(SHEET_OPEN, timeout=4)
                    except TimeoutError:
                        continue
                    await walk.drawn()
                    return
                raise AssertionError("no sheet opened for Alpha")

            # -- Join, by Just Initials --------------------------------------------
            await walk.visit("/remote?screen=join")
            seen["join_screen"] = await browser.wait_for(
                "document.querySelector('.remote-shell').innerText")
            await click_text(".remote-action", t("console.players.just_initials"))
            await browser.wait_for(DIALOG_READY)
            await type_into(".q-dialog input", GUEST_INITIALS)
            await click_text(DIALOG_FOOTER, t("console.remote.join"))
            await browser.wait_for(
                "document.querySelector('.remote-tab--here')?.innerText.includes"
                f"({json.dumps(t('word.now'))})")
            await walk.drawn()
            guest = next(key for key, one in roster().items() if one["guest"])
            seen["guest_up_alone"] = {key: one["up"] for key, one in roster().items()}
            seen["guest_initials"] = roster()[guest]["initials"]
            seen["header_no_chip_for_guest"] = await browser.evaluate(
                "!document.querySelector('.remote-identity-initials')")
            # The join toast sits low enough to cover a sheet button opened right under
            # it; a real tap a moment later never meets it, but this one might.
            await browser.wait_for("!document.querySelector('.q-notification')")

            # -- The identity sheet, for the guest just joined ---------------------
            await open_identity()
            seen["guest_sheet"] = await browser.evaluate(
                "document.querySelector('.remote-sheet').innerText")
            await click_text(".remote-action",
                             t("console.remote.share_with", service="VPinPlay"))
            await browser.wait_for(DIALOG_READY)
            await type_into(".q-dialog input", USER_ID)
            await click_text(DIALOG_FOOTER, t("console.remote.share"))
            await browser.wait_for(NO_DIALOG)
            await walk.drawn()
            seen["guest_account_after_share"] = _call(
                instance, "GET", f"/api/v1/players/{guest}/accounts/vpinplay")

            await open_identity()
            seen["guest_sheet_after_share"] = await browser.evaluate(
                "document.querySelector('.remote-sheet').innerText")
            await click_text(".remote-action", t("console.players.save_card"))
            seen["saved_card"] = await _saved(saved / CARD_FILE)
            await browser.wait_for("!document.querySelector('.q-notification')")

            # Save Card does not close the sheet - it is still the one open.
            await click_text(".remote-action", t("console.players.sign_out"))
            await browser.wait_for(
                "document.body.innerText.includes("
                f"{json.dumps(t('console.players.sign_out_one', name=GUEST_INITIALS))})")
            await browser.wait_for(DIALOG_READY)
            await click_text(DIALOG_FOOTER, t("console.players.sign_out"))
            await sheet_closed()
            seen["roster_after_sign_out"] = roster()

            # -- This Is Me, Not Me: who a rating and Favorite are for -------------
            await open_identity()
            seen["nobody_said_sheet"] = await browser.evaluate(
                "document.querySelector('.remote-sheet').innerText")
            await click_text(".remote-action", KID_NAME)
            await sheet_closed()
            seen["header_shows_kid"] = await browser.wait_for(
                "document.querySelector('.remote-identity-initials')?.innerText")

            await walk.visit("/remote?screen=play")
            await browser.wait_for("document.body.innerText.includes('Alpha')")
            await open_game_sheet()
            seen["kid_sheet_words"] = await browser.evaluate(
                "[...document.querySelectorAll('.remote-sheet button')]"
                ".map(b => b.innerText.trim())")
            await browser.click(".remote-sheet .console-star", nth=2)
            await sheet_closed()
            seen["kid_record"] = _call(instance, "GET", f"/api/v1/players/{kid}/record")
            seen["owner_game_after_kid_rated"] = _call(instance, "GET", "/api/v1/games/alpha")

            await open_identity()
            await click_text(".remote-action", t("console.remote.not_me"))
            await sheet_closed()
            seen["header_after_not_me"] = await browser.evaluate(
                "!document.querySelector('.remote-identity-initials')")
            await open_game_sheet()
            seen["owner_sheet_words"] = await browser.evaluate(
                "[...document.querySelectorAll('.remote-sheet button')]"
                ".map(b => b.innerText.trim())")

            # -- Now: who is up, a toggle on each -----------------------------------
            # A fresh navigation rather than closing the sheet by hand - it takes the
            # open dialog with it the same way a person moving on would.
            await walk.visit("/remote?screen=now")
            await browser.wait_for("document.querySelectorAll('.remote-up-row').length === 2")
            await browser.click(".remote-up-row .q-toggle", nth=1)
            await walk.drawn()
            seen["kid_up_after_toggle"] = roster()[kid]["up"]

            seen["console"] = [line for line in browser.console if "error" in line.lower()]
        return seen

    # -- Join --------------------------------------------------------------------

    def test_the_join_screen_offers_both_ways_in(self) -> None:
        said = self.seen["join_screen"]
        # The target's own name fills the sentence - this machine's, whatever it is here.
        before, after = t("console.remote.play_as_you", target="\0").split("\0")
        self.assertIn(before, said)
        self.assertIn(after, said)
        self.assertIn(t("console.remote.use_my_card"), said)
        self.assertIn(t("console.players.just_initials"), said)
        self.assertIn(t("console.remote.guest_until_close"), said)

    def test_just_initials_joins_up_alone(self) -> None:
        self.assertEqual(self.seen["guest_up_alone"].get(
            next(k for k, v in self.seen["guest_up_alone"].items() if v)), True)
        self.assertEqual(sum(self.seen["guest_up_alone"].values()), 1)
        self.assertEqual(self.seen["guest_initials"], GUEST_INITIALS)

    def test_a_guests_initials_are_not_shown_in_the_header(self) -> None:
        self.assertTrue(self.seen["header_no_chip_for_guest"])

    # -- The identity sheet --------------------------------------------------------

    def test_a_guest_who_joined_with_initials_is_offered_sign_out_and_share(self) -> None:
        said = self.seen["guest_sheet"]
        self.assertIn(t("console.players.sign_out"), said)
        self.assertIn(t("console.remote.share_with", service="VPinPlay"), said)

    def test_sharing_sets_the_user_id_and_turns_share_on(self) -> None:
        account = self.seen["guest_account_after_share"]
        self.assertTrue(account["share"])
        self.assertEqual(
            next(f["value"] for f in account["fields"] if f["key"] == "user_id"), USER_ID)

    def test_once_shared_the_sheet_offers_save_card_not_share_again(self) -> None:
        said = self.seen["guest_sheet_after_share"]
        self.assertIn(t("console.players.save_card"), said)
        self.assertNotIn(t("console.remote.share_with", service="VPinPlay"), said)

    def test_save_card_downloads_the_account(self) -> None:
        self.assertIn("VPINPLAY_PAYLOAD", self.seen["saved_card"])
        self.assertIn(USER_ID, self.seen["saved_card"])

    def test_sign_out_removes_the_guest(self) -> None:
        self.assertTrue(all(not one["guest"]
                            for one in self.seen["roster_after_sign_out"].values()))

    def test_nobody_said_offers_this_is_me_for_the_kept_player(self) -> None:
        self.assertIn(KID_NAME, self.seen["nobody_said_sheet"])

    # -- This Is Me, Not Me ---------------------------------------------------------

    def test_this_is_me_shows_their_initials_in_the_header(self) -> None:
        self.assertEqual(self.seen["header_shows_kid"], KID_INITIALS)

    def test_a_kept_players_sheet_has_no_favorite_but_has_add_to_collection(self) -> None:
        words = " ".join(self.seen["kid_sheet_words"])
        self.assertNotIn(t("word.favorite"), words)
        self.assertIn(t("console.remote.add_collection"), words)

    def test_a_kept_players_rating_goes_to_their_record_not_the_library(self) -> None:
        record = {row["game_id"]: row for row in self.seen["kid_record"]["games"]}
        self.assertEqual(record["alpha"]["rating"], 3)
        self.assertFalse(self.seen["owner_game_after_kid_rated"].get("user", {}).get("rating"))

    def test_not_me_clears_the_header_and_favorite_returns(self) -> None:
        self.assertTrue(self.seen["header_after_not_me"])
        self.assertIn(t("word.favorite"), " ".join(self.seen["owner_sheet_words"]))

    # -- Now: who is up --------------------------------------------------------------

    def test_toggling_a_switch_puts_that_player_up(self) -> None:
        self.assertTrue(self.seen["kid_up_after_toggle"])

    def test_nothing_failed_in_the_browser(self) -> None:
        self.assertEqual(self.seen["console"], [])


if __name__ == "__main__":
    unittest.main()
