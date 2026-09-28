"""Settings > Frontend > Browser: what the browser plays, and Use Google Chrome."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import requests
from fastapi.testclient import TestClient

import httpapi
from common import paths
from common.host import frontend_browser
from common.i18n import t
from console import panel, settings, undo
from console.api import ApiClient
from console.data import Library
from tests.support.clicks import press

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
BROWSER = next(page for _group, pages in settings.DEVICE_INDEX for page in pages
               if page[0] == "frontend.chromium")
NO_H264 = {"h264": False, "hevc": False, "vp9": True, "av1": True, "aac": False,
           "mp3": True, "vorbis": True, "opus": True}
PLAYS_ALL = dict.fromkeys(NO_H264, True)


class Served:
    """The Console's client, answered by this install's API in-process, with a frontend
    whose running and restarting the test holds."""

    def __init__(self, client: TestClient) -> None:
        self._client = client
        self.running = True
        self.perform_action = Mock(return_value={})

    @staticmethod
    def _answered(response: Any) -> Any:
        if response.is_error:
            raise RuntimeError(response.text)
        return response.json()

    def config_schema(self) -> list[dict]:
        return list(self._answered(self._client.get("/config/schema"))["sections"])

    def config_values(self) -> dict:
        return dict(self._answered(self._client.get("/config"))["values"])

    def config_path_checks(self) -> list[dict]:
        return list(self._answered(self._client.get("/config/paths"))["checks"])

    def put_config(self, changes: dict) -> dict:
        return dict(self._answered(self._client.put("/config", json=changes))["values"])

    def frontend_browser(self) -> dict:
        return dict(self._answered(self._client.get("/frontend/browser")))

    def frontend_state(self) -> dict:
        return {"running": self.running, "collection": "", "game": ""}


class BrowserPageTests(unittest.IsolatedAsyncioTestCase):
    """A browser in use that is not Google Chrome, with Chrome installed beside it."""

    def setUp(self) -> None:
        root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.in_use = root / "chromium"
        self.in_use.touch()
        self.bundled = False
        self.chrome = CHROME
        self.report = root / "frontend_browser.json"
        self.enterContext(patch.object(paths, "VPINFE_INI_PATH", root / "vpinfe.ini"))
        self.enterContext(patch.object(paths, "FRONTEND_BROWSER_PATH", self.report))
        self.enterContext(patch.object(frontend_browser, "_in_use",
                                       side_effect=lambda: (str(self.in_use), self.bundled)))
        self.enterContext(patch.object(frontend_browser, "_google_chrome",
                                       side_effect=lambda: self.chrome))
        self.client = TestClient(httpapi.create_api_app(), raise_server_exceptions=False)
        self.served = Served(self.client)
        self.library = Library(self.served)  # type: ignore[arg-type]
        self.enterContext(patch.object(
            settings.run, "io_bound",
            new=AsyncMock(side_effect=lambda call, *args, **kwargs: call(*args, **kwargs))))
        self.ui = self.enterContext(patch.object(settings, "ui"))
        self.enterContext(patch.object(settings, "page_head"))
        self.facts = self.enterContext(patch.object(panel, "facts"))
        self.action = self.enterContext(patch.object(panel, "action"))
        self.link = self.enterContext(patch.object(panel, "link"))
        self.offer = self.enterContext(patch.object(undo, "offer"))

    def _reported(self, formats: dict[str, bool], browser: str = "Chromium 145.0.7632.0",
                  path: Path | None = None) -> None:
        self.report.write_text(json.dumps({
            "browser": browser, "path": str(path or self.in_use), "bundled": self.bundled,
            "formats": formats, "reported_at": "2026-09-28T01:20:00Z"}), encoding="utf-8")

    def _program(self) -> str:
        return str(self.served.config_values()["chromium"]["path"])

    async def _drawn(self) -> list[tuple[Any, Any]]:
        self.facts.reset_mock()
        await settings._draw_system_page(self.library, Mock(), MagicMock(), BROWSER, {}, [])
        [drawn] = self.facts.call_args_list
        return list(drawn.args[1])

    @staticmethod
    def _labels(entries: list[tuple[Any, Any]]) -> list[Any]:
        return [label for label, _value in entries]

    def _value(self, entries: list[tuple[Any, Any]], label: str) -> Any:
        return dict((one, value) for one, value in entries if isinstance(one, str))[label]

    def _use_google_chrome(self, entries: list[tuple[Any, Any]]) -> Any:
        """The finding drawn, and the act it offers, if any."""
        self.action.reset_mock()
        entries[0][1]()
        offered = [call.args[1] for call in self.action.call_args_list
                   if call.args[0] == t("console.settings.use_google_chrome")]
        return offered[0] if offered else None

    async def test_the_report_and_the_settings_are_one_list(self) -> None:
        self._reported(NO_H264)

        labels = self._labels(await self._drawn())

        self.assertLess(labels.index(t("console.settings.browser_in_use")),
                        labels.index(t("config.chromium.path.label")))

    async def test_a_finding_leads_the_page_across_both_columns(self) -> None:
        self._reported(NO_H264)

        entries = await self._drawn()

        self.assertIs(entries[0][0], panel.FULL)
        self.assertEqual(self._value(entries, t("console.settings.browser_plays")),
                         "VP9, AV1, MP3, Vorbis, Opus")
        self.assertEqual(self._value(entries, t("console.settings.browser_does_not_play")),
                         "H.264, HEVC, AAC")

    async def test_a_browser_that_plays_everything_says_so_and_nothing_more(self) -> None:
        self._reported(PLAYS_ALL)

        entries = await self._drawn()

        self.assertIsNot(entries[0][0], panel.FULL)
        self.assertNotIn(t("console.settings.browser_does_not_play"), self._labels(entries))

    async def test_from_is_left_out_where_browser_program_names_the_same_path(self) -> None:
        self._reported(PLAYS_ALL)
        found = self._labels(await self._drawn())

        self.served.put_config({"chromium": {"path": str(self.in_use)}})
        chosen = self._labels(await self._drawn())

        self.assertIn(t("console.settings.browser_from"), found)
        self.assertNotIn(t("console.settings.browser_from"), chosen)

    async def test_the_bundled_copy_is_said_by_name_rather_than_by_its_path(self) -> None:
        self.bundled = True
        self._reported(PLAYS_ALL)
        self.ui.label.reset_mock()

        self._value(await self._drawn(), t("console.settings.browser_from"))()

        self.assertEqual(self.ui.label.call_args.args[0], t("console.settings.browser_bundled"))

    async def test_a_browser_that_has_not_reported_reads_not_checked_never_a_no(self) -> None:
        entries = await self._drawn()
        self.ui.label.reset_mock()

        self._value(entries, t("console.settings.browser_in_use"))()

        self.assertEqual(self.ui.label.call_args.args[0],
                         t("console.settings.browser_not_checked"))
        self.assertNotIn(t("console.settings.browser_does_not_play"), self._labels(entries))
        self.assertIsNot(entries[0][0], panel.FULL)

    async def test_a_report_on_another_browser_is_not_this_one_s(self) -> None:
        self._reported(NO_H264, path=self.in_use.with_name("elsewhere"))

        entries = await self._drawn()

        self.assertNotIn(t("console.settings.browser_plays"), self._labels(entries))

    async def test_an_install_too_old_to_say_draws_its_settings_alone(self) -> None:
        with patch.object(self.served, "frontend_browser", return_value={}):
            labels = self._labels(await self._drawn())

        self.assertEqual(labels[0], t("config.chromium.path.label"))

    async def test_a_report_that_cannot_be_read_says_so_above_the_settings(self) -> None:
        with patch.object(self.served, "frontend_browser", side_effect=RuntimeError("gone")), \
                patch.object(panel, "line") as line:
            entries = await self._drawn()
            entries[0][1]()

        self.assertEqual(line.call_args.args[0], t("console.settings.could_not_read_browser"))
        self.assertIn(t("config.chromium.path.label"), self._labels(entries))

    async def test_use_google_chrome_sets_browser_program_and_restarts_the_frontend(
            self) -> None:
        self._reported(NO_H264)
        use = self._use_google_chrome(await self._drawn())

        await press(use)

        self.assertEqual(self._program(), CHROME)
        self.served.perform_action.assert_called_once_with("frontend", "restart", "")

    async def test_a_closed_frontend_is_left_closed(self) -> None:
        self.served.running = False
        self._reported(NO_H264)

        await press(self._use_google_chrome(await self._drawn()))

        self.assertEqual(self._program(), CHROME)
        self.served.perform_action.assert_not_called()

    async def test_undo_puts_the_previous_browser_program_back_and_restarts_again(
            self) -> None:
        self.served.put_config({"chromium": {"path": str(self.in_use)}})
        self._reported(NO_H264)
        await press(self._use_google_chrome(await self._drawn()))
        [(said, reverse)] = [call.args for call in self.offer.call_args_list]

        await press(reverse)

        self.assertEqual(said, t("console.settings.using_google_chrome"))
        self.assertEqual(self._program(), str(self.in_use))
        self.assertEqual(self.served.perform_action.call_count, 2)
        self.offer.assert_called_once()

    async def test_it_is_offered_only_where_chrome_is_installed_and_not_in_use(self) -> None:
        self.chrome = ""
        self._reported(NO_H264)

        entries = await self._drawn()

        self.assertIs(entries[0][0], panel.FULL)
        self.assertIsNone(self._use_google_chrome(entries))


    async def test_a_browser_without_h264_is_offered_recording_as_vp9(self) -> None:
        self._reported(NO_H264)
        self.ui.label.reset_mock()

        (await self._drawn())[0][1]()

        said = [call.args[0] for call in self.ui.label.call_args_list if call.args]
        self.assertIn(t("console.recording.or_record_as_vp9"), said)
        self.assertEqual(self.link.call_args.kwargs["to"],
                         settings.address_for("capture"))

    async def test_a_browser_that_plays_no_video_is_not_offered_vp9(self) -> None:
        self._reported(dict.fromkeys(NO_H264, False))
        self.ui.label.reset_mock()

        (await self._drawn())[0][1]()

        said = [call.args[0] for call in self.ui.label.call_args_list if call.args]
        self.assertNotIn(t("console.recording.or_record_as_vp9"), said)


class TooOldToSayTests(unittest.TestCase):
    def test_an_install_without_the_report_answers_empty_never_none(self) -> None:
        gone = requests.Response()
        gone.status_code = 404
        with patch.object(requests.adapters.HTTPAdapter, "send", return_value=gone):
            self.assertEqual(ApiClient("http://127.0.0.1:1").frontend_browser(), {})


if __name__ == "__main__":
    unittest.main()
