"""Launchers: the store, and the one function that says which one plays a table.

The resolution order is the part worth pinning. It is what the grid's column and the
launch path both read, and them disagreeing is the bug the override mask has today -
what will actually happen at launch is not visible anywhere before it happens.
"""

import json
import os
import unittest
from tempfile import TemporaryDirectory

from apps.vpx import FIELDS as VPX_FIELDS
from common.games import launchers


def _launcher(launcher_id: str, **kwargs) -> launchers.Launcher:
    return launchers.Launcher(launcher_id=launcher_id,
                              app=kwargs.pop("app", "vpx"),
                              display_name=kwargs.pop("display_name", launcher_id),
                              **kwargs)


class StoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = launchers.LauncherStore(
            os.path.join(self.tmp.name, "launchers.json"))

    def test_a_first_run_has_none_and_that_is_not_an_error(self) -> None:
        self.assertEqual(self.store.launchers(), [])
        self.assertEqual(self.store.mappings(), {})

    def test_a_launcher_survives_being_written_and_read(self) -> None:
        one = _launcher("a", settings={"bin_path": "/usr/bin/vpx"}, owns_ini=True)

        self.store.put(one)

        self.assertEqual(self.store.get("a"), one)

    def test_putting_the_same_id_replaces_in_place(self) -> None:
        """Order is what says which launcher is the default, so a replacement that moved
        to the end would silently change which one plays every unassigned table."""
        self.store.put(_launcher("a"))
        self.store.put(_launcher("b"))

        self.store.put(_launcher("a", display_name="renamed"))

        self.assertEqual([one.launcher_id for one in self.store.launchers()],
                         ["a", "b"])
        self.assertEqual(self.store.get("a").display_name, "renamed")

    def test_removing_takes_its_mappings_with_it(self) -> None:
        """A table pointing at a launcher that was deleted is not a state anybody chose,
        so it goes back to the default rather than being left dangling."""
        self.store.put(_launcher("a"))
        self.store.put(_launcher("b"))
        self.store.assign("table-1", "a")
        self.store.assign("table-2", "b")

        self.assertTrue(self.store.remove("a"))

        self.assertEqual(self.store.mappings(), {"table-2": "b"})

    def test_removing_something_that_is_not_there_says_so(self) -> None:
        self.assertFalse(self.store.remove("nope"))

    def test_clearing_an_assignment_drops_the_row(self) -> None:
        """An absent mapping already means "the default", so a blank one would be a
        second spelling of one state."""
        self.store.put(_launcher("a"))
        self.store.assign("table-1", "a")

        self.store.assign("table-1", "")

        self.assertEqual(self.store.mappings(), {})

    def test_a_mapping_to_a_launcher_that_is_gone_is_dropped_on_read(self) -> None:
        """Hand-edited, or left by a build that wrote them apart. A table reporting an
        override it does not have is worse than one reporting none."""
        with open(self.store.path, "w", encoding="utf-8") as handle:
            json.dump({"schema": 1,
                       "launchers": [{"launcher_id": "a", "app": "vpx"}],
                       "mappings": {"table-1": "a", "table-2": "ghost"}}, handle)

        self.assertEqual(self.store.mappings(), {"table-1": "a"})

    def test_an_unreadable_file_is_an_empty_store(self) -> None:
        with open(self.store.path, "w", encoding="utf-8") as handle:
            handle.write("{not json")

        with self.assertLogs("vpinfe.common.games.launchers", level="ERROR"):
            self.assertEqual(self.store.launchers(), [])

    def test_a_field_a_newer_build_wrote_is_carried_through(self) -> None:
        """A downgrade must not silently strip what it does not understand."""
        with open(self.store.path, "w", encoding="utf-8") as handle:
            json.dump({"schema": 1, "launchers": [
                {"launcher_id": "a", "app": "vpx", "future": "kept"}]}, handle)

        self.store.put(_launcher("b"))

        with open(self.store.path, encoding="utf-8") as handle:
            written = json.load(handle)
        self.assertEqual(written["launchers"][0]["future"], "kept")


class ValueTests(unittest.TestCase):
    def test_a_field_it_does_not_carry_answers_the_app_default(self) -> None:
        """A launcher missing a field is running on the default, so blank says the
        opposite of what is true."""
        one = _launcher("a")

        self.assertEqual(one.value("log_delete_on_start"), "false")

    def test_a_field_it_carries_answers_itself(self) -> None:
        one = _launcher("a", settings={"log_delete_on_start": True})

        self.assertIs(one.value("log_delete_on_start"), True)

    def test_an_app_nobody_declares_offers_nothing_of_its_own(self) -> None:
        """A launcher whose app this build does not know is still a launcher: it is
        listed, and the only fields it has are the ones every launcher has."""
        one = _launcher("a", app="future-pinball")

        self.assertEqual(one.fields(), launchers.OWN_FIELDS)
        self.assertEqual(one.value("bin_path"), "")


class ResolutionTests(unittest.TestCase):
    """Explicit assignment, then is it enabled, then the default for the app."""

    def setUp(self) -> None:
        self.default = _launcher("d", display_name="Visual Pinball X")
        self.other = _launcher("o", display_name="VPX (4K)")
        self.held = [self.default, self.other]

    def _for(self, table_id: str, mappings=None, held=None):
        return launchers.launcher_for_table("Table.vpx", table_id,
                                            self.held if held is None else held,
                                            mappings or {})

    def test_a_table_that_names_nothing_gets_the_default(self) -> None:
        self.assertEqual(self._for("t1"), self.default)

    def test_a_table_that_names_one_gets_it(self) -> None:
        self.assertEqual(self._for("t1", {"t1": "o"}), self.other)

    def test_a_table_naming_a_disabled_launcher_falls_back(self) -> None:
        """Falling back rather than refusing to launch. The caller says so - the
        fallback is honest and silence about it is what makes it a mystery."""
        held = [self.default, _launcher("o", enabled=False)]

        self.assertEqual(self._for("t1", {"t1": "o"}, held), self.default)

    def test_the_default_is_the_first_enabled_one(self) -> None:
        held = [_launcher("off", enabled=False), self.other]

        self.assertEqual(self._for("t1", {}, held), self.other)

    def test_a_file_no_app_claims_has_no_launcher(self) -> None:
        """Not a table, so there is nothing to answer. A launcher here would be a
        promise to run something we cannot."""
        self.assertIsNone(launchers.launcher_for_table("notes.txt", "t1",
                                                       self.held, {}))

    def test_a_library_with_no_launchers_resolves_to_nothing(self) -> None:
        self.assertIsNone(self._for("t1", {}, []))

    def test_the_default_for_another_app_is_not_borrowed(self) -> None:
        """An app's launcher runs that app's files. A Future Pinball launcher standing
        in for a .vpx would launch the wrong program with a straight face."""
        held = [_launcher("fp", app="future-pinball")]

        self.assertIsNone(self._for("t1", {}, held))


class SeedTests(unittest.TestCase):
    """The launcher an install already had, from the values read out of its old config."""

    VALUES = {
        "bin_path": "/usr/bin/VPinballX_GL",
        "ini_path": "/home/cab/.vpinball/VPinballX.ini",
        "launch_env": "SDL_VIDEODRIVER=wayland",
        "log_delete_on_start": True,
        "ini_override": "",
        "table_ini_override_enabled": True,
        "table_ini_override_mask": "{table}.ini",
    }

    def test_the_values_arrive_as_one_launcher(self) -> None:
        one = launchers.seeded_from(self.VALUES)

        self.assertEqual(one.app, "vpx")
        self.assertEqual(one.value("bin_path"), "/usr/bin/VPinballX_GL")
        self.assertEqual(one.value("table_ini_override_mask"), "{table}.ini")
        self.assertIs(one.value("log_delete_on_start"), True)

    def test_it_does_not_claim_to_own_visual_pinballs_own_ini(self) -> None:
        """Removing a launcher offers to delete the file it owns, and this one points at
        the ini Visual Pinball wrote. Claiming it would delete a person's real setup."""
        self.assertFalse(launchers.seeded_from(self.VALUES).owns_ini)

    def test_it_carries_exactly_what_the_app_declares(self) -> None:
        """A field left unseeded reads as its default, which for a path means the install
        quietly stopped using what it was configured with."""
        one = launchers.seeded_from(self.VALUES)

        self.assertEqual(sorted(one.settings), sorted(f.key for f in VPX_FIELDS))


if __name__ == "__main__":
    unittest.main()
