"""What the Extensions page says about an extension that is not running.

The words are the whole of this page: the list itself is one card per row. What is worth
pinning is that every state the host can reach is shown, by a word or by the switch, and
that a switch somebody set does not read as something that broke.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from nicegui import ui

from common import i18n
from common.extensions import host
from console import ext_page, sections, wizard
from tests.support import lines


class StateWordTests(unittest.TestCase):
    def test_every_state_the_switch_cannot_show_has_a_word(self) -> None:
        """A state with no word draws no chip, so a stopped extension would look fine."""
        states = {value for name, value in vars(host).items()
                  if name.isupper() and isinstance(value, str)
                  and value in {"loaded", "failed", "disabled", "off"}}

        self.assertEqual(states - {host.LOADED, host.OFF}, set(sections.STATE_WORDS))

    def test_running_draws_no_chip(self) -> None:
        """A badge on every row says nothing."""
        self.assertNotIn(host.LOADED, sections.STATE_WORDS)

    def test_off_draws_no_chip_beside_the_switch_that_says_it(self) -> None:
        self.assertNotIn(host.OFF, sections.STATE_WORDS)


class FrontDoorTests(unittest.TestCase):
    """What a person browsing what is installed is shown.

    Not what an extension may reach. A scope is what somebody agrees to when installing
    something; on a list of what is already installed it is jargon in front of everybody
    who is not auditing, and it belongs on the extension's own page.
    """

    def test_the_card_does_not_name_scopes_or_capabilities(self) -> None:
        source = Path(sections.__file__).read_text(encoding="utf-8")
        card = source[source.index("def _extension_card"):source.index("def _actions")]

        self.assertNotIn("scopes", card)
        self.assertNotIn("capabilities", card)

    def test_an_action_is_drawn_from_its_label_alone(self) -> None:
        """The description is already the line under the extension's name."""
        source = Path(sections.__file__).read_text(encoding="utf-8")
        actions = source[source.index("def _actions"):]

        self.assertIn("tooltip", actions)


def _drawn(found: dict) -> tuple[list[str], list[bool]]:
    with ui.column() as body:
        sections._extension_card(found)
    return ([one.text for one in body.descendants() if isinstance(one, ui.label)],
            [bool(one.value) for one in body.descendants() if isinstance(one, ui.switch)])


def _card(found: dict) -> list[str]:
    return _drawn(found)[0]


RUNNING = {"name": "sample", "state": host.LOADED, "enabled": True, "reason": "",
           "reason_key": ""}
SWITCHED_OFF = {**RUNNING, "state": host.OFF, "enabled": False, "reason": "Switched off",
                "reason_key": host.SWITCHED_OFF}


class CardTests(unittest.TestCase):
    def test_one_switched_off_says_nothing_the_switch_does_not(self) -> None:
        self.assertEqual(_drawn(SWITCHED_OFF), (["sample"], [False]))

    def test_one_switched_on_says_it_waits_for_the_next_start(self) -> None:
        said, switches = _drawn({
            **SWITCHED_OFF, "enabled": True,
            "reason": i18n.t(host.STARTS_AT_RESTART),
            "reason_key": host.STARTS_AT_RESTART})

        self.assertIn(i18n.t(host.STARTS_AT_RESTART), said)
        self.assertEqual(switches, [True])

    def test_one_off_for_another_reason_says_which(self) -> None:
        said, switches = _drawn({
            **RUNNING, "state": host.OFF, "reason": "Not for macOS",
            "reason_key": "extension.reason.not_for_platform"})

        self.assertIn("Not for macOS", said)
        self.assertEqual(switches, [True])

    def test_one_that_broke_wears_a_chip_and_keeps_its_switch_on(self) -> None:
        said, switches = _drawn({**RUNNING, "state": host.DISABLED,
                                 "reason": "It threw"})

        self.assertEqual(said, ["sample", i18n.t("console.sections.stopped"), "It threw"])
        self.assertEqual(switches, [True])


class SwitchTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        # Outside the test's task, which has no page to draw into.
        self.body = ui.column()

    def draw(self, found: dict, answer: object) -> tuple[mock.Mock, mock.AsyncMock]:
        switch = self.enterContext(mock.patch.object(sections.panel, "switch"))
        io = self.enterContext(mock.patch.object(
            sections.offload, "io",
            new=mock.AsyncMock(**({"side_effect": answer} if isinstance(answer, Exception)
                                  else {"return_value": answer}))))
        with self.body:
            sections._extension_card(found)
        return switch, io

    async def press(self, switch: mock.Mock) -> None:
        with self.body:
            await switch.call_args.args[1](SimpleNamespace(value=False))

    async def test_it_asks_the_api_and_draws_the_answer(self) -> None:
        switch, io = self.draw(RUNNING, SWITCHED_OFF)

        await self.press(switch)

        [asked] = io.await_args_list
        self.assertEqual(asked.args[0].__name__, "set_extension_enabled")
        self.assertEqual(asked.args[1:], ("sample", False))
        self.assertFalse(switch.call_args.args[0])

    async def test_a_refused_switch_goes_back(self) -> None:
        notify = self.enterContext(mock.patch.object(sections.ui, "notify"))
        switch, _io = self.draw(RUNNING, RuntimeError("Not allowed"))

        await self.press(switch)

        notify.assert_called_once_with(i18n.t("said.could_not_turn_off"), caption="Not allowed",
                                       type="negative")
        self.assertEqual([one.args[0] for one in switch.call_args_list], [True, True])

    async def test_a_refusal_is_said_after_the_page_is_left(self) -> None:
        notify = self.enterContext(mock.patch.object(sections.ui, "notify", wraps=ui.notify))
        switch, io = self.draw(RUNNING, None)
        with self.body:
            pressed = ui.row().default_slot

        def refused_once_left(*_args: object) -> None:
            self.body.clear()
            raise RuntimeError("Not allowed")

        io.side_effect = refused_once_left
        with pressed:
            await switch.call_args.args[1](SimpleNamespace(value=False))

        notify.assert_called_once_with(i18n.t("said.could_not_turn_off"), caption="Not allowed",
                                       type="negative")


class SecretSettingTests(unittest.TestCase):
    """A secret is drawn empty whatever it holds, and leaving it empty keeps it."""

    def _drawn(self, field: dict) -> tuple[str, object, str]:
        given = {}

        def fake(value, on_save, *, placeholder=""):
            given.update(value=value, on_save=on_save, placeholder=placeholder)
            return lambda: None

        client = mock.Mock()
        with mock.patch.object(ext_page.panel, "field", fake):
            ext_page._control(client, "/ext/sample/settings", "token", field,
                              mock.AsyncMock())
        self.client = client
        return given["value"], given["on_save"], given["placeholder"]

    def test_a_value_that_arrived_anyway_is_not_drawn(self) -> None:
        value, _, placeholder = self._drawn({"key": "token", "type": "secret",
                                             "value": "leaked", "set": True})

        self.assertEqual((value, placeholder), ("", i18n.t("console.ext_page.secret_set")))

    def test_one_not_set_says_so(self) -> None:
        _, _, placeholder = self._drawn({"key": "token", "type": "secret", "set": False})

        self.assertEqual(placeholder, i18n.t("console.ext_page.secret_not_set"))

    def test_leaving_it_empty_writes_nothing(self) -> None:
        _, on_save, _ = self._drawn({"key": "token", "type": "secret", "set": True})

        self.assertIsNone(on_save(""))
        self.client.ext_put.assert_not_called()


class LanguageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.addCleanup(i18n.set_language, i18n.language())

    def test_what_a_scope_allows_is_read_in_the_language_set(self) -> None:
        english = ext_page._plainly("games:read")
        i18n.set_language("qps")

        self.assertNotEqual(english, ext_page._plainly("games:read"))

    def test_a_scope_nobody_described_is_shown_as_it_is(self) -> None:
        self.assertEqual("games:teleport", ext_page._plainly("games:teleport"))


def _said(job: dict, under: str = "ext.sample.action.run") -> list[str]:
    with ui.column() as body:
        wizard._report(body, job, under)
    return [one.text for one in body.descendants() if isinstance(one, ui.label)]


def _reported(job: dict) -> dict[str, str]:
    with ui.column() as body:
        wizard._report(body, job, "ext.sample.action.run")
    return lines.details(body)


def _noted(notes: list) -> dict[str, str]:
    with ui.column() as body:
        wizard._lines(notes, "")
    return lines.details(body)


class NoteTests(unittest.TestCase):
    def test_a_plain_note_hovers_nothing(self) -> None:
        self.assertEqual({"Kiss.pov was left behind": ""},
                         _noted(["Kiss.pov was left behind"]))

    def test_a_note_with_a_detail_hovers_it(self) -> None:
        self.assertEqual(
            {"Settings.xml could not be read": "Nothing is at /pbx/Config/Settings.xml"},
            _noted([{"text": "Settings.xml could not be read",
                     "detail": "Nothing is at /pbx/Config/Settings.xml"}]))

    def test_a_note_with_only_a_detail_says_the_detail(self) -> None:
        self.assertEqual({"Nothing answers at example.org": ""},
                         _noted([{"detail": "Nothing answers at example.org"}]))


class ReportTests(unittest.TestCase):
    def setUp(self) -> None:
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        (Path(folder.name) / "en.json").write_text(
            json.dumps({"action.run.result.games": "Games made"}), encoding="utf-8")
        i18n.own("ext.sample", Path(folder.name))
        self.addCleanup(i18n.disown, "ext.sample")
        self.addCleanup(i18n.set_language, i18n.language())

    def test_a_count_is_titled_by_its_extension(self) -> None:
        self.assertIn("Games made", _said({"state": "done", "result": {"games": 3}}))

    def test_a_count_with_no_word_is_titled_by_its_field(self) -> None:
        self.assertIn("games_skipped",
                      _said({"state": "done", "result": {"games_skipped": 1}}))

    def test_a_row_that_does_not_say_how_it_matched_is_named_alone(self) -> None:
        said = _said({"state": "done",
                      "result": {"already_here": [{"key": "k", "name": "Kiss"}]}})

        self.assertIn("Kiss", said)

    def test_a_row_that_did_not_come_across_is_worded_by_the_catalog(self) -> None:
        with mock.patch.object(wizard, "t", side_effect=lambda key, **_values: key):
            said = _said({"state": "done",
                          "result": {"rows": [{"name": "Kiss", "error": "no table"}]}})

        self.assertIn("console.ext_action.missed", said)

    def test_a_row_error_with_a_detail_hovers_it(self) -> None:
        drawn = _reported({"state": "done", "result": {"rows": [
            {"name": "Kiss", "error": {"text": "the game file did not come across",
                                       "detail": "Something is already at Kiss.vpx"}}]}})

        self.assertEqual("Something is already at Kiss.vpx",
                         drawn["Kiss - the game file did not come across"])

    def test_a_row_error_as_a_string_hovers_nothing(self) -> None:
        drawn = _reported({"state": "done", "result": {"rows": [
            {"name": "Kiss", "error": "the game file did not come across"}]}})

        self.assertEqual("", drawn["Kiss - the game file did not come across"])


if __name__ == "__main__":
    unittest.main()
