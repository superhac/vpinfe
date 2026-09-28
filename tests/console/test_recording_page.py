"""Settings > Hardware > Recording: each default read from its setting, the two commands,
Test, and the recordings waiting."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, Mock, patch

from starlette.testclient import TestClient

import httpapi
from common import config_schema, paths
from common.capture import adapters, commands, preflight
from common.host import tools
from common.i18n import t
from console import panel, recording, settings
from console.data import Library
from tests.capture.test_preflight import report

PAGE = next(page for _group, pages in settings.DEVICE_INDEX for page in pages
            if page[0] == "hardware.recording")


class Served:
    """The Console's client, answered by this install's API in-process."""

    def __init__(self, client: TestClient) -> None:
        self._client = client
        self.discarded = 0
        self.tested: dict[str, Any] = {"ok": True, "size": [1920, 1080], "fps": 30.0,
                                       "frames": 90, "picture": "data:image/jpeg;base64,"}

    def _get(self, path: str) -> Any:
        response = self._client.get(path)
        if response.is_error:
            raise RuntimeError(response.text)
        return response.json()

    def config_schema(self) -> list[dict]:
        return list(self._get("/config/schema")["sections"])

    def config_values(self) -> dict:
        return dict(self._get("/config")["values"])

    def config_path_checks(self) -> list[dict]:
        return list(self._get("/config/paths")["checks"])

    def put_config(self, changes: dict) -> dict:
        response = self._client.put("/config", json=changes)
        if response.is_error:
            raise RuntimeError(response.text)
        return dict(response.json()["values"])

    def capture_report(self) -> dict:
        return dict(self._get("/capture"))

    def capture_proposals(self) -> dict:
        return {"count": 2, "bytes": 3 * 1024 * 1024, "proposals": []}

    def discard_proposals(self) -> dict:
        self.discarded += 1
        return {"discarded": 2}

    def test_capture(self, _settings: dict | None = None) -> dict:
        return self.tested

    def choose_capture_screens(self) -> dict:
        self.chosen = getattr(self, "chosen", 0) + 1
        return {"id": "j1"}


class RecordingPageTests(unittest.IsolatedAsyncioTestCase):
    """A device that records every screen, with the community's settings."""

    def setUp(self) -> None:
        root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.enterContext(patch.object(paths, "VPINFE_INI_PATH", root / "vpinfe.ini"))
        self.report = report()
        self.plays_no_h264 = report(browser_state="no_h264")
        self.unsupported = report(adapters.Unsupported("wayland", adapters.NO_WAY))
        self.enterContext(patch("common.capture.preflight.report",
                                side_effect=lambda **_: self.report))
        self.served = Served(TestClient(httpapi.create_api_app(),
                                        raise_server_exceptions=False))
        self.library = Library(self.served)  # type: ignore[arg-type]
        self.enterContext(patch.object(
            settings.run, "io_bound",
            new=AsyncMock(side_effect=lambda call, *args, **kwargs: call(*args, **kwargs))))
        self.enterContext(patch("console.on_page.ui"))
        for module in (settings, recording):
            self.enterContext(patch.object(module, "ui"))
        self.head = self.enterContext(patch.object(settings, "page_head"))
        self.facts = self.enterContext(patch.object(panel, "facts"))
        self.line = self.enterContext(patch.object(panel, "line"))
        self.field = self.enterContext(patch.object(panel, "field"))
        self.action = self.enterContext(patch.object(panel, "action"))
        self.enterContext(patch.object(panel, "disclosure"))
        self.rerender = Mock()

    async def _drawn(self) -> list[tuple[Any, Any]]:
        self.facts.reset_mock()
        await settings._draw_system_page(self.library, self.rerender, MagicMock(), PAGE,
                                         {}, [])
        [drawn] = self.facts.call_args_list
        return list(drawn.args[1])

    def _under(self, entries: list[tuple[Any, Any]], label: str) -> str:
        """The line drawn under a setting."""
        at = next(i for i, (one, _) in enumerate(entries) if one == label)
        self.line.reset_mock()
        entries[at + 1][1]()
        return str(self.line.call_args.args[0])

    def _option(self, key: str) -> dict:
        return next(option for section in self.served.config_schema()
                    if section["name"] == "capture" for option in section["options"]
                    if option["key"] == key)

    async def test_the_page_is_under_hardware_with_its_settings_gathered(self) -> None:
        headings = [value for label, value in await self._drawn() if label is panel.HEADING]

        self.assertEqual(PAGE[3], ("capture",))
        self.assertEqual(headings, [t("config.group.timing"), t("config.group.video"),
                                    t("config.group.audio"), t("config.group.commands")])

    async def test_a_setting_at_the_standard_says_so_with_no_number(self) -> None:
        entries = await self._drawn()

        self.assertEqual(self._under(entries, t("config.capture.length.label")),
                         t("console.settings.described_default",
                           description=t("config.capture.length.description"),
                           default=t("console.settings.community_standard")))
        self.assertEqual(self._under(entries, t("config.capture.fps.label")),
                         t("console.settings.community_standard"))
        self.assertEqual(self._under(entries, t("config.capture.wait.label")),
                         t("console.settings.described_default",
                           description=t("config.capture.wait.description"),
                           default=t("console.settings.vpinfe_default")))

    async def test_a_changed_setting_names_the_default_read_from_the_schema(self) -> None:
        self.served.put_config({"capture": {"length": 25, "fps": "60", "wait": 8}})
        entries = await self._drawn()

        self.assertTrue(self._under(entries, t("config.capture.length.label")).endswith(
            t("console.settings.community_standard_is",
              value=t("console.settings.seconds", value="20"))))
        self.assertEqual(self._under(entries, t("config.capture.fps.label")),
                         t("console.settings.community_standard_is", value="30"))
        self.assertTrue(self._under(entries, t("config.capture.wait.label")).endswith(
            t("console.settings.vpinfe_default_is",
              value=t("console.settings.seconds", value="15"))))

    def test_the_reminder_follows_the_default_wherever_it_moves(self) -> None:
        moved = {**self._option("length"), "default": "30"}

        self.assertEqual(settings.default_said(moved, 20),
                         t("console.settings.community_standard_is",
                           value=t("console.settings.seconds", value="30")))
        self.assertEqual(settings.default_said(moved, 30),
                         t("console.settings.community_standard"))

    async def test_the_line_follows_the_value_as_it_is_set(self) -> None:
        option = self._option("sound")
        save = AsyncMock(return_value=True)
        saved, (_, draw) = settings._noted(option, False, save, "")  # type: ignore[misc]
        draw()

        await saved(True)

        self.assertEqual(self.line.return_value.set_text.call_args.args[0],
                         t("console.settings.described_default",
                           description=t("config.capture.sound.description"),
                           default=t("console.settings.community_standard_is",
                                     value=t("word.off"))))

    async def test_automatic_says_what_it_records_here(self) -> None:
        h264 = self._under(await self._drawn(), t("config.capture.video_codec.label"))
        self.report = self.plays_no_h264
        vp9 = self._under(await self._drawn(), t("config.capture.video_codec.label"))

        self.assertTrue(h264.endswith(t("console.recording.automatic_h264")))
        self.assertTrue(vp9.endswith(t("console.recording.automatic_vp9")))

    async def test_an_empty_command_stands_for_vpinfes_own_on_this_device(self) -> None:
        await self._drawn()

        placeholders = [call.kwargs.get("placeholder") for call in self.field.call_args_list
                        if call.kwargs.get("refuses")]
        self.assertEqual(placeholders, [self.report["commands"]["record"],
                                        self.report["commands"]["encode"]])

    async def test_a_command_that_cannot_run_is_refused_at_the_field(self) -> None:
        await self._drawn()
        keep = next(call.args[1] for call in self.field.call_args_list
                    if call.kwargs.get("placeholder") == self.report["commands"]["record"])

        refused = await keep("{recorder} {input} {video_codec} {output}")
        kept = await keep("{recorder} -o {screen} -f {output}")

        self.assertEqual(refused, t(commands.ELSEWHERE, token="video_codec",
                                    command=t("config.capture.encode_command.label")))
        self.assertEqual(kept, "")
        self.assertEqual(self.served.config_values()["capture"]["record_command"],
                         "{recorder} -o {screen} -f {output}")

    async def test_copy_vpinfes_command_puts_it_in_the_field_to_edit(self) -> None:
        entries = await self._drawn()
        at = next(i for i, (one, _) in enumerate(entries)
                  if one == t("config.capture.encode_command.label"))
        self.action.reset_mock()
        for label, draw in entries[at + 1:at + 3]:
            self.assertIs(label, panel.ASIDE)
            draw()
        [copy] = [call.args[1] for call in self.action.call_args_list
                  if call.args[0] == t("console.recording.copy_vpinfe_command")]

        await copy()

        self.assertEqual(self.served.config_values()["capture"]["encode_command"],
                         commands.OWN_ENCODE)
        settings.ui.timer.assert_called_with(0.01, self.rerender, once=True)

    async def test_a_device_that_records_nothing_says_why_with_the_pages_name(self) -> None:
        self.report = self.unsupported
        await self._drawn()

        [said] = self.head.call_args.args[1]
        said()

        self.assertEqual(recording.ui.label.call_args.args[0],
                         t(adapters.NO_WAY))

    async def test_a_missing_ffmpeg_vpinfe_can_get_links_to_the_tools_page(self) -> None:
        with patch.object(tools, "here", return_value=tools.WINDOWS):
            blocked = preflight.reason(preflight.NEEDS_TOOL, {"tool": "FFmpeg"},
                                       tools.remedy(tools.FFMPEG, missing=True))
        self.report = {**self.unsupported, "reason": blocked}
        link = self.enterContext(patch.object(panel, "link"))
        await self._drawn()

        [said] = self.head.call_args.args[1]
        said()

        self.assertEqual(blocked["fix"], tools.FIX_AUTO)
        link.assert_called_once_with(t("console.settings.page_tools"),
                                     to=settings.address_for(settings.TOOLS))

    async def _choose_screens(self) -> Any:
        """The Recording page on a desktop not yet told which screens VPinFE may record:
        what its finding says, and Choose Screens."""
        self.report = {**self.unsupported, "reason": preflight.reason(
            adapters.NOT_CHOSEN, {"desktop": "KDE Plasma"})}
        await self._drawn()
        [said] = self.head.call_args.args[1]
        self.action.reset_mock()
        said()
        [choose] = [call.args[1] for call in self.action.call_args_list
                    if call.args[0] == t("console.recording.choose_screens")]
        return choose

    async def test_a_desktop_not_yet_told_which_screens_offers_choose_screens(self) -> None:
        await self._choose_screens()

        labels = [call.args[0] for call in recording.ui.label.call_args_list]
        self.assertIn(t(adapters.NOT_CHOSEN, desktop="KDE Plasma"), labels)
        self.assertNotIn(t("capture.portal.not_chosen.remedy"), " ".join(labels))

    async def test_choose_screens_asks_first_then_says_what_the_desktop_answered(
            self) -> None:
        choose = await self._choose_screens()
        answered = {"kept": True, "shared": 3, "screens": 3, "reason": None}

        with patch("console.confirm.ask", new=AsyncMock(return_value=True)) as asked, \
                patch("console.record.ended_job", new=AsyncMock(return_value=answered)):
            await choose()

        self.assertEqual(asked.call_args.kwargs["detail"],
                         t("console.recording.choose_screens_detail", desktop="KDE Plasma"))
        self.assertEqual(self.served.chosen, 1)
        self.assertEqual(recording.ui.notify.call_args.args[0],
                         t("console.recording.chose_screens", desktop="KDE Plasma",
                           shared="3", screens="3"))
        self.assertEqual(recording.ui.notify.call_args.kwargs["type"], "positive")
        self.rerender.assert_called_once()

    async def test_a_screen_left_out_of_the_choice_is_a_warning(self) -> None:
        choose = await self._choose_screens()
        answered = {"kept": True, "shared": 2, "screens": 3, "reason": None}

        with patch("console.confirm.ask", new=AsyncMock(return_value=True)), \
                patch("console.record.ended_job", new=AsyncMock(return_value=answered)):
            await choose()

        self.assertEqual(recording.ui.notify.call_args.kwargs["type"], "warning")

    async def test_what_the_desktop_did_not_keep_is_said_as_a_warning(self) -> None:
        choose = await self._choose_screens()
        answered = {"kept": False, "shared": 3, "screens": 3,
                    "reason": {"key": "capture.portal.not_kept",
                               "params": {"desktop": "KDE Plasma"}}}

        with patch("console.confirm.ask", new=AsyncMock(return_value=True)), \
                patch("console.record.ended_job", new=AsyncMock(return_value=answered)):
            await choose()

        notified = recording.ui.notify.call_args
        self.assertEqual((notified.kwargs["caption"], notified.kwargs["type"]),
                         (t("capture.portal.not_kept", desktop="KDE Plasma"), "warning"))

    async def test_choose_screens_asks_nothing_of_the_desktop_until_agreed(self) -> None:
        choose = await self._choose_screens()

        with patch("console.confirm.ask", new=AsyncMock(return_value=False)):
            await choose()

        self.assertFalse(hasattr(self.served, "chosen"))

    async def test_a_device_that_records_says_nothing_with_it(self) -> None:
        await self._drawn()

        self.assertEqual(self.head.call_args.args[1], [])

    async def test_test_is_dimmed_with_the_reason_where_nothing_records(self) -> None:
        self.report = self.unsupported
        entries = await self._drawn()
        tester = next(value for label, value in entries[1:] if label is panel.FULL)
        self.action.reset_mock()

        tester()

        test = next(call for call in self.action.call_args_list
                    if call.args[0] == t("console.recording.test"))
        self.assertEqual((test.kwargs["enabled"], test.kwargs["hint"]),
                         (False, t(adapters.NO_WAY)))

    def test_what_a_test_made_is_said_with_its_picture(self) -> None:
        recording.ui.reset_mock()

        recording.came_out(self.served.tested)

        recording.ui.image.assert_called_once_with("data:image/jpeg;base64,")
        self.assertEqual(recording.ui.label.call_args.args[0],
                         t("console.recording.test_came_out", width="1920", height="1080",
                           fps="30", frames="90"))

    def test_a_failed_test_says_which_command_and_what_it_said(self) -> None:
        recording.came_out({"ok": False, "step": "record",
                            "reason": {"key": "capture.test.recorded_nothing"},
                            "detail": "wf-recorder: failed to find output DP-9"})

        self.assertEqual(self.line.call_args.args[0], t("capture.test.recorded_nothing"))
        self.assertEqual(self.line.call_args.kwargs["hint"],
                         "wf-recorder: failed to find output DP-9")

    async def test_recordings_waiting_are_counted_with_discard_all(self) -> None:
        entries = await self._drawn()
        waiting = dict((label, value) for label, value in entries
                       if isinstance(label, str))[t("console.recording.waiting")]
        self.action.reset_mock()
        recording.ui.reset_mock()
        waiting()
        [discard] = [call.args[1] for call in self.action.call_args_list
                     if call.args[0] == t("console.recording.discard_all")]

        with patch("console.confirm.ask", new=AsyncMock(return_value=True)) as asked:
            await discard()

        self.assertEqual(recording.ui.label.call_args.args[0],
                         t("console.recording.waiting_are", count=2, size="3.0 MB"))
        self.assertEqual(asked.call_args.args[0], t("console.recording.discard_ask", count=2))
        self.assertEqual(self.served.discarded, 1)

    def test_the_command_editor_is_declared_where_it_is_used(self) -> None:
        self.assertIs(settings.EDITORS[config_schema.EDITOR_CAPTURE_COMMAND],
                      recording.command_editor)


if __name__ == "__main__":
    unittest.main()
