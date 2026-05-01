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
            self.assertEqual(chromium_manager.get_chromium_path(), bundled)
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
            self.assertEqual(chromium_manager.get_chromium_path(), chrome)

    def test_windows_get_chromium_path_does_not_use_edge_for_slim_build(self) -> None:
        bundled = r"C:\vpinfe\chromium\windows\chrome-win\chrome.exe"
        edge = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"

        def exists(path: str) -> bool:
            return path == edge

        with mock.patch("frontend.chromium_manager.platform.system", return_value="Windows"), \
            mock.patch("frontend.chromium_manager.resource_path", return_value=bundled), \
            mock.patch("frontend.chromium_manager.os.path.expandvars", side_effect=lambda value: edge if "Microsoft\\Edge" in value else value), \
            mock.patch("frontend.chromium_manager.os.path.isfile", side_effect=exists):
            self.assertEqual(chromium_manager.get_chromium_path(), bundled)

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
