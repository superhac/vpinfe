"""Adding from the Games and Tables grids in a real browser: the menus, the dialog behind
More Collections..., the message each add leaves and its Undo.

Slow: boots a real instance and a real browser.
"""

from __future__ import annotations

import asyncio
import json
import unittest
import urllib.request
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import quote

from tests.support.browser_session import BrowserSession, chromium_path
from tests.support.library import game_info, write_game
from tests.support.live_instance import LiveInstance

HAND = "Hand Picked"
SMART = "Smart Bally"
GAMES = {"Alpha": ("Bally", "1992"), "Bravo": ("Bally", "1995"),
         "Charlie": ("Williams", "1993"), "Delta": ("Williams", "1980")}

API = ("(() => { const el = document.querySelector('.ag-root-wrapper')"
       ".closest('.nicegui-aggrid'); return getElement(Number(el.id.slice(1))).api; })()")
SHOWN = ("(() => { const out = []; " + API + ".forEachNodeAfterFilterAndSort("
         "n => out.push(n.data.id)); return out; })()")
MENU = ("[...document.querySelectorAll('.q-menu .console-menu-item')]"
        ".map(e => [e.innerText.replace(/\\n+/g, ' / '),"
        " e.classList.contains('console-menu-blocked')])")
NOTE = ("(() => { const n = [...document.querySelectorAll('.q-notification')]"
        ".find(n => n.innerText.includes(%s)); return n ? [n.innerText, n.className] : null;"
        " })()")
ADD_BOX = ("[...document.querySelectorAll('.console-section-work .q-select')]"
           ".findIndex(e => e.innerText.includes('Add Games'))")
OPTIONS = ("[...document.querySelectorAll('.q-menu .q-item')].map(e => ["
           "e.innerText.replace(/\\n+/g, ' / '), e.classList.contains('disabled')])")
BOX_AFTER = ("(() => { const a = document.activeElement;"
             " const box = a && a.closest && a.closest('.q-select');"
             " return [!!box && box.innerText.includes('Add Games'),"
             " !!document.querySelector('.q-menu.console-picker-popup')]; })()")
PANEL_ROWS = ("[...document.querySelectorAll('.console-section-work .console-member-row')]"
              ".map(r => [r.innerText.split('\\n').slice(0, 2).join(' / '),"
              " !!r.querySelector('button')])")
INDEX_OF = ("(() => [...document.querySelectorAll(%s)]"
            ".findIndex(el => el.innerText.includes(%s)))()")
UNDO_AT = ("(() => { const n = [...document.querySelectorAll('.q-notification')]"
           ".find(n => n.innerText.includes(%s)); const b = n && [...n.querySelectorAll("
           "'button')].find(b => b.innerText.includes('Undo')); if (!b) return null;"
           " const r = b.getBoundingClientRect(); return [r.left + r.width / 2,"
           " r.top + r.height / 2]; })()")


class CollectionAddsDrive(unittest.TestCase):
    seen: dict = {}

    @classmethod
    def setUpClass(cls) -> None:
        if not chromium_path():
            raise unittest.SkipTest("no Chromium on this machine")
        with TemporaryDirectory() as tmp:
            for title, (maker, year) in GAMES.items():
                tables = ({"t-a1": {"id": "t-a1", "filename": "Alpha 1.vpx", "version": "1"},
                           "t-a2": {"id": "t-a2", "filename": "Alpha 2.vpx", "version": "2"}}
                          if title == "Alpha" else None)
                info = game_info(title, vps_id="", game_id=title.lower(), tables=tables,
                                 Info={"Manufacturer": maker, "Year": year})
                if tables:
                    info["vpinfe"]["default_table"] = "t-a2"
                write_game(Path(tmp), title, info=info, vpx=not tables,
                           files={"Alpha 1.vpx": b"x", "Alpha 2.vpx": b"x"} if tables
                           else None)
            with LiveInstance(Path(tmp)) as instance:
                cls.seen = asyncio.run(cls._drive(instance))

    @classmethod
    async def _drive(cls, instance: LiveInstance) -> dict:
        seen: dict = {}
        instance.wait_for_api()

        def send(method: str, path: str, body: dict) -> None:
            urllib.request.urlopen(urllib.request.Request(
                instance.console_url(path), data=json.dumps(body).encode(), method=method,
                headers={"Content-Type": "application/json"}), timeout=10).close()

        instance.post("/api/v1/collections", {"name": HAND, "games": ["bravo", "charlie"]})
        send("PATCH", f"/api/v1/collections/{quote(HAND)}", {"order_by": "manual"})
        instance.post("/api/v1/collections", {"name": SMART,
                                              "filters": {"manufacturer": ["Bally"]}})

        def refs(name: str) -> list:
            return [(one["game"], one["ref_table"], one["origin"]) for one in instance.api(
                f"/api/v1/collections/{quote(name)}/members")["members"]]

        async with BrowserSession(chromium_path()) as browser:
            async def settled() -> None:
                await asyncio.sleep(1.5)

            async def mouse(kind: str, x: float, y: float, button: str = "left") -> None:
                await browser.send("Input.dispatchMouseEvent",
                                   {"type": kind, "x": x, "y": y, "button": button,
                                    "buttons": 2 if button == "right" else 1,
                                    "clickCount": 1})

            async def right_click(row_id: str, column: str) -> None:
                await browser.evaluate(API + ".ensureNodeVisible(" + API + ".getRowNode("
                                       + json.dumps(row_id) + "), 'middle')")
                await asyncio.sleep(0.4)
                where = await browser.evaluate(
                    "(() => { const c = document.querySelector('.ag-row[row-id="
                    + json.dumps(row_id) + "] .ag-cell[col-id=\"" + column + "\"]');"
                    " const r = c.getBoundingClientRect();"
                    " return [r.left + r.width / 2, r.top + r.height / 2]; })()")
                await mouse("mousePressed", where[0], where[1], "right")
                await mouse("mouseReleased", where[0], where[1], "right")
                await browser.wait_for("document.querySelectorAll('.q-menu"
                                       " .console-menu-item').length > 0")
                await asyncio.sleep(0.6)

            async def click_text(selector: str, text: str) -> None:
                at = await browser.wait_for(
                    f"(() => {{ const i = {INDEX_OF % (json.dumps(selector), json.dumps(text))};"
                    " return i >= 0 ? i + 1 : 0; })()")
                await browser.click(selector, nth=int(at) - 1)
                await asyncio.sleep(0.6)

            async def outside() -> None:
                await mouse("mousePressed", 1200, 700)
                await mouse("mouseReleased", 1200, 700)
                await asyncio.sleep(0.5)

            async def said(text: str) -> list:
                return await browser.wait_for(NOTE % json.dumps(text), timeout=15.0)

            async def undo(text: str) -> None:
                last = None
                for _ in range(30):
                    where = await browser.evaluate(UNDO_AT % json.dumps(text))
                    if where and where == last:
                        break
                    last = where
                    await asyncio.sleep(0.1)
                await mouse("mousePressed", where[0], where[1])
                await mouse("mouseReleased", where[0], where[1])
                await settled()

            async def pick_from_dialog(name: str) -> None:
                await click_text(".q-menu .console-menu-item", "Add to Collection")
                await click_text(".q-menu .console-menu-item", "More Collections")
                await browser.wait_for("!!document.querySelector('.q-dialog"
                                       " .console-collection-pick')")
                await asyncio.sleep(0.6)
                seen.setdefault("dialogs", []).append(await browser.evaluate(
                    "document.querySelector('.q-dialog').innerText"))
                await click_text(".q-dialog .console-source-row", name)
                await click_text(".q-dialog button", "Add")

            await browser.navigate(instance.console_url("/console?view=games"))
            await browser.wait_for(API + ".getDisplayedRowCount() > 0", timeout=90.0)
            await settled()

            await right_click("delta", "name")
            seen["first_menu"] = await browser.evaluate(MENU)
            await pick_from_dialog(HAND)
            seen["added"] = await said("Added to")
            seen["added_refs"] = refs(HAND)

            await right_click("delta", "name")
            seen["again"] = await browser.evaluate(MENU)
            await outside()
            await undo("Added to")
            seen["undone"] = refs(HAND)

            await right_click("charlie", "name")
            await pick_from_dialog(SMART)
            seen["exception"] = await said("exception")
            seen["exception_refs"] = refs(SMART)

            await browser.navigate(instance.console_url("/console?view=tables"))
            await browser.wait_for(API + ".getDisplayedRowCount() > 0", timeout=60.0)
            await settled()
            await right_click("t-a1", "game")
            seen["table_menu"] = await browser.evaluate(MENU)
            await pick_from_dialog(HAND)
            await said("Added to")
            seen["table_refs"] = refs(HAND)

            await browser.navigate(instance.console_url(
                f"/console?view=games&collection={quote(HAND)}"))
            await browser.wait_for(API + ".getDisplayedRowCount() > 0", timeout=60.0)
            await settled()
            seen["narrowed"] = await browser.evaluate(SHOWN)
            await right_click("bravo", "name")
            seen["narrowed_menu"] = await browser.evaluate(MENU)
            await click_text(".q-menu .console-menu-item", f"Remove from “{HAND}”")
            seen["removed"] = await said("Removed from")
            await settled()
            seen["removed_refs"] = refs(HAND)
            seen["removed_shown"] = await browser.evaluate(SHOWN)
            await undo("Removed from")
            seen["put_back_refs"] = refs(HAND)
            seen["put_back_shown"] = await browser.evaluate(SHOWN)

            async def key(name: str, code: int, text: str) -> None:
                for kind in ("keyDown", "keyUp"):
                    await browser.send("Input.dispatchKeyEvent", {
                        "type": kind, "key": name, "code": name,
                        "windowsVirtualKeyCode": code, "nativeVirtualKeyCode": code,
                        **({"text": text} if kind == "keyDown" and text else {})})
                    await asyncio.sleep(0.05)

            await browser.navigate(instance.console_url(
                f"/console?view=collections&collection={quote(HAND)}"))
            await browser.wait_for("document.body.innerText.includes('Add Games')",
                                   timeout=60.0)
            await settled()
            box = await browser.evaluate(ADD_BOX)
            await browser.click(".console-section-work .q-select input", nth=box)
            for letter in "a":
                await key(letter, ord(letter.upper()), letter)
            await asyncio.sleep(0.8)
            seen["options"] = await browser.evaluate(OPTIONS)
            await key("Backspace", 8, "")
            for letter in "delta":
                await key(letter, ord(letter.upper()), letter)
            await asyncio.sleep(0.5)
            await key("Enter", 13, "\r")
            await said("Added to")
            await settled()
            seen["box_after"] = await browser.evaluate(BOX_AFTER)

            send("PUT", f"/api/v1/collections/{quote(SMART)}/excluded/bravo", {"table": ""})
            await browser.navigate(instance.console_url(
                "/console?view=games&game=bravo&section=collections"))
            await browser.wait_for("document.body.innerText.includes('Add to Collection')",
                                   timeout=60.0)
            await settled()
            seen["game_panel"] = await browser.evaluate(PANEL_ROWS)
            await click_text(".console-section-work button", "Add to Collection")
            seen["game_menu"] = await browser.evaluate(MENU)
            await outside()
            await browser.click(".console-section-work .console-member-row button",
                                nth=[row for row, _b in seen["game_panel"]].index(
                                    f"{SMART} / Taken out"))
            await settled()
            seen["put_back"] = refs(SMART)
        return seen

    def test_a_first_menu_offers_the_rest_through_a_dialog(self) -> None:
        self.assertEqual(["Launch", "Add to Collection / chevron_right"],
                         [label for label, _inert in self.seen["first_menu"]])
        self.assertIn("Hand-picked · 2 games", self.seen["dialogs"][0])
        self.assertIn("Smart · 2 games", self.seen["dialogs"][0])

    def test_an_add_into_a_hand_picked_one_is_green_with_undo(self) -> None:
        text, classes = self.seen["added"]
        self.assertIn(f"Added to “{HAND}”", text)
        self.assertIn("Undo", text)
        self.assertIn("bg-positive", classes)
        self.assertIn(("delta", "", "named"), self.seen["added_refs"])

    def test_the_collection_used_last_leads_and_says_when_it_holds_the_row(self) -> None:
        self.assertEqual((f"Add to “{HAND}” / In It", True), tuple(self.seen["again"][1]))

    def test_undo_takes_the_add_back(self) -> None:
        self.assertNotIn("delta", [game for game, _t, _o in self.seen["undone"]])

    def test_an_add_into_a_smart_one_is_amber_and_an_exception(self) -> None:
        text, classes = self.seen["exception"]
        self.assertIn(f"Added to “{SMART}” as an exception to its rules", text)
        self.assertIn("settings_suggest", text)
        self.assertIn("bg-warning", classes)
        self.assertIn(("charlie", "", "named"), self.seen["exception_refs"])

    def test_a_table_goes_in_held_to_that_table(self) -> None:
        self.assertIn(("alpha", "t-a1", "named"), self.seen["table_refs"])

    def test_a_grid_narrowed_to_a_collection_offers_to_remove_from_it(self) -> None:
        self.assertIn(f"Remove from “{HAND}”",
                      [label for label, _inert in self.seen["narrowed_menu"]])
        self.assertNotIn("bravo", [game for game, _t, _o in self.seen["removed_refs"]])
        self.assertNotIn("bravo", self.seen["removed_shown"])

    def test_the_add_box_says_maker_and_year_and_ticks_what_is_in_it(self) -> None:
        options = dict((label, held) for label, held in self.seen["options"])
        self.assertIs(False, options.get("Delta / Williams 1980"))
        self.assertIs(True, options.get("Charlie / Williams 1993 / check"))
        # Held to one of its tables is held all the same.
        self.assertIs(True, options.get("Alpha / Bally 1992 / check"))

    def test_the_add_box_stays_open_and_focused_for_the_next(self) -> None:
        self.assertEqual([True, True], self.seen["box_after"])

    def test_a_game_s_panel_shows_where_it_was_taken_out_and_puts_it_back(self) -> None:
        self.assertIn([f"{SMART} / Taken out", True], self.seen["game_panel"])
        self.assertIn(("bravo", "", "filter"), self.seen["put_back"])

    def test_a_game_s_panel_offers_every_collection_and_a_new_one(self) -> None:
        self.assertEqual([[f"{HAND} / In It", True],
                          ["settings_suggest / Last Played", False],
                          [f"settings_suggest / {SMART}", False],
                          ["New Collection...", False]], self.seen["game_menu"])

    def test_undoing_a_removal_puts_it_back_in_its_place(self) -> None:
        order = [game for game, _t, origin in self.seen["put_back_refs"] if origin == "named"]
        self.assertEqual("bravo", order[0])
        self.assertIn("bravo", self.seen["put_back_shown"])


if __name__ == "__main__":
    unittest.main()
