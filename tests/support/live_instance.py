"""A real VPinFE, started against a throwaway library, for tests that need a browser.

Not the servers assembled by hand: `main.py --headless` is what a user runs, and the
breaks this exists to catch have all been in the wiring between the pieces rather than in
a piece. Two of them were a hardcoded window list, which no unit test could see because
each unit was correct.

The instance gets its own config dir, its own ports and its own library, so it cannot
touch the developer's install or collide with one already running.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from tempfile import TemporaryDirectory

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
HARNESS_THEME = REPO_ROOT / "tests" / "fixtures" / "theme-harness"


class LiveInstance:
    """Start `main.py --headless`, wait for it to serve, and stop it afterwards."""

    def __init__(self, games_root: Path, theme: str = "Harness",
                 extra_settings: dict | None = None,
                 windows: tuple[str, ...] = ("playfield", "backglass", "scoreview")):
        self.games_root = Path(games_root)
        self.theme = theme
        self.windows = windows
        self.extra_settings = extra_settings or {}
        self._tmp = TemporaryDirectory(prefix="vpinfe-live-")
        self.config_dir = Path(self._tmp.name)
        self.proc: subprocess.Popen | None = None
        self.ports: dict[str, int] = {}

    # -- lifecycle ---------------------------------------------------------

    def __enter__(self) -> LiveInstance:
        self._write_config()
        self._install_harness_theme()
        self.proc = subprocess.Popen(
            [sys.executable, "main.py", "--headless"],
            cwd=str(REPO_ROOT),
            env={**os.environ, "VPINFE_CONFIG_DIR": str(self.config_dir)},
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        self._wait_until_serving()
        return self

    def __exit__(self, *_exc) -> None:
        if self.proc is not None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=20)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        self._tmp.cleanup()

    # -- setup -------------------------------------------------------------

    def _write_config(self) -> None:
        from common.config_access import cfg_set
        from common.config_store import ConfigStore

        # Ports of its own, so a running instance is not a reason this fails.
        from tests.support.browser_session import free_port
        self.ports = {"assets": free_port(), "manager": free_port(), "ws": free_port()}

        store = ConfigStore(str(self.config_dir / "vpinfe.ini"))
        cfg_set(store, "general", "game_root_dir", str(self.games_root))
        cfg_set(store, "general", "theme", self.theme)
        # A window with no screen assigned gets no API instance, which is right on a
        # desktop with one monitor and wrong for a test that wants to open all three.
        for index, window in enumerate(self.windows):
            cfg_set(store, f"windows.{window}", "screen_id", index)
        cfg_set(store, "network", "theme_assets_port", self.ports["assets"])
        cfg_set(store, "network", "manager_ui_port", self.ports["manager"])
        cfg_set(store, "network", "ws_port", self.ports["ws"])
        for (section, key), value in self.extra_settings.items():
            cfg_set(store, section, key, value)
        store.save()

    def _install_harness_theme(self) -> None:
        target = self.config_dir / "themes" / self.theme
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(HARNESS_THEME, target)

    def _wait_until_serving(self, timeout: float = 90.0) -> None:
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self.proc.poll() is not None:
                raise RuntimeError("VPinFE exited during startup:\n" + self.output())
            try:
                urllib.request.urlopen(self.url("/themes/"), timeout=1).read()
                return
            except urllib.error.HTTPError:
                return          # answering at all is what we are waiting for
            except Exception:
                time.sleep(0.25)
        raise TimeoutError("VPinFE never served its assets:\n" + self.output())

    # -- reading -----------------------------------------------------------

    def url(self, path: str = "/") -> str:
        return f"http://127.0.0.1:{self.ports['assets']}{path}"

    def theme_url(self, window: str = "playfield") -> str:
        return self.url(f"/themes/{self.theme}/index_{window}.html?window={window}"
                        f"&wsPort={self.ports['ws']}"
                        f"&themeAssetsPort={self.ports['assets']}")

    def api(self, path: str):
        with urllib.request.urlopen(
                f"http://127.0.0.1:{self.ports['manager']}{path}", timeout=10) as handle:
            return json.load(handle)

    def output(self) -> str:
        """Whatever the process has written. Only safe once it has been stopped."""
        if self.proc is None or self.proc.stdout is None:
            return ""
        if self.proc.poll() is None:
            return "(still running)"
        return self.proc.stdout.read() or ""
