"""Who is allowed to open the device channel.

The channel reaches `shutdown_system`, `launch_table` and `build_metadata`, and binding it
to loopback does not keep other pages out: a WebSocket handshake is not subject to the
same-origin policy the way XHR is, so any page in any browser on this machine could
connect. The origin check is what actually keeps them out, so it is asserted against a
real handshake rather than only against the predicate.
"""

from __future__ import annotations

import asyncio
import unittest

import websockets

from frontend.device_channel import DeviceChannel


class OriginPredicateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.channel = DeviceChannel(port=0)

    def test_a_window_served_from_this_machine_is_allowed(self) -> None:
        for origin in ("http://127.0.0.1:8000", "http://localhost:8000",
                       "http://127.0.0.1:54321", "http://[::1]:8000"):
            with self.subTest(origin=origin):
                self.assertTrue(self.channel._origin_allowed(origin))

    def test_a_page_from_anywhere_else_is_refused(self) -> None:
        for origin in ("http://evil.example.com", "https://mail.google.com",
                       "http://192.168.1.10:8000", "null",
                       # A name is not a prefix match: these resolve wherever their
                       # owner points them, and both read as loopback at a glance.
                       "http://127.0.0.1.evil.com", "http://localhost.evil.com"):
            with self.subTest(origin=origin):
                self.assertFalse(self.channel._origin_allowed(origin))

    def test_no_origin_at_all_is_allowed(self) -> None:
        """A non-browser client sends none. It already runs code here, so refusing it
        stops nothing and would break scripts that legitimately drive the channel."""
        self.assertTrue(self.channel._origin_allowed(None))


class OriginHandshakeTests(unittest.IsolatedAsyncioTestCase):
    """Against a running server, because the predicate being right is only half of it -
    the header has to be read off the handshake, and that is websockets-version specific."""

    async def asyncSetUp(self) -> None:
        from tests.support.browser_session import free_port

        self.channel = DeviceChannel(port=free_port())
        # A real window is one this process opened, so it has an API registered before
        # its browser is launched. Without that the channel refuses the name outright
        # and the origin check never runs.
        self.channel.register_api("bg", object())
        self.channel.start()
        self.addCleanup(self.channel.stop)
        await asyncio.sleep(0.5)

    async def _connect(self, origin):
        """Open a connection and wait long enough to see whether it is closed on us.

        An accepted channel simply goes quiet - the server says nothing until asked - so
        silence is the pass and a close frame is the refusal.
        """
        extra = {"additional_headers": {"Origin": origin}} if origin else {}
        url = f"ws://127.0.0.1:{self.channel.port}/?window=bg"
        async with websockets.connect(url, **extra) as socket:
            with self.assertRaises(TimeoutError):
                await asyncio.wait_for(socket.recv(), timeout=0.3)
            # While it is still open: registration is undone on disconnect.
            return self.channel.is_window_connected("bg")

    async def test_a_real_window_connects(self) -> None:
        self.assertTrue(await self._connect("http://127.0.0.1:8000"))

    async def test_a_hostile_page_is_closed_and_never_registers(self) -> None:
        with self.assertRaises(websockets.exceptions.ConnectionClosed) as caught:
            await self._connect("https://mail.google.com")

        self.assertEqual(caught.exception.rcvd.code, 1008)
        self.assertFalse(self.channel.is_window_connected("bg"),
                         "a refused connection must not displace a real window")


if __name__ == "__main__":
    unittest.main()
