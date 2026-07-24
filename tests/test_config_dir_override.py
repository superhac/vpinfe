import importlib
import os
import unittest
from pathlib import Path

import common.paths
from common.config_bootstrap import apply_configdir_override

ENV_VAR = "VPINFE_CONFIG_DIR"


class TestConfigDirEnvOverride(unittest.TestCase):
    """common.paths.CONFIG_DIR honors VPINFE_CONFIG_DIR at import time."""

    def setUp(self) -> None:
        self._saved = os.environ.get(ENV_VAR)

    def tearDown(self) -> None:
        if self._saved is None:
            os.environ.pop(ENV_VAR, None)
        else:
            os.environ[ENV_VAR] = self._saved
        # Leave the module resolved against the real environment for other tests.
        importlib.reload(common.paths)

    def _reload(self):
        return importlib.reload(common.paths)

    def test_override_relocates_config_dir_and_derived_paths(self) -> None:
        os.environ[ENV_VAR] = "/tmp/vpinfe-override"
        paths = self._reload()

        self.assertEqual(paths.CONFIG_DIR, Path("/tmp/vpinfe-override"))
        self.assertEqual(paths.VPINFE_INI_PATH, Path("/tmp/vpinfe-override/vpinfe.ini"))
        self.assertEqual(paths.THEMES_DIR, Path("/tmp/vpinfe-override/themes"))
        self.assertEqual(paths.COLLECTIONS_PATH, Path("/tmp/vpinfe-override/collections.ini"))

    def test_override_expands_user_home(self) -> None:
        os.environ[ENV_VAR] = "~/vpinfe-home"
        paths = self._reload()

        self.assertEqual(paths.CONFIG_DIR, Path.home() / "vpinfe-home")

    def test_blank_override_falls_back_to_platformdirs(self) -> None:
        os.environ.pop(ENV_VAR, None)
        default = self._reload().CONFIG_DIR

        os.environ[ENV_VAR] = "   "
        self.assertEqual(self._reload().CONFIG_DIR, default)


class TestApplyConfigdirOverride(unittest.TestCase):
    """The CLI flag maps onto the env var before common.paths is imported."""

    def test_sets_env_from_space_separated_flag(self) -> None:
        env: dict[str, str] = {}
        applied = apply_configdir_override(["--configdir", "/tmp/cfg"], env)

        self.assertEqual(applied, "/tmp/cfg")
        self.assertEqual(env[ENV_VAR], "/tmp/cfg")

    def test_sets_env_from_equals_form(self) -> None:
        env: dict[str, str] = {}
        apply_configdir_override(["--configdir=/tmp/cfg"], env)

        self.assertEqual(env[ENV_VAR], "/tmp/cfg")

    def test_existing_env_wins_over_flag(self) -> None:
        env = {ENV_VAR: "/already/set"}
        applied = apply_configdir_override(["--configdir", "/tmp/cfg"], env)

        self.assertIsNone(applied)
        self.assertEqual(env[ENV_VAR], "/already/set")

    def test_last_flag_wins(self) -> None:
        env: dict[str, str] = {}
        apply_configdir_override(["--configdir", "/first", "--configdir=/second"], env)

        self.assertEqual(env[ENV_VAR], "/second")

    def test_no_flag_leaves_env_untouched(self) -> None:
        env: dict[str, str] = {}
        applied = apply_configdir_override(["--headless", "--buildmeta"], env)

        self.assertIsNone(applied)
        self.assertNotIn(ENV_VAR, env)

    def test_blank_flag_value_is_ignored(self) -> None:
        env: dict[str, str] = {}
        applied = apply_configdir_override(["--configdir", "   "], env)

        self.assertIsNone(applied)
        self.assertNotIn(ENV_VAR, env)

    def test_trailing_flag_without_value_is_ignored(self) -> None:
        env: dict[str, str] = {}
        applied = apply_configdir_override(["--headless", "--configdir"], env)

        self.assertIsNone(applied)
        self.assertNotIn(ENV_VAR, env)


if __name__ == "__main__":
    unittest.main()
