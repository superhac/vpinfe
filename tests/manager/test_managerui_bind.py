"""The address the Manager UI listens on reaches the server that binds it.

The setting is only worth having if it arrives: `NetworkConfig` reading it correctly and
`ui.run` still being handed a hardcoded host would look right everywhere except on the
socket, and the default is the value that hides that - it is what the code said before.
"""

from __future__ import annotations

import unittest
from unittest import mock

from managerui import managerui


class ManagerUiBindTests(unittest.TestCase):
    def setUp(self) -> None:
        self.addCleanup(setattr, managerui, "_ui_bind", managerui._ui_bind)
        self.addCleanup(setattr, managerui, "_ui_port", managerui._ui_port)

    def _ran_with(self, **kwargs) -> dict:
        """What `_run_ui` would hand NiceGUI, without starting a server."""
        managerui._ui_bind = kwargs.get("bind", "0.0.0.0")
        managerui._ui_port = kwargs.get("port", 8001)
        with mock.patch.object(managerui, "ui") as nicegui, \
             mock.patch.object(managerui, "_manager_ui_urls", return_value=[]):
            managerui._run_ui()
        return nicegui.run.call_args.kwargs

    def test_it_answers_every_interface_by_default(self) -> None:
        """What it has always done: a cabinet is administered from another machine."""
        self.assertEqual(self._ran_with()["host"], "0.0.0.0")

    def test_an_install_can_pull_it_back_to_this_machine(self) -> None:
        self.assertEqual(self._ran_with(bind="127.0.0.1")["host"], "127.0.0.1")

    def test_the_port_still_arrives_with_it(self) -> None:
        ran = self._ran_with(bind="127.0.0.1", port=9001)

        self.assertEqual((ran["host"], ran["port"]), ("127.0.0.1", 9001))


if __name__ == "__main__":
    unittest.main()
