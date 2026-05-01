from __future__ import annotations

import types
import unittest
from unittest import mock

from frontend.chromium_manager import ChromiumManager


class ChromiumManagerTests(unittest.TestCase):
    def test_wait_ignores_exited_launcher_while_window_connected(self) -> None:
        manager = ChromiumManager()
        proc = types.SimpleNamespace(poll=mock.Mock(return_value=0), returncode=0)
        manager._processes = [("table", proc, None, None)]
        connected_states = iter([True, False])
        manager.terminate_all = mock.Mock(side_effect=lambda: manager._exit_event.set())

        manager.wait_for_exit(
            is_window_connected=lambda window_name: next(connected_states, False)
        )

        self.assertGreaterEqual(proc.poll.call_count, 2)
        manager.terminate_all.assert_called_once()


if __name__ == "__main__":
    unittest.main()
