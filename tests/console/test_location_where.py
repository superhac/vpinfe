"""The Where column: this device, or the server whose share holds the folder."""

from __future__ import annotations

import unittest
from typing import Any

from common.i18n import t
from console import locations

WIRE = {"location_id": "one", "name": "pinball/tables", "path": "/mnt/nas/tables",
        "kind": "root", "state": "ready", "reachable": True, "writable": True,
        "reason": "", "write_to": False, "shadowed": 0}


def _row(**wire: Any) -> dict[str, Any]:
    return locations.rows([{**WIRE, **wire}])[0]


class WhereColumnTests(unittest.TestCase):
    def test_a_folder_on_this_device_says_so_with_nothing_to_tip(self) -> None:
        row = _row(where="local", origin=None)

        self.assertEqual((row["where"], row["where_tip"]), (t("word.this_device"), ""))

    def test_a_folder_on_a_share_names_its_server_and_tips_the_share(self) -> None:
        row = _row(where="system", origin={"server": "nas.lan",
                                           "source": "nas.lan:/export/pinball"})

        self.assertEqual((row["where"], row["where_tip"]),
                         ("nas.lan", "nas.lan:/export/pinball"))


if __name__ == "__main__":
    unittest.main()
