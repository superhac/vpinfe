from pathlib import Path
import unittest

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

    def test_build_posix_update_script_repairs_linux_chromium_permissions(self) -> None:
        prepared = {
            "zip_path": "/tmp/vpinfe.zip",
            "stage_dir": "/tmp/stage",
            "install_root": "/tmp/install",
            "launch_target": "/tmp/install/vpinfe",
            "last_update_log": "/tmp/last_update.log",
        }

        script = _build_posix_update_script(prepared, current_pid=1234, log_path=Path("/tmp/apply_update.log"))

        self.assertIn('CHROMIUM_ROOT="$INSTALL_ROOT/_internal/chromium/linux/chrome"', script)
        self.assertIn('find "$CHROMIUM_ROOT" -type d -exec chmod a+rx {} +', script)
        self.assertIn("chrome_crashpad_handler chrome-sandbox", script)


if __name__ == "__main__":
    unittest.main()
