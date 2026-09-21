"""Where a 2.x `alt_vpsid` ends up, decided by what the id it holds actually names."""

from __future__ import annotations

import copy
import unittest
from unittest.mock import patch

from common.games.game_service import classify_vps_id, route_legacy_match

ENTRY = "kGBkVb-v"
RELEASE = "butCgIcLzI"

CATALOG = [
    {"id": ENTRY, "name": "AC/DC (LUCI Premium)", "manufacturer": "Stern",
     "year": 2013, "tableFiles": [{"id": RELEASE, "version": "1.1.3"}]},
]

RECORD = {
    "Info": {"Title": "AC/DC", "VPSId": ENTRY},
    "vpinfe": {"game_id": "g-0001", "alt_vpsid": RELEASE},
    "tables": {"tbl001": {"id": "tbl001", "filename": "AC-DC.vpx"}},
}


class RoutingCase(unittest.TestCase):
    def setUp(self) -> None:
        patcher = patch("common.games.game_service.load_vpsdb",
                        return_value=copy.deepcopy(CATALOG))
        self.catalog = patcher.start()
        self.addCleanup(patcher.stop)

    def _route(self, alt: str) -> tuple[str, dict]:
        data = copy.deepcopy(RECORD)
        data["vpinfe"]["alt_vpsid"] = alt
        return route_legacy_match(data, "AC-DC (Stern 2013)"), data


class ClassifyTests(RoutingCase):
    def test_an_entry_id_is_a_machine(self) -> None:
        self.assertEqual(classify_vps_id(ENTRY), "entry")

    def test_a_table_file_id_is_a_release(self) -> None:
        self.assertEqual(classify_vps_id(RELEASE), "release")

    def test_an_id_the_catalog_does_not_hold_is_neither(self) -> None:
        self.assertEqual(classify_vps_id("nosuchid"), "")


class RouteTests(RoutingCase):
    def test_a_release_id_binds_to_the_default_table(self) -> None:
        done, data = self._route(RELEASE)

        self.assertEqual(done, "bound")
        self.assertEqual(data["vpinfe"]["alt_vpsid"], "")
        source = data["tables"]["tbl001"]["source"]
        self.assertEqual(source["vps_file_id"], RELEASE)
        self.assertEqual(source["confirmed_by"], "user")

    def test_an_entry_id_stays_as_the_match(self) -> None:
        done, data = self._route(ENTRY)

        self.assertEqual(done, "kept")
        self.assertEqual(data["vpinfe"]["alt_vpsid"], ENTRY)
        self.assertNotIn("source", data["tables"]["tbl001"])

    def test_an_id_the_catalog_does_not_hold_is_dropped(self) -> None:
        done, data = self._route("nosuchid")

        self.assertEqual(done, "dropped")
        self.assertEqual(data["vpinfe"]["alt_vpsid"], "")

    def test_a_record_with_no_match_is_left_alone(self) -> None:
        done, data = self._route("")

        self.assertEqual(done, "")
        self.assertEqual(data["vpinfe"]["alt_vpsid"], "")

    def test_binding_keeps_what_the_source_block_already_held(self) -> None:
        """A file we built carries the base and the patch that made it, and which
        upstream record it is answers a different question about the same file."""
        data = copy.deepcopy(RECORD)
        data["tables"]["tbl001"]["source"] = {"base": "Old.vpx", "patch": "p.jdiff"}

        route_legacy_match(data, "AC-DC (Stern 2013)")

        source = data["tables"]["tbl001"]["source"]
        self.assertEqual(source["base"], "Old.vpx")
        self.assertEqual(source["vps_file_id"], RELEASE)


class NoCatalogTests(unittest.TestCase):
    def test_nothing_is_routed_while_the_catalog_is_empty(self) -> None:
        data = copy.deepcopy(RECORD)
        with patch("common.games.game_service.load_vpsdb", return_value=[]):
            done = route_legacy_match(data, "AC-DC (Stern 2013)")

        self.assertEqual(done, "")
        self.assertEqual(data["vpinfe"]["alt_vpsid"], RELEASE)


if __name__ == "__main__":
    unittest.main()
