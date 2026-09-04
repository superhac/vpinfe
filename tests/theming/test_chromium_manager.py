from __future__ import annotations

import threading
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

        def expandvars(value: str) -> str:
            return chrome if "Google\\Chrome" in value else value

        with (
            mock.patch("frontend.chromium_manager.platform.system", return_value="Windows"),
            mock.patch("frontend.chromium_manager.resource_path", return_value=bundled),
            mock.patch("frontend.chromium_manager.os.path.expandvars",
                       side_effect=expandvars),
            mock.patch("frontend.chromium_manager.os.path.isfile", side_effect=exists),
        ):
            self.assertEqual(
                chromium_manager.get_chromium_path(),
                chromium_manager.ChromiumPath(chrome, True),
            )

    def test_windows_get_chromium_path_does_not_use_edge_for_slim_build(self) -> None:
        bundled = r"C:\vpinfe\chromium\windows\chrome-win\chrome.exe"
        edge = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"

        def exists(path: str) -> bool:
            return path == edge

        def expandvars(value: str) -> str:
            return edge if "Microsoft\\Edge" in value else value

        with (
            mock.patch("frontend.chromium_manager.platform.system", return_value="Windows"),
            mock.patch("frontend.chromium_manager.resource_path", return_value=bundled),
            mock.patch("frontend.chromium_manager.os.path.expandvars",
                       side_effect=expandvars),
            mock.patch("frontend.chromium_manager.os.path.isfile", side_effect=exists),
        ):
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

        chromium = chromium_manager.ChromiumPath("/usr/bin/chromium", True)
        with (
            mock.patch("frontend.chromium_manager.get_chromium_path", return_value=chromium),
            mock.patch("frontend.chromium_manager.os.path.exists", return_value=True),
            mock.patch("frontend.chromium_manager.tempfile.mkdtemp",
                       return_value="/tmp/vpinfe-profile"),
            mock.patch("frontend.chromium_manager.subprocess.Popen", return_value=proc) as popen,
        ):
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

    def test_a_stray_quote_in_the_exclusions_does_not_stop_the_launch(self) -> None:
        """A typo in a text field cost the whole frontend. `chrome_options` was
        guarded and `chrome_options_exclude` was not, though both are the same
        setting shape parsed by the same function - so an unbalanced quote in the
        second raised out of the args list and every window went with it."""
        manager = ChromiumManager()
        proc = types.SimpleNamespace()
        monitor = types.SimpleNamespace(x=10, y=20, width=800, height=600)

        chromium = chromium_manager.ChromiumPath("/usr/bin/chromium", True)
        with (
            mock.patch("frontend.chromium_manager.get_chromium_path", return_value=chromium),
            mock.patch("frontend.chromium_manager.os.path.exists", return_value=True),
            mock.patch("frontend.chromium_manager.tempfile.mkdtemp",
                       return_value="/tmp/vpinfe-profile"),
            mock.patch("frontend.chromium_manager.subprocess.Popen", return_value=proc) as popen,
        ):
            manager.launch_window(
                "table",
                "http://127.0.0.1:8000/app/table",
                monitor,
                0,
                mute_audio=True,
                exclude_options='--mute-audio "',
            )

        args = popen.call_args.args[0]
        self.assertTrue(args, "the window still launches")
        # The exclusion is ignored rather than half-applied: nothing was excluded,
        # so the default it named is still there.
        self.assertIn("--mute-audio", args)

    def test_a_stray_quote_in_the_options_does_not_stop_the_launch(self) -> None:
        manager = ChromiumManager()
        proc = types.SimpleNamespace()
        monitor = types.SimpleNamespace(x=10, y=20, width=800, height=600)

        chromium = chromium_manager.ChromiumPath("/usr/bin/chromium", True)
        with (
            mock.patch("frontend.chromium_manager.get_chromium_path", return_value=chromium),
            mock.patch("frontend.chromium_manager.os.path.exists", return_value=True),
            mock.patch("frontend.chromium_manager.tempfile.mkdtemp",
                       return_value="/tmp/vpinfe-profile"),
            mock.patch("frontend.chromium_manager.subprocess.Popen", return_value=proc) as popen,
        ):
            manager.launch_window(
                "table",
                "http://127.0.0.1:8000/app/table",
                monitor,
                0,
                additional_options='--ozone-platform=x11 "',
            )

        self.assertTrue(popen.call_args.args[0])

    def test_launch_window_can_disable_default_chromium_options(self) -> None:
        manager = ChromiumManager()
        proc = types.SimpleNamespace()
        monitor = types.SimpleNamespace(x=10, y=20, width=800, height=600)

        chromium = chromium_manager.ChromiumPath("/usr/bin/chromium", True)
        with (
            mock.patch("frontend.chromium_manager.get_chromium_path", return_value=chromium),
            mock.patch("frontend.chromium_manager.os.path.exists", return_value=True),
            mock.patch("frontend.chromium_manager.tempfile.mkdtemp",
                       return_value="/tmp/vpinfe-profile"),
            mock.patch("frontend.chromium_manager.subprocess.Popen", return_value=proc) as popen,
        ):
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

    def test_request_exit_unblocks_a_wait_without_closing_the_windows(self) -> None:
        manager = ChromiumManager()
        proc = types.SimpleNamespace(poll=mock.Mock(return_value=None), returncode=None)
        manager._processes = [("table", proc, None, None)]
        threading.Timer(0.1, manager.request_exit).start()

        manager.wait_for_exit()

        self.assertEqual(manager._processes, [("table", proc, None, None)])

    def test_terminate_all_is_a_no_op_once_the_windows_are_gone(self) -> None:
        manager = ChromiumManager()

        manager.terminate_all()

        self.assertTrue(manager._exit_event.is_set())


class LibraryEndpointTests(unittest.TestCase):
    """Reading `network.library_url` into the three values a window url carries."""

    @staticmethod
    def _network(library_url: str = "", http_port: int = 8001, assets_port: int = 8000):
        return types.SimpleNamespace(library_url=library_url, http_port=http_port,
                                     theme_assets_port=assets_port)

    def _resolve(self, *args, services=None, **kwargs):
        """That install's own ports come from its discovery document, so a test says
        what it published rather than reaching a real one."""
        with mock.patch.object(chromium_manager.remote_library, "remote_services",
                               return_value=services or {}):
            return chromium_manager._library_endpoint(self._network(*args, **kwargs))

    def test_no_library_set_and_both_ports_are_this_install(self) -> None:
        for value in ("", "   "):
            with self.subTest(value=value):
                self.assertEqual(self._resolve(value), ("", 8001, 8001, 8000))

    def test_a_library_url_yields_its_host_and_port(self) -> None:
        self.assertEqual(self._resolve("http://cab.local:8001"),
                         ("cab.local", 8001, 8001, 8000))

    def test_the_library_port_and_this_machine_s_port_are_answered_separately(self) -> None:
        """The one that would misdial in both directions if a single number were sent."""
        self.assertEqual(self._resolve("https://library.example:9000"),
                         ("library.example", 9000, 8001, 8000))

    def test_a_url_with_no_port_falls_back_to_this_install_s(self) -> None:
        self.assertEqual(self._resolve("http://cab.local", 8005),
                         ("cab.local", 8005, 8005, 8000))


    def test_the_library_s_asset_port_comes_from_the_library(self) -> None:
        """It is in no url and cannot be guessed: artwork is served on a different port
        from the api, and this install's own number describes the wrong machine."""
        resolved = self._resolve("https://library.example:9000",
                                 services={"assets": {"port": 9500}})

        self.assertEqual(resolved, ("library.example", 9000, 8001, 9500))

    def test_a_library_that_says_nothing_leaves_this_install_s_answer(self) -> None:
        """An older install, or one that could not be reached for its discovery document."""
        for services in ({}, {"assets": {}}, {"assets": {"port": "nonsense"}}):
            with self.subTest(services=services):
                self.assertEqual(
                    self._resolve("https://library.example:9000", services=services).assets_port,
                    8000)


class WindowUrlTests(unittest.TestCase):
    """A window has to be told where the services are: it cannot ask, because asking
    needs the bridge and finding the bridge needs a port. A port missing here is a
    frontend dialling the wrong one forever, which is why every form is checked."""

    def _url(self, system: str, *, splash: bool = False, library_host: str = "",
             http_port: int = 9001, device_port: int = 9001) -> str:
        with mock.patch("frontend.chromium_manager.platform.system", return_value=system):
            return chromium_manager._build_window_url(
                base_url="http://127.0.0.1",
                theme_assets_port=9000,
                theme_name="Some Theme",
                window_name="playfield",
                splash_enabled=splash,
                ws_port=9002,
                http_port=http_port,
                library_host=library_host,
                device_port=device_port,
            )

    def test_every_window_url_carries_every_port(self) -> None:
        for system, splash, label in (("Linux", False, "the /app/ bootstrap"),
                                      ("Darwin", True, "the splash page"),
                                      ("Darwin", False, "a theme page")):
            with self.subTest(label):
                url = self._url(system, splash=splash)

                self.assertIn("wsPort=9002", url)
                self.assertIn("themeAssetsPort=9000", url)
                self.assertIn("libraryPort=9001", url)

    def test_no_library_host_leaves_the_url_as_it_was(self) -> None:
        """Every single-machine install. The page keeps assuming loopback for everything,
        so a setting nobody set cannot change what a window opens with."""
        for system, splash, label in (("Linux", False, "the /app/ bootstrap"),
                                      ("Darwin", True, "the splash page"),
                                      ("Darwin", False, "a theme page")):
            with self.subTest(label):
                url = self._url(system, splash=splash)

                self.assertNotIn("libraryHost", url)
                self.assertNotIn("devicePort", url)

    def test_a_remote_library_travels_in_every_window_url(self) -> None:
        """A page cannot ask where its library is for the same reason it cannot ask for a
        port, so the host takes the same route."""
        for system, splash, label in (("Linux", False, "the /app/ bootstrap"),
                                      ("Darwin", True, "the splash page"),
                                      ("Darwin", False, "a theme page")):
            with self.subTest(label):
                url = self._url(system, splash=splash, library_host="library.example")

                self.assertIn("libraryHost=library.example", url)

    def test_the_library_port_and_this_machine_s_port_travel_separately(self) -> None:
        """A library on 9000 is not this machine on 9000. Sending one number would make an
        install dial its own api at the library's port, or the library's at its own."""
        url = self._url("Darwin", library_host="library.example", http_port=9000,
                        device_port=8001)

        self.assertIn("libraryPort=9000", url)
        self.assertIn("devicePort=8001", url)

    def test_a_host_that_needs_encoding_is_encoded(self) -> None:
        url = self._url("Darwin", library_host="library name")

        self.assertIn("libraryHost=library%20name", url)

    def test_the_ports_are_query_parameters_of_the_page(self) -> None:
        """Appended to whatever the form already asks for, not replacing it."""
        url = self._url("Darwin")

        self.assertIn("index_playfield.html?window=playfield&", url)


if __name__ == "__main__":
    unittest.main()
