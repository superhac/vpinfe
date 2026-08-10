"""The asset server serves what is mounted, and nothing else.

Every path that did not resolve inside a mount used to fall through to
`SimpleHTTPRequestHandler`, which resolves against the working directory - so the whole
install directory was readable over HTTP, `.git` and all, and the server bound every
interface while logging that it had bound loopback. A request that matches no mount is
not a request for a file somewhere else; it is a 404.
"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from frontend.custom_http_server import NOTHING_HERE, CustomHTTPServer


class _Handler(CustomHTTPServer.MultiDirHTTPRequestHandler):
    """The path logic on its own - no socket, no request."""

    def __init__(self, mount_points):
        self.mount_points = mount_points
        self.debug = False


class TranslateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "themes"
        (self.root / "Example").mkdir(parents=True)
        (self.root / "Example" / "index.html").write_text("<html></html>", encoding="utf-8")
        self.handler = _Handler({"/themes/": str(self.root)})

    def _served(self, path: str) -> str:
        return self.handler.translate_path(path)

    def _is_refusal(self, resolved: str) -> bool:
        return resolved.startswith(NOTHING_HERE) and not os.path.exists(resolved)

    def test_a_mounted_file_is_served(self) -> None:
        self.assertEqual(self._served("/themes/Example/index.html"),
                         str(self.root / "Example" / "index.html"))

    def test_an_unmounted_path_is_not_looked_for_in_the_working_directory(self) -> None:
        """The finding: /CLAUDE.local.md and /.git/config both returned 200."""
        for path in ("/main.py", "/.git/config", "/CLAUDE.local.md", "/"):
            self.assertTrue(self._is_refusal(self._served(path)), path)

    def test_a_miss_inside_a_mount_does_not_fall_out_of_it(self) -> None:
        self.assertTrue(self._is_refusal(self._served("/themes/Example/nope.html")))

    def test_climbing_out_of_a_mount_is_refused_rather_than_redirected(self) -> None:
        """It was 'blocked' by resolving against the working directory instead."""
        for path in ("/themes/../../../etc/passwd", "/themes/Example/../../../../etc/hosts"):
            self.assertTrue(self._is_refusal(self._served(path)), path)

    def test_the_refusal_target_is_not_a_real_directory(self) -> None:
        """The whole mechanism rests on this, so it is asserted rather than assumed."""
        self.assertFalse(os.path.exists(NOTHING_HERE))


class BindTests(unittest.TestCase):
    def _bound_to(self, **kwargs) -> tuple:
        server = CustomHTTPServer({})
        with mock.patch("frontend.custom_http_server.ThreadingTCPServer") as tcp, \
             mock.patch("frontend.custom_http_server.threading.Thread"):
            server.start_file_server(port=8123, **kwargs)
        return tcp.call_args[0][0]

    def test_the_file_server_binds_loopback(self) -> None:
        """It serves the table library and the theme packages, and every caller of this
        port builds a 127.0.0.1 url. It bound every interface."""
        self.assertEqual(self._bound_to(), ("127.0.0.1", 8123))

    def test_an_install_can_name_the_address_to_serve_on(self) -> None:
        """An address, not a switch, so one interface can be named rather than every one.
        Opening this port shares read access to the table library, so it is opt-in."""
        self.assertEqual(self._bound_to(bind="0.0.0.0"), ("0.0.0.0", 8123))
        self.assertEqual(self._bound_to(bind="100.64.0.1"), ("100.64.0.1", 8123))


class NetworkConfigTests(unittest.TestCase):
    """The two ports do not share one setting: 8000 serves the table library and 8002
    reaches shutdown_system, so one switch would mean previewing a theme remotely also
    exposed machine control."""

    def _network(self, **settings):
        from configparser import ConfigParser

        from common.config_access import NetworkConfig, cfg_set

        parser = ConfigParser()
        for key, value in settings.items():
            cfg_set(parser, "network", key, value)
        return NetworkConfig.from_config(parser)

    def test_the_defaults_are_what_the_two_servers_already_did(self) -> None:
        network = self._network()

        self.assertEqual(network.theme_assets_bind, "127.0.0.1")
        self.assertEqual(network.hub_bind, "0.0.0.0", "it has always answered all")

    def test_each_address_is_set_on_its_own(self) -> None:
        network = self._network(theme_assets_bind="0.0.0.0")

        self.assertEqual(network.theme_assets_bind, "0.0.0.0")
        self.assertEqual(network.hub_bind, "0.0.0.0", "the other is untouched")

    def test_a_blank_address_falls_back_rather_than_binding_nothing(self) -> None:
        """An empty string binds every interface, which is the opposite of what somebody
        clearing the setting meant."""
        network = self._network(theme_assets_bind="   ", hub_bind="")

        self.assertEqual(network.theme_assets_bind, "127.0.0.1")
        self.assertEqual(network.hub_bind, "0.0.0.0")


if __name__ == "__main__":
    unittest.main()
