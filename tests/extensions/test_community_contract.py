"""A list an extension declares for Community, and the ones it may not."""

from __future__ import annotations

import unittest

from common.extensions.context import ContractError, ExtensionUI

COLUMNS = [{"field": "name", "header": "Table"},
           {"field": "plays", "header": "Plays", "kind": "number"},
           {"field": "vpsId", "header": "VPS"}]


class TheDeclaration(unittest.TestCase):
    def setUp(self) -> None:
        self.ui = ExtensionUI("site", allowed=True)

    def test_a_list_is_recorded_as_data(self) -> None:
        self.ui.community("tables", "Site", "/community/tables", columns=COLUMNS,
                          views=[{"name": "Most played", "columns": ["name", "plays"],
                                  "sort": [{"field": "plays", "desc": True}]}],
                          relation={"field": "vpsId", "keys": "vps_entry"})

        (said,) = self.ui.community_lists
        self.assertEqual(("tables", ["text", "number", "text"],
                          [{"field": "plays", "desc": True}], "vps_entry"),
                         (said["key"], [one["kind"] for one in said["columns"]],
                          said["views"][0]["sort"], said["relation"]["keys"]))

    def test_a_kind_core_does_not_draw_is_refused(self) -> None:
        with self.assertRaises(ContractError):
            self.ui.community("tables", "Site", "/t",
                              columns=[{"field": "art", "header": "Art", "kind": "html"}])

    def test_a_view_on_a_column_it_does_not_have_is_refused(self) -> None:
        with self.assertRaises(ContractError):
            self.ui.community("tables", "Site", "/t", columns=COLUMNS,
                              views=[{"name": "Top", "sort": [{"field": "rating"}]}])

    def test_a_relation_by_anything_but_a_vps_id_is_refused(self) -> None:
        with self.assertRaises(ContractError):
            self.ui.community("tables", "Site", "/t", columns=COLUMNS,
                              relation={"field": "name", "keys": "rom"})

    def test_it_needs_the_capability_to_draw(self) -> None:
        with self.assertRaises(ContractError):
            ExtensionUI("site", allowed=False).community("tables", "Site", "/t",
                                                         columns=COLUMNS)


if __name__ == "__main__":
    unittest.main()
