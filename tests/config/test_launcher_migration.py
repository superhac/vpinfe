"""The configuration an install already had, read out as launchers.

The case that matters is a 2.x cabinet with plugin profiles: it should come up with the
launcher it was running plus one per profile, each carrying the environment and overrides
it already had rather than a bare copy of Visual Pinball.
"""

import configparser
import os
import unittest
from tempfile import TemporaryDirectory
from unittest.mock import patch

from common.games import launcher_migration, launchers


def _config(**values) -> configparser.ConfigParser:
    parser = configparser.ConfigParser()
    parser.add_section("Settings")
    for key, value in {"vpxbinpath": "/usr/bin/VPinballX_GL",
                       "vpxlaunchenv": "SDL_VIDEODRIVER=wayland",
                       **values}.items():
        parser.set("Settings", key, str(value))
    return parser


class SeedTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = launchers.LauncherStore(
            os.path.join(self.tmp.name, "launchers.json"))
        self.profiles = os.path.join(self.tmp.name, "plugin_profiles")

    def _seed(self, config=None) -> bool:
        from pathlib import Path
        with patch.object(launcher_migration, "PLUGIN_PROFILES_DIR",
                          Path(self.profiles)):
            return launcher_migration.seed(self.store, config or _config())

    def _profile(self, name: str) -> None:
        os.makedirs(self.profiles, exist_ok=True)
        with open(os.path.join(self.profiles, name), "w", encoding="utf-8") as handle:
            handle.write("[Plugin.DMD]\n")

    def test_an_install_gets_the_launcher_it_was_already_running(self) -> None:
        self._seed()

        held = self.store.launchers()
        self.assertEqual(len(held), 1)
        self.assertEqual(held[0].value("bin_path"), "/usr/bin/VPinballX_GL")
        self.assertEqual(held[0].value("launch_env"), "SDL_VIDEODRIVER=wayland")
        self.assertEqual(held[0].display_name, launcher_migration.SHIPPED_NAME)

    def test_a_2x_file_still_seeds_its_launcher(self) -> None:
        """The seven keys left the schema, so nothing resolves their old spellings any
        more. This pass has to know them itself, or an upgrading cabinet comes up with a
        launcher that has no program and no way to say what happened."""
        parser = configparser.ConfigParser()
        parser.add_section("Settings")
        parser.set("Settings", "vpxbinpath", "/opt/vpinball/VPinballX_GL")
        parser.set("Settings", "vpxinipath", "/home/cab/VPinballX.ini")
        parser.set("Settings", "vpxlogdeleteonstart", "true")
        parser.set("Settings", "globaltableinioverridemask", "windows")

        self._seed(parser)

        one = self.store.launchers()[0]
        self.assertEqual(one.value("bin_path"), "/opt/vpinball/VPinballX_GL")
        self.assertEqual(one.value("ini_path"), "/home/cab/VPinballX.ini")
        self.assertIs(one.value("log_delete_on_start"), True)
        self.assertEqual(one.value("table_ini_override_mask"), "windows")

    def test_a_3x_file_seeds_from_the_current_spellings(self) -> None:
        parser = configparser.ConfigParser()
        parser.add_section("general")
        parser.set("general", "vpx_bin_path", "/usr/bin/VPinballX_BGFX")
        parser.set("general", "global_ini_override", "/cfg/other.ini")

        self._seed(parser)

        one = self.store.launchers()[0]
        self.assertEqual(one.value("bin_path"), "/usr/bin/VPinballX_BGFX")
        self.assertEqual(one.value("ini_override"), "/cfg/other.ini")

    def test_an_install_with_nothing_configured_still_gets_one(self) -> None:
        """A launcher with no binary is something a person can fix from the Console. No
        launcher at all is a machine with nothing to point at."""
        self._seed(configparser.ConfigParser())

        self.assertEqual(len(self.store.launchers()), 1)

    def test_each_plugin_profile_becomes_a_launcher(self) -> None:
        self._profile("no-dmd.ini")
        self._profile("Loud.ini")

        self._seed()

        held = self.store.launchers()
        self.assertEqual([one.display_name for one in held],
                         [launcher_migration.SHIPPED_NAME, "Loud", "no-dmd"])

    def test_a_profile_keeps_what_the_install_was_already_set_to(self) -> None:
        """A profile was a copy of the ini, not a different Visual Pinball. Dropping the
        environment would leave it launching differently in ways nobody asked for."""
        self._profile("no-dmd.ini")

        self._seed()

        profile = self.store.launchers()[1]
        self.assertEqual(profile.value("bin_path"), "/usr/bin/VPinballX_GL")
        self.assertEqual(profile.value("launch_env"), "SDL_VIDEODRIVER=wayland")
        self.assertTrue(profile.value("ini_override").endswith("no-dmd.ini"))

    def test_only_the_profiles_are_claimed_as_ours_to_delete(self) -> None:
        """Removing a launcher offers to delete the ini it owns. The shipped one points
        at Visual Pinball's own file and must never be offered."""
        self._profile("no-dmd.ini")

        self._seed()

        shipped, profile = self.store.launchers()
        self.assertFalse(shipped.owns_ini)
        self.assertTrue(profile.owns_ini)

    def test_the_shipped_launcher_leads_so_it_is_the_default(self) -> None:
        self._profile("aaa-sorts-first.ini")

        self._seed()

        self.assertEqual(self.store.launchers()[0].display_name,
                         launcher_migration.SHIPPED_NAME)

    def test_a_file_that_is_not_an_ini_is_not_a_profile(self) -> None:
        self._profile("real.ini")
        os.makedirs(self.profiles, exist_ok=True)
        with open(os.path.join(self.profiles, "notes.txt"), "w",
                  encoding="utf-8") as handle:
            handle.write("hello")

        self._seed()

        self.assertEqual(len(self.store.launchers()), 2)

    def test_it_runs_once(self) -> None:
        """Somebody who deletes a launcher they did not want must not find it back on
        the next start."""
        self.assertTrue(self._seed())
        self.store.remove(self.store.launchers()[0].launcher_id)

        self.assertFalse(self._seed())
        self.assertEqual(self.store.launchers(), [])

    def test_launchers_added_later_are_left_alone(self) -> None:
        self._seed()
        self.store.put(launchers.Launcher(launcher_id="mine", app="vpx"))

        self._seed()

        self.assertEqual([one.launcher_id for one in self.store.launchers()][-1],
                         "mine")


class _Game:
    """Enough of a game for the assignment pass: its folder name and its metadata."""

    def __init__(self, name: str, vpinfe: dict, tables: dict | None = None):
        self.gameDirName = name
        self.meta_config = {"vpinfe": dict(vpinfe),
                            "tables": dict(tables or {"t-" + name: {"filename": "a.vpx"}})}


class AssignmentTests(unittest.TestCase):
    """A table's own override becomes a launcher and an assignment."""

    def setUp(self) -> None:
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = launchers.LauncherStore(
            os.path.join(self.tmp.name, "launchers.json"))
        self.store.save([launchers.Launcher(
            launcher_id="shipped", app="vpx",
            display_name=launcher_migration.SHIPPED_NAME,
            settings={"bin_path": "/usr/bin/vpx", "launch_env": "X=1"})], {})

    def _run(self, games):
        return launcher_migration.migrate_assignments(self.store, games)

    def test_a_table_with_nothing_set_is_left_alone(self) -> None:
        self._run([_Game("plain", {})])

        self.assertEqual(self.store.mappings(), {})
        self.assertEqual(len(self.store.launchers()), 1)

    def test_an_alt_launcher_becomes_a_launcher_and_an_assignment(self) -> None:
        self._run([_Game("vr", {"alt_launcher": "/opt/vpx-vr/VPinballX"})])

        held = self.store.launchers()
        self.assertEqual(len(held), 2)
        self.assertEqual(held[1].display_name, "VPinballX")
        self.assertEqual(self.store.mappings(), {"t-vr": held[1].launcher_id})

    def test_the_same_binary_twice_is_one_launcher(self) -> None:
        """Forty tables naming one alternative build is one launcher, not forty."""
        self._run([_Game("a", {"alt_launcher": "/opt/x/VPinballX"}),
                   _Game("b", {"alt_launcher": "/opt/x/VPinballX"})])

        self.assertEqual(len(self.store.launchers()), 2)
        self.assertEqual(len(set(self.store.mappings().values())), 1)

    def test_an_alt_launcher_keeps_the_rest_of_the_install_setup(self) -> None:
        """It only ever replaced the program. A bare launcher would drop the environment
        and the overrides the install was already launching with."""
        self._run([_Game("vr", {"alt_launcher": "/opt/x/VPinballX"})])

        made = self.store.launchers()[1]
        self.assertEqual(made.value("bin_path"), "/opt/x/VPinballX")
        self.assertEqual(made.value("launch_env"), "X=1")

    def test_a_plugin_profile_maps_to_the_launcher_seeding_made(self) -> None:
        self.store.put(launchers.Launcher(launcher_id="p1", app="vpx",
                                          display_name="no-dmd", owns_ini=True))

        self._run([_Game("quiet", {"plugin_profile": "no-dmd"})])

        self.assertEqual(self.store.mappings(), {"t-quiet": "p1"})
        self.assertEqual(len(self.store.launchers()), 2, "no second launcher for it")

    def test_a_profile_with_no_launcher_is_reported_and_left_on_the_default(self) -> None:
        """The ini was deleted, or never existed. Falling back is right; doing it
        silently is not."""
        with self.assertLogs("vpinfe.common.games.launcher_migration",
                             level="WARNING"):
            self._run([_Game("quiet", {"plugin_profile": "gone"})])

        self.assertEqual(self.store.mappings(), {})

    def test_every_table_in_the_game_is_assigned(self) -> None:
        """The override was written per game, and nothing records which of its tables it
        was for. Guessing one would be inventing a choice nobody made."""
        game = _Game("multi", {"alt_launcher": "/opt/x/VPinballX"},
                     tables={"t1": {"filename": "a.vpx"}, "t2": {"filename": "b.vpx"}})

        self._run([game])

        self.assertEqual(sorted(self.store.mappings()), ["t1", "t2"])

    def test_the_keys_are_taken_out_of_the_info(self) -> None:
        """Consumed rather than left inert: both are published to contract 1 themes, and
        a dead key in the theme API is a lie to third-party code. Contract 1 computes
        them from the resolver now."""
        game = _Game("vr", {"alt_launcher": "/opt/x/VPinballX",
                            "plugin_profile": "no-dmd"})
        written = []

        with patch("common.games.game_metadata.persist_game_meta",
                   side_effect=lambda g, c: written.append(c)):
            self._run([game])

        self.assertNotIn("alt_launcher", game.meta_config["vpinfe"])
        self.assertNotIn("plugin_profile", game.meta_config["vpinfe"])
        self.assertEqual(len(written), 1, "the file is rewritten without them")
        self.assertNotIn("alt_launcher", written[0]["vpinfe"])

    def test_a_game_that_had_none_is_not_rewritten(self) -> None:
        """Only the games that carried an override are written. A library-wide rewrite
        for nothing is a round trip per folder on a share."""
        written = []
        game = _Game("plain", {})

        with patch("common.games.game_metadata.persist_game_meta",
                   side_effect=lambda g, c: written.append(g)):
            self._run([game])

        self.assertEqual(written, [])

    def test_it_runs_once(self) -> None:
        self._run([_Game("vr", {"alt_launcher": "/opt/x/VPinballX"})])
        self.store.assign("t-vr", "")

        self._run([_Game("vr", {"alt_launcher": "/opt/x/VPinballX"})])

        self.assertEqual(self.store.mappings(), {})


if __name__ == "__main__":
    unittest.main()
