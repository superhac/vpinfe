from pathlib import Path
import sys
import types
import unittest

if "platformdirs" not in sys.modules:
    platformdirs = types.ModuleType("platformdirs")
    platformdirs.user_config_dir = lambda *args, **kwargs: "/tmp"
    sys.modules["platformdirs"] = platformdirs

if "requests" not in sys.modules:
    requests = types.ModuleType("requests")
    sys.modules["requests"] = requests

from common.app_updater import _build_posix_update_script


class TestAppUpdaterScripts(unittest.TestCase):
    def test_build_posix_update_script_keeps_shell_env_expansion_literals(self) -> None:
        prepared = {
            "zip_path": "/tmp/vpinfe.zip",
            "stage_dir": "/tmp/stage",
            "install_root": "/tmp/install",
            "launch_target": "/tmp/install/vpinfe",
            "last_update_log": "/tmp/last_update.log",
        }

        script = _build_posix_update_script(prepared, current_pid=1234, log_path=Path("/tmp/apply_update.log"))

        self.assertIn("DISPLAY=${DISPLAY:-<unset>}", script)
        self.assertIn("WAYLAND_DISPLAY=${WAYLAND_DISPLAY:-<unset>}", script)
        self.assertIn("XDG_RUNTIME_DIR=${XDG_RUNTIME_DIR:-<unset>}", script)


if __name__ == "__main__":
    unittest.main()
