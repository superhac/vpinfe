"""BrowserSession must not leak a process or a profile when its handshake fails."""

from __future__ import annotations

import asyncio
import os
import unittest
from unittest import mock

from tests.support import browser_session


class _FakeChromeProcess:
    """Enough of `subprocess.Popen` for `__aenter__`/`__aexit__` to run against."""

    def __init__(self) -> None:
        self.terminated = False
        self.stdout = None
        self.stderr = None
        self.stdin = None

    def terminate(self) -> None:
        self.terminated = True

    def wait(self, timeout: float | None = None) -> int:
        return 0

    def poll(self) -> int | None:
        return None


class HandshakeFailureTests(unittest.TestCase):
    def test_a_handshake_that_never_finishes_stops_the_process_and_its_profile(self) -> None:
        fake_proc = _FakeChromeProcess()

        async def enter_and_fail() -> browser_session.BrowserSession:
            session = browser_session.BrowserSession("ignored-binary")
            with mock.patch.object(browser_session.subprocess, "Popen",
                                   return_value=fake_proc), \
                    mock.patch.object(browser_session.BrowserSession, "_page_endpoint",
                                      side_effect=RuntimeError("never came up")), \
                    self.assertRaises(RuntimeError):
                async with session:
                    pass
            return session

        session = asyncio.run(enter_and_fail())
        profile = session._profile

        self.assertTrue(fake_proc.terminated)
        self.assertIsNotNone(profile)
        assert profile is not None  # for the type checker; asserted above
        self.assertFalse(os.path.exists(profile))


if __name__ == "__main__":
    unittest.main()
