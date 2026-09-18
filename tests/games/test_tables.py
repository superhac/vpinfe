import unittest

from common.games.tables import default_table, is_parsed, table_names


class TableNamesTests(unittest.TestCase):
    def test_only_vpx_files_count(self) -> None:
        names = ["Table.vpx", "Table.vbs", "Table.directb2s", "notes.txt", "Table.VPX"]

        self.assertEqual(table_names(names), ["Table.vpx", "Table.VPX"])

    def test_order_does_not_depend_on_the_listing(self) -> None:
        forwards = table_names(["b.vpx", "A.vpx", "c.vpx"])
        backwards = table_names(["c.vpx", "A.vpx", "b.vpx"])

        self.assertEqual(forwards, backwards)
        self.assertEqual(forwards, ["A.vpx", "b.vpx", "c.vpx"])


class DefaultTableTests(unittest.TestCase):
    """Which .vpx is 'the' table. Every caller has to agree, or metadata describes
    one file while another launches."""

    def test_the_recorded_file_wins(self) -> None:
        names = ["Alt Build.vpx", "The Table (Bally 1990).vpx"]

        chosen = default_table(names, "The Table (Bally 1990)", "Alt Build.vpx")

        self.assertEqual(chosen, "Alt Build.vpx",
                         "the metadata and media were built against this one")

    def test_a_recorded_file_that_is_absent_is_ignored(self) -> None:
        names = ["Alt Build.vpx", "The Table (Bally 1990).vpx"]

        chosen = default_table(names, "The Table (Bally 1990)", "gone.vpx")

        self.assertEqual(chosen, "The Table (Bally 1990).vpx", "falls to the folder name")

    def test_the_folder_name_breaks_the_tie(self) -> None:
        names = ["aaa mod.vpx", "The Table (Bally 1990).vpx"]

        chosen = default_table(names, "The Table (Bally 1990)")

        self.assertEqual(chosen, "The Table (Bally 1990).vpx",
                         "not 'aaa mod.vpx', which sorts first")

    def test_folder_name_match_is_case_insensitive(self) -> None:
        chosen = default_table(["zzz.vpx", "THE TABLE.vpx"], "The Table")

        self.assertEqual(chosen, "THE TABLE.vpx")

    def test_otherwise_the_first_by_name_wins(self) -> None:
        names = ["b build.vpx", "a build.vpx"]

        chosen = default_table(names, "Some Folder")

        self.assertEqual(chosen, "a build.vpx", "deterministic, not directory order")

    def test_a_folder_with_no_tables_resolves_to_nothing(self) -> None:
        self.assertEqual(default_table(["readme.txt"], "Some Folder"), "")

    def test_the_answer_never_depends_on_listing_order(self) -> None:
        names = ["c.vpx", "a.vpx", "Folder.vpx", "b.vpx"]

        first = default_table(names, "Folder")
        shuffled = default_table(list(reversed(names)), "Folder")

        self.assertEqual(first, shuffled)


class IsParsedTests(unittest.TestCase):
    """An entry exists for two different reasons: because we read the .vpx, or because
    somebody decided something about it. Only the first says anything about the build."""

    def test_a_parsed_entry_is_parsed(self) -> None:
        self.assertTrue(is_parsed({"file_hash": "3a77427e", "rom": "afm_113b"}))

    def test_an_empty_rom_still_counts_as_parsed(self) -> None:
        """An EM game declares no ROM. That is an answer, not an absence of one."""
        self.assertTrue(is_parsed({"file_hash": "3a77427e", "rom": ""}))

    def test_a_decision_alone_is_not_a_parse(self) -> None:
        """Hiding a table records what the user wants, not what the file says."""
        self.assertFalse(is_parsed({"hidden": True}))

    def test_junk_is_not_a_parse(self) -> None:
        for bad in (None, {}, [], "nope"):
            with self.subTest(entry=bad):
                self.assertFalse(is_parsed(bad))


if __name__ == "__main__":
    unittest.main()
