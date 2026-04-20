import unittest

from frontend.customhttpserver import CustomHTTPServer


class TestCustomHttpServer(unittest.TestCase):
    def test_allows_only_pinball_primer_urls(self) -> None:
        handler = CustomHTTPServer.MultiDirHTTPRequestHandler

        self.assertTrue(handler._is_allowed_pinball_primer_url("https://pinballprimer.github.io/paddock_GR0W9.html"))
        self.assertFalse(handler._is_allowed_pinball_primer_url("http://pinballprimer.github.io/paddock_GR0W9.html"))
        self.assertFalse(handler._is_allowed_pinball_primer_url("https://example.com/tutorial.html"))

    def test_injects_base_tag_into_head(self) -> None:
        handler = CustomHTTPServer.MultiDirHTTPRequestHandler
        html = "<html><head><title>Test</title></head><body>Hello</body></html>"

        updated = handler._inject_base_tag(html, "https://pinballprimer.github.io/paddock_GR0W9.html")

        self.assertIn('<base href="https://pinballprimer.github.io/paddock_GR0W9.html">', updated)
        self.assertIn("<title>Test</title>", updated)

    def test_injects_base_tag_when_head_missing(self) -> None:
        handler = CustomHTTPServer.MultiDirHTTPRequestHandler
        html = "<html><body>Hello</body></html>"

        updated = handler._inject_base_tag(html, "https://pinballprimer.github.io/paddock_GR0W9.html")

        self.assertTrue(updated.startswith('<head><base href="https://pinballprimer.github.io/paddock_GR0W9.html"></head>'))
