"""A kill signal takes the same way out as a user closing a window."""

from __future__ import annotations

import os
import signal
import sys
import threading
import time
import unittest
from unittest import mock

from common import shutdown
from frontend import runtime


# Windows defines SIGTERM but does not deliver it: os.kill falls through to
# TerminateProcess and the whole run dies, with no failure and no summary. Same guard,
# same reason, as tests/host/test_shutdown.py.
@unittest.skipIf(sys.platform.startswith("win"),
                 "Windows terminates the process instead of delivering SIGTERM")
@unittest.skipIf(not hasattr(signal, "SIGTERM"), "no SIGTERM on this platform")
class TerminationSignalTests(unittest.TestCase):
    def setUp(self):
        for name in ("SIGTERM", "SIGINT", "SIGBREAK"):
            sig = getattr(signal, name, None)
            if sig is not None:
                self.addCleanup(signal.signal, sig, signal.getsignal(sig))
        # Absorb the signal here first. If run_frontend_loop ever stops installing its
        # own handler, these tests have to fail - not kill the whole run, which is what
        # SIGTERM does by default to the process sending it to itself.
        signal.signal(signal.SIGTERM, lambda *_args: None)
        shutdown.reset_for_tests()
        self.addCleanup(shutdown.reset_for_tests)

    def _send_sigterm_shortly(self):
        killer = threading.Timer(0.2, os.kill, (os.getpid(), signal.SIGTERM))
        killer.start()
        self.addCleanup(killer.cancel)

    def _browser_that_waits(self):
        """A stand-in for ChromiumManager: blocks until request_exit is called."""
        exited = threading.Event()
        browser = mock.Mock()
        browser.request_exit.side_effect = exited.set

        def _wait_for_exit(**_kwargs):
            deadline = time.monotonic() + 10.0
            while not exited.wait(0.05):
                if time.monotonic() > deadline:
                    raise AssertionError("the signal never reached request_exit")

        browser.wait_for_exit.side_effect = _wait_for_exit
        return browser

    def test_sigterm_closes_the_windows_and_returns_for_shutdown(self):
        browser = self._browser_that_waits()
        self._send_sigterm_shortly()

        with mock.patch.object(runtime, "get_display_monitors", return_value=[]):
            runtime.run_frontend_loop(
                False,
                mock.Mock(is_new=False),
                browser,
                threading.Event(),
                mock.Mock(),
            )

        browser.terminate_all.assert_called_once_with()

    def test_sigterm_ends_the_headless_loop(self):
        shutdown_event = threading.Event()
        self._send_sigterm_shortly()
        failsafe = threading.Timer(10.0, shutdown_event.set)
        failsafe.start()
        self.addCleanup(failsafe.cancel)
        started = time.monotonic()

        runtime.run_frontend_loop(True, mock.Mock(), mock.Mock(), shutdown_event, mock.Mock())

        self.assertLess(time.monotonic() - started, 5.0, "the signal never ended the loop")

    def test_a_closed_window_still_ends_the_loop_without_a_signal(self):
        browser = mock.Mock()
        browser.wait_for_exit.side_effect = lambda **_kwargs: None

        with mock.patch.object(runtime, "get_display_monitors", return_value=[]):
            runtime.run_frontend_loop(
                False,
                mock.Mock(is_new=False),
                browser,
                threading.Event(),
                mock.Mock(),
            )

        browser.launch_all_windows.assert_called_once()
        browser.terminate_all.assert_called_once_with()

    def test_a_signal_during_startup_stops_the_frontend_opening_at_all(self):
        browser = self._browser_that_waits()
        shutdown.watch_during_startup()
        os.kill(os.getpid(), signal.SIGTERM)

        with mock.patch.object(runtime, "get_display_monitors", return_value=[]):
            runtime.run_frontend_loop(
                False,
                mock.Mock(is_new=False),
                browser,
                threading.Event(),
                mock.Mock(),
            )

        browser.launch_all_windows.assert_not_called()
        browser.wait_for_exit.assert_not_called()


if __name__ == "__main__":
    unittest.main()
