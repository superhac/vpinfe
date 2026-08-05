from __future__ import annotations

import types
import unittest
from unittest import mock

from frontend import chromium_manager
from frontend.chromium_manager import ChromiumManager


class ChromiumManagerTests(unittest.TestCase):
    def test_windows_get_chromium_path_prefers_bundled_when_present(self) -> None:
        bundled = r"C:\vpinfe\chromium\windows\chrome-win\chrome.exe"

        with mock.patch("frontend.chromium_manager.platform.system", return_value="Windows"), \
            mock.patch("frontend.chromium_manager.resource_path", return_value=bundled), \
            mock.patch("frontend.chromium_manager.os.path.expandvars") as expandvars, \
            mock.patch("frontend.chromium_manager.os.path.isfile", return_value=True):
            self.assertEqual(
                chromium_manager.get_chromium_path(),
                chromium_manager.ChromiumPath(bundled, False),
            )
            expandvars.assert_not_called()

    def test_windows_get_chromium_path_uses_system_browser_for_slim_build(self) -> None:
        bundled = r"C:\vpinfe\chromium\windows\chrome-win\chrome.exe"
        chrome = r"C:\Program Files\Google\Chrome\Application\chrome.exe"

        def exists(path: str) -> bool:
            return path == chrome

        with mock.patch("frontend.chromium_manager.platform.system", return_value="Windows"), \
            mock.patch("frontend.chromium_manager.resource_path", return_value=bundled), \
            mock.patch("frontend.chromium_manager.os.path.expandvars", side_effect=lambda value: chrome if "Google\\Chrome" in value else value), \
            mock.patch("frontend.chromium_manager.os.path.isfile", side_effect=exists):
            self.assertEqual(
                chromium_manager.get_chromium_path(),
                chromium_manager.ChromiumPath(chrome, True),
            )

    def test_windows_get_chromium_path_does_not_use_edge_for_slim_build(self) -> None:
        bundled = r"C:\vpinfe\chromium\windows\chrome-win\chrome.exe"
        edge = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"

        def exists(path: str) -> bool:
            return path == edge

        with mock.patch("frontend.chromium_manager.platform.system", return_value="Windows"), \
            mock.patch("frontend.chromium_manager.resource_path", return_value=bundled), \
            mock.patch("frontend.chromium_manager.os.path.expandvars", side_effect=lambda value: edge if "Microsoft\\Edge" in value else value), \
            mock.patch("frontend.chromium_manager.os.path.isfile", side_effect=exists):
            self.assertEqual(
                chromium_manager.get_chromium_path(),
                chromium_manager.ChromiumPath(bundled, False),
            )

    def test_linux_get_chromium_path_finds_google_chrome_stable(self) -> None:
        chrome = "/usr/bin/google-chrome-stable"
        bundled = "/opt/vpinfe/chromium/linux/chrome/chrome"

        def which(binary_name: str) -> str | None:
            return chrome if binary_name == "google-chrome-stable" else None

        with mock.patch("frontend.chromium_manager.platform.system", return_value="Linux"), \
            mock.patch("frontend.chromium_manager.which", side_effect=which), \
            mock.patch("frontend.chromium_manager.resource_path", return_value=bundled):
            self.assertEqual(
                chromium_manager.get_chromium_path(),
                chromium_manager.ChromiumPath(chrome, True),
            )

    def test_parse_additional_chromium_options_supports_multiple_flags(self) -> None:
        options = chromium_manager.parse_additional_chromium_options(
            '--disable-accelerated-video-decode\n'
            '--ozone-platform=x11 --user-agent="VPinFE Test"'
        )

        self.assertEqual(
            options,
            [
                "--disable-accelerated-video-decode",
                "--ozone-platform=x11",
                "--user-agent=VPinFE Test",
            ],
        )

    def test_launch_window_appends_additional_chromium_options(self) -> None:
        manager = ChromiumManager()
        proc = types.SimpleNamespace()
        monitor = types.SimpleNamespace(x=10, y=20, width=800, height=600)

        with mock.patch("frontend.chromium_manager.get_chromium_path", return_value=chromium_manager.ChromiumPath("/usr/bin/chromium", True)), \
            mock.patch("frontend.chromium_manager.os.path.exists", return_value=True), \
            mock.patch("frontend.chromium_manager.tempfile.mkdtemp", return_value="/tmp/vpinfe-profile"), \
            mock.patch("frontend.chromium_manager.subprocess.Popen", return_value=proc) as popen:
            manager.launch_window(
                "table",
                "http://127.0.0.1:8000/app/table",
                monitor,
                0,
                additional_options="--disable-accelerated-video-decode\n--ozone-platform=x11",
            )

        args = popen.call_args.args[0]
        self.assertIn("--disable-accelerated-video-decode", args)
        self.assertIn("--ozone-platform=x11", args)

    def test_launch_window_can_disable_default_chromium_options(self) -> None:
        manager = ChromiumManager()
        proc = types.SimpleNamespace()
        monitor = types.SimpleNamespace(x=10, y=20, width=800, height=600)

        with mock.patch("frontend.chromium_manager.get_chromium_path", return_value=chromium_manager.ChromiumPath("/usr/bin/chromium", True)), \
            mock.patch("frontend.chromium_manager.os.path.exists", return_value=True), \
            mock.patch("frontend.chromium_manager.tempfile.mkdtemp", return_value="/tmp/vpinfe-profile"), \
            mock.patch("frontend.chromium_manager.subprocess.Popen", return_value=proc) as popen:
            manager.launch_window(
                "table",
                "http://127.0.0.1:8000/app/table",
                monitor,
                0,
                include_default_options=False,
            )

        args = popen.call_args.args[0]
        self.assertIn("--app=http://127.0.0.1:8000/app/table", args)
        self.assertIn("--window-size=800,600", args)
        self.assertNotIn("--kiosk", args)
        self.assertNotIn("--disable-background-networking", args)

    def test_wait_ignores_exited_launcher_while_window_connected(self) -> None:
        manager = ChromiumManager()
        proc = types.SimpleNamespace(poll=mock.Mock(return_value=0), returncode=0)
        manager._processes = [("table", proc, None, None)]
        connected_states = iter([True, False])
        manager.terminate_all = mock.Mock(side_effect=lambda: manager._exit_event.set())

        manager.wait_for_exit(
            is_window_connected=lambda window_name: next(connected_states, False)
        )

        proc.poll.assert_called()
        manager.terminate_all.assert_called_once()


if __name__ == "__main__":
    unittest.main()
