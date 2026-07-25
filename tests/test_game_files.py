import unittest

from common.tables.game_files import default_game_file, game_file_names


class GameFileNamesTests(unittest.TestCase):
    def test_only_vpx_files_count(self) -> None:
        names = ["Table.vpx", "Table.vbs", "Table.directb2s", "notes.txt", "Table.VPX"]

        self.assertEqual(game_file_names(names), ["Table.vpx", "Table.VPX"])

    def test_order_does_not_depend_on_the_listing(self) -> None:
        forwards = game_file_names(["b.vpx", "A.vpx", "c.vpx"])
        backwards = game_file_names(["c.vpx", "A.vpx", "b.vpx"])

        self.assertEqual(forwards, backwards)
        self.assertEqual(forwards, ["A.vpx", "b.vpx", "c.vpx"])


class DefaultGameFileTests(unittest.TestCase):
    """Which .vpx is 'the' table. Every caller has to agree, or metadata describes
    one file while another launches."""

    def test_the_recorded_file_wins(self) -> None:
        names = ["Alt Build.vpx", "The Table (Bally 1990).vpx"]

        chosen = default_game_file(names, "The Table (Bally 1990)", "Alt Build.vpx")

        self.assertEqual(chosen, "Alt Build.vpx",
                         "the metadata and media were built against this one")

    def test_a_recorded_file_that_is_absent_is_ignored(self) -> None:
        names = ["Alt Build.vpx", "The Table (Bally 1990).vpx"]

        chosen = default_game_file(names, "The Table (Bally 1990)", "gone.vpx")

        self.assertEqual(chosen, "The Table (Bally 1990).vpx", "falls to the folder name")

    def test_the_folder_name_breaks_the_tie(self) -> None:
        names = ["aaa mod.vpx", "The Table (Bally 1990).vpx"]

        chosen = default_game_file(names, "The Table (Bally 1990)")

        self.assertEqual(chosen, "The Table (Bally 1990).vpx",
                         "not 'aaa mod.vpx', which sorts first")

    def test_folder_name_match_is_case_insensitive(self) -> None:
        chosen = default_game_file(["zzz.vpx", "THE TABLE.vpx"], "The Table")

        self.assertEqual(chosen, "THE TABLE.vpx")

    def test_otherwise_the_first_by_name_wins(self) -> None:
        names = ["b build.vpx", "a build.vpx"]

        chosen = default_game_file(names, "Some Folder")

        self.assertEqual(chosen, "a build.vpx", "deterministic, not directory order")

    def test_a_folder_with_no_game_files_resolves_to_nothing(self) -> None:
        self.assertEqual(default_game_file(["readme.txt"], "Some Folder"), "")

    def test_the_answer_never_depends_on_listing_order(self) -> None:
        names = ["c.vpx", "a.vpx", "Folder.vpx", "b.vpx"]

        first = default_game_file(names, "Folder")
        shuffled = default_game_file(list(reversed(names)), "Folder")

        self.assertEqual(first, shuffled)


if __name__ == "__main__":
    unittest.main()
