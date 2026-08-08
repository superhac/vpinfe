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
    def test_the_file_server_binds_loopback(self) -> None:
        """It serves the table library and the theme packages, and every caller of this
        port builds a 127.0.0.1 url. It bound every interface."""
        server = CustomHTTPServer({})
        with mock.patch("frontend.custom_http_server.ThreadingTCPServer") as tcp, \
             mock.patch("frontend.custom_http_server.threading.Thread"):
            server.start_file_server(port=8123)

        address = tcp.call_args[0][0]
        self.assertEqual(address, ("127.0.0.1", 8123))


if __name__ == "__main__":
    unittest.main()
