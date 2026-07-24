import configparser
import unittest
from types import SimpleNamespace

from frontend import input_api
from frontend.api import API
from frontend.table_state import page_jump_index


def _table(title):
    return SimpleNamespace(metaConfig={"Info": {"Title": title}})


def _tables(*titles):
    return [_table(title) for title in titles]


class TestPageJumpIndexAlpha(unittest.TestCase):
    def setUp(self):
        # Alpha-sorted list: groups #(2), A(2), B(1), C(3)
        self.tables = _tables(
            "24", "4x4", "Attack", "Avalanche", "Bally Hoo", "Cactus", "Comet", "Cyclone"
        )

    def test_next_jumps_to_first_of_next_letter(self):
        self.assertEqual(page_jump_index(self.tables, 2, "next"), 4)

    def test_next_from_mid_group_skips_rest_of_group(self):
        self.assertEqual(page_jump_index(self.tables, 5, "next"), 0)

    def test_next_wraps_to_number_bucket(self):
        self.assertEqual(page_jump_index(self.tables, 7, "next"), 0)

    def test_prev_jumps_to_first_of_previous_letter(self):
        self.assertEqual(page_jump_index(self.tables, 4, "prev"), 2)

    def test_prev_from_mid_group_goes_to_previous_group_start(self):
        self.assertEqual(page_jump_index(self.tables, 6, "prev"), 4)

    def test_prev_wraps_from_number_bucket_to_last_group(self):
        self.assertEqual(page_jump_index(self.tables, 0, "prev"), 5)

    def test_numbers_and_symbols_share_one_bucket(self):
        tables = _tables("24", "4x4", "(Secret)", "Attack")
        self.assertEqual(page_jump_index(tables, 0, "next"), 3)

    def test_descending_alpha_order_still_groups(self):
        tables = _tables("Cactus", "Bally Hoo", "Attack", "Avalanche")
        self.assertEqual(page_jump_index(tables, 0, "next"), 1)
        self.assertEqual(page_jump_index(tables, 3, "prev"), 1)

    def test_single_letter_group_falls_back_to_numeric(self):
        tables = _tables("Attack", "Avalanche", "Aztec", "Airborne")
        # Numeric fallback: step = min(10, 4 // 2) = 2
        self.assertEqual(page_jump_index(tables, 0, "next"), 2)

    def test_non_alpha_sort_falls_back_to_numeric(self):
        result = page_jump_index(self.tables, 0, "next", sort_type="LastRun", page_size=3)
        self.assertEqual(result, 3)


class TestPageJumpIndexNumeric(unittest.TestCase):
    def test_next_steps_by_page_size(self):
        tables = _tables(*[f"T{i:02d}" for i in range(30)])
        self.assertEqual(page_jump_index(tables, 0, "next", paging_type="numeric", page_size=10), 10)

    def test_prev_steps_back_and_wraps(self):
        tables = _tables(*[f"T{i:02d}" for i in range(30)])
        self.assertEqual(page_jump_index(tables, 5, "prev", paging_type="numeric", page_size=10), 25)

    def test_step_caps_at_half_the_list(self):
        # 15 tables, size 10: uncapped this would land 10 ahead, which reads as
        # moving backward 5 on a circular wheel. Cap keeps it at 7.
        tables = _tables(*[f"T{i:02d}" for i in range(15)])
        self.assertEqual(page_jump_index(tables, 0, "next", paging_type="numeric", page_size=10), 7)

    def test_two_tables_step_one(self):
        tables = _tables("Alpha", "Bravo")
        self.assertEqual(page_jump_index(tables, 0, "next", paging_type="numeric", page_size=10), 1)

    def test_single_table_is_noop(self):
        tables = _tables("Alpha")
        self.assertEqual(page_jump_index(tables, 0, "next", paging_type="numeric"), 0)

    def test_empty_list_returns_index(self):
        self.assertEqual(page_jump_index([], 3, "next"), 3)

    def test_out_of_range_index_is_normalized(self):
        tables = _tables(*[f"T{i:02d}" for i in range(10)])
        self.assertEqual(page_jump_index(tables, 12, "next", paging_type="numeric", page_size=3), 5)


class TestGetPagingConfig(unittest.TestCase):
    def _config(self, **input_values):
        parser = configparser.ConfigParser()
        parser.add_section("Input")
        for key, value in input_values.items():
            parser.set("Input", key, value)
        return parser

    def test_defaults_when_unset(self):
        self.assertEqual(input_api.get_paging_config(self._config()), ("alpha", 10))

    def test_reads_configured_values(self):
        config = self._config(pagingtype="numeric", pagingsize="25")
        self.assertEqual(input_api.get_paging_config(config), ("numeric", 25))

    def test_invalid_values_fall_back_to_defaults(self):
        config = self._config(pagingtype="bogus", pagingsize="zero")
        self.assertEqual(input_api.get_paging_config(config), ("alpha", 10))

    def test_nonpositive_size_falls_back(self):
        config = self._config(pagingsize="0")
        self.assertEqual(input_api.get_paging_config(config), ("alpha", 10))


class TestApiGetPageIndex(unittest.TestCase):
    def _api(self, tables, sort_type="Alpha", **input_values):
        parser = configparser.ConfigParser()
        parser.add_section("Input")
        for key, value in input_values.items():
            parser.set("Input", key, value)
        api = API.__new__(API)
        api._iniConfig = SimpleNamespace(config=parser)
        api.filteredTables = tables
        api.current_sort = sort_type
        return api

    def test_alpha_paging_over_current_view(self):
        api = self._api(_tables("Attack", "Avalanche", "Bally Hoo", "Cactus"))
        self.assertEqual(api.get_page_index(0, "next"), 2)
        self.assertEqual(api.get_page_index(0, "prev"), 3)

    def test_numeric_config_is_honored(self):
        api = self._api(
            _tables(*[f"T{i:02d}" for i in range(20)]),
            pagingtype="numeric",
            pagingsize="5",
        )
        self.assertEqual(api.get_page_index(0, "next"), 5)

    def test_non_alpha_sort_uses_numeric_fallback(self):
        api = self._api(
            _tables(*[f"T{i:02d}" for i in range(20)]),
            sort_type="LastRun",
            pagingsize="4",
        )
        self.assertEqual(api.get_page_index(0, "next"), 4)

    def test_bad_index_from_theme_is_coerced(self):
        api = self._api(_tables("Attack", "Bally Hoo", "Cactus"))
        self.assertEqual(api.get_page_index("not-a-number", "next"), 1)


if __name__ == "__main__":
    unittest.main()
