"""What the frontend's browser reports it can play, the state and fix read off it, and the
route and capability that serve it."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from starlette.testclient import TestClient

import httpapi
from common import device_registry, install_identity, paths
from common.host import frontend_browser as fb

BUNDLED = "/opt/vpinfe/chromium/linux/chrome/chrome"
CHROME = "/usr/bin/google-chrome"

BUNDLED_145 = {
    "user_agent": "Mozilla/5.0 (X11; Linux x86_64) Chrome/145.0.0.0 Safari/537.36",
    "brands": [{"brand": "Chromium", "version": "145.0.7632.0"},
               {"brand": "Not.A/Brand", "version": "99.0.0.0"}],
    "can_play": {"h264": "", "hevc": "", "vp9": "probably", "av1": "probably", "aac": "",
                 "mp3": "probably", "vorbis": "probably", "opus": "probably"},
    "decoded": {"h264": False, "vp9": True},
}


class _Isolated(unittest.TestCase):
    """A report file of its own, a browser in use that exists, and no Chrome. The log is
    silent unless the test is about the log."""

    quiet = True

    def setUp(self) -> None:
        if self.quiet:
            silent = mock.patch.object(fb, "_log")
            silent.start()
            self.addCleanup(silent.stop)
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.store = Path(tmp.name) / "cache" / "frontend_browser.json"
        self.browser = Path(tmp.name) / "chrome"
        self.browser.write_text("")
        device_registry.reset_for_tests(Path(tmp.name) / "devices.json")
        self.addCleanup(device_registry.reset_for_tests)
        for patch in (mock.patch.object(fb.paths, "FRONTEND_BROWSER_PATH", self.store),
                      mock.patch.object(fb, "_in_use", return_value=(str(self.browser), True)),
                      mock.patch.object(fb, "_google_chrome", return_value=""),
                      mock.patch.object(fb.platform, "system", return_value="Linux")):
            patch.start()
            self.addCleanup(patch.stop)
        fb.reset_for_tests()


class StateTests(unittest.TestCase):
    def test_h264_is_what_plays_means(self) -> None:
        self.assertEqual(fb.state_of({"h264": True, "vp9": False}), fb.PLAYS)

    def test_vp9_without_h264_is_no_h264(self) -> None:
        self.assertEqual(fb.state_of({"h264": False, "vp9": True}), fb.NO_H264)

    def test_neither_is_no_video(self) -> None:
        self.assertEqual(fb.state_of({"h264": False, "vp9": False}), fb.NO_VIDEO)

    def test_an_answer_that_did_not_come_is_unknown_not_no(self) -> None:
        for formats in ({}, {"h264": None, "vp9": False}, {"h264": False, "vp9": None}):
            self.assertEqual(fb.state_of(formats), fb.UNKNOWN, formats)


class FixTests(unittest.TestCase):
    def fix(self, state: str, system: str, bundled: bool, chrome: str = "") -> fb.Fix | None:
        return fb.fix_for(state, system=system, bundled=bundled, in_use=BUNDLED, chrome=chrome)

    def test_nothing_to_fix_where_it_plays_or_has_not_said(self) -> None:
        self.assertIsNone(self.fix(fb.PLAYS, "Linux", True))
        self.assertIsNone(self.fix(fb.UNKNOWN, "Linux", True))

    def test_chrome_installed_and_not_in_use_is_one_press(self) -> None:
        found = self.fix(fb.NO_H264, "Windows", True, chrome=CHROME)
        self.assertEqual((found.action, found.chrome_path), (fb.USE_CHROME, CHROME))

    def test_chrome_already_in_use_is_not_offered_again(self) -> None:
        found = fb.fix_for(fb.NO_H264, system="Linux", bundled=False, in_use=CHROME,
                           chrome=CHROME)
        self.assertEqual(found.action, "")

    def test_windows_needs_the_setting_because_the_bundled_copy_wins(self) -> None:
        self.assertEqual(self.fix(fb.NO_H264, "Windows", True).key,
                         "frontend_browser.fix.install_chrome_set")

    def test_macos_needs_only_the_install(self) -> None:
        self.assertEqual(self.fix(fb.NO_H264, "Darwin", True).key,
                         "frontend_browser.fix.install_chrome_mac")

    def test_linux_with_the_bundled_copy_needs_only_the_install(self) -> None:
        self.assertEqual(self.fix(fb.NO_VIDEO, "Linux", True).key,
                         "frontend_browser.fix.install_chrome_linux")

    def test_linux_with_a_distribution_chromium_needs_the_setting(self) -> None:
        # `chromium` is found ahead of `google-chrome`, so installing Chrome changes nothing.
        self.assertEqual(self.fix(fb.NO_H264, "Linux", False).key,
                         "frontend_browser.fix.install_chrome_set")

    def test_no_browser_has_its_own_fix(self) -> None:
        self.assertEqual(self.fix(fb.NO_BROWSER, "Windows", False).key,
                         "frontend_browser.fix.no_browser")


class BrowserNameTests(unittest.TestCase):
    def test_the_made_up_brand_is_skipped(self) -> None:
        self.assertEqual(fb._browser_name(BUNDLED_145["brands"], ""), "Chromium 145.0.7632.0")

    def test_google_chrome_is_named_over_the_chromium_it_is_built_on(self) -> None:
        brands = [{"brand": "Not)A;Brand", "version": "8"},
                  {"brand": "Chromium", "version": "140.0.1"},
                  {"brand": "Google Chrome", "version": "140.0.1"}]
        self.assertEqual(fb._browser_name(brands, ""), "Google Chrome 140.0.1")

    def test_without_brands_the_user_agent_gives_the_major_version(self) -> None:
        self.assertEqual(fb._browser_name([], BUNDLED_145["user_agent"]), "Chromium 145")

    def test_nothing_readable_is_blank(self) -> None:
        self.assertEqual(fb._browser_name("junk", "curl/8"), "")


class RecordTests(_Isolated):
    def test_a_report_is_kept_and_read_back(self) -> None:
        answer = fb.record(BUNDLED_145)
        self.assertEqual(answer["state"], fb.NO_H264)
        self.assertEqual(answer["browser"], "Chromium 145.0.7632.0")
        self.assertEqual(answer["plays"], ["VP9", "AV1", "MP3", "Vorbis", "Opus"])
        self.assertEqual(answer["does_not_play"], ["H.264", "HEVC", "AAC"])
        self.assertTrue(self.store.is_file())
        self.assertEqual(fb.current()["state"], fb.NO_H264)

    def test_a_decode_that_ran_beats_can_play_type(self) -> None:
        # canPlayType says maybe, the real file shows no picture: no.
        answer = fb.record({**BUNDLED_145, "can_play": {"h264": "maybe"},
                            "decoded": {"h264": False, "vp9": True}})
        self.assertIs(answer["formats"]["h264"], False)

    def test_only_known_formats_are_kept(self) -> None:
        fb.record({**BUNDLED_145, "can_play": {"h264": "", "flac": "probably"}})
        held = json.loads(self.store.read_text(encoding="utf-8"))
        self.assertNotIn("flac", held["formats"])

    def test_something_that_is_not_a_report_is_unknown(self) -> None:
        self.assertEqual(fb.record("not a report")["state"], fb.UNKNOWN)

    def test_this_install_s_own_device_entry_keeps_it(self) -> None:
        registry = device_registry.get_device_registry()
        own = install_identity.install_id(paths.get_ini_config())
        registry.record(own)

        fb.record(BUNDLED_145)

        kept = registry.get(own).browser
        self.assertEqual((kept["state"], kept["name"]), (fb.NO_H264, "Chromium 145.0.7632.0"))
        self.assertTrue(kept["checked_at"])

    def test_a_report_from_another_browser_is_no_answer(self) -> None:
        fb.record(BUNDLED_145)
        other = self.browser.with_name("other")
        other.write_text("")
        with mock.patch.object(fb, "_in_use", return_value=(str(other), False)):
            self.assertEqual(fb.current()["state"], fb.UNKNOWN)

    def test_a_browser_that_is_not_there_is_no_browser(self) -> None:
        self.browser.unlink()
        answer = fb.current()
        self.assertEqual(answer["state"], fb.NO_BROWSER)
        self.assertEqual(answer["fix"]["key"], "frontend_browser.fix.no_browser")

    def test_not_reported_yet_says_nothing_is_wrong(self) -> None:
        answer = fb.current()
        self.assertEqual((answer["state"], answer["finding"], answer["fix"]),
                         (fb.UNKNOWN, "", None))


class LogTests(_Isolated):
    quiet = False

    def test_once_per_browser_and_state_with_the_fix(self) -> None:
        with self.assertLogs(fb.logger, "INFO") as seen:
            fb.record(BUNDLED_145)
            fb.record(BUNDLED_145)
        infos = [line for line in seen.output if line.startswith("INFO")]
        warnings = [line for line in seen.output if line.startswith("WARNING")]
        self.assertEqual(len(infos), 1)
        self.assertIn("Chromium 145.0.7632.0 (bundled). Plays VP9, AV1", infos[0])
        self.assertEqual(len(warnings), 1)
        self.assertIn("Install Google Chrome, and VPinFE uses it from then on", warnings[0])

    def test_a_browser_that_plays_everything_gets_no_warning(self) -> None:
        plays = {**BUNDLED_145, "decoded": {"h264": True, "vp9": True}}
        with self.assertLogs(fb.logger, "INFO") as seen:
            fb.record(plays)
        self.assertFalse([line for line in seen.output if line.startswith("WARNING")])


class ServedTests(_Isolated):
    def test_the_route_serves_the_report(self) -> None:
        fb.record(BUNDLED_145)
        client = TestClient(httpapi.create_api_app(), raise_server_exceptions=False)
        found = client.get("/frontend/browser")
        self.assertEqual(found.status_code, 200)
        body = found.json()
        self.assertEqual((body["state"], body["formats"]["vp9"]), (fb.NO_H264, True))
        self.assertEqual(body["finding"], "Most shared videos won't play in this browser")

    def test_capability_is_unavailable_only_where_nothing_plays(self) -> None:
        self.assertIs(fb.available(), True)
        fb.record({**BUNDLED_145, "decoded": {"h264": False, "vp9": False}})
        self.assertEqual(fb.available(), (False, "This browser can't play video"))
