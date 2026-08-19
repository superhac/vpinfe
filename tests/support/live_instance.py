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
import urllib.parse
import urllib.request
from contextlib import suppress
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
        # The hub's asset port, which the real launcher reads out of its discovery
        # document. A test that stands up a hub sets it from that instance.
        self.hub_assets_port = 0
        self._tmp = TemporaryDirectory(prefix="vpinfe-live-")
        self.config_dir = Path(self._tmp.name)
        self.proc: subprocess.Popen | None = None
        self.ports: dict[str, int] = {}

    # -- lifecycle ---------------------------------------------------------

    def __enter__(self) -> LiveInstance:
        self._write_config()
        self._install_harness_theme()
        # To a file, not a pipe. Nothing drains a pipe until the process is stopped, so
        # a chatty startup fills the buffer and the child blocks on its own logging -
        # which looks exactly like an instance that never finished booting.
        self._log_path = self.config_dir / "instance.log"
        self._log = open(self._log_path, "w", encoding="utf-8")
        self.proc = subprocess.Popen(
            # -u because the child buffers its own stdout when it is not a tty, so
            # nothing reaches the file until it exits. `output()` flushes this end of the
            # pipe, which does nothing about the far end - every failure of a still-running
            # instance reported an empty log, which is why they were hard to diagnose.
            [sys.executable, "-u", "main.py", "--headless"],
            cwd=str(REPO_ROOT),
            env={**os.environ, "VPINFE_CONFIG_DIR": str(self.config_dir),
                 "PYTHONUNBUFFERED": "1"},
            stdout=self._log, stderr=subprocess.STDOUT, text=True)
        self._wait_until_serving()
        return self

    def __exit__(self, *_exc) -> None:
        if self.proc is not None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=30)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait(timeout=30)
        if getattr(self, "_log", None) is not None:
            self._log.close()
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
        cfg_set(store, "network", "hub_port", self.ports["manager"])
        cfg_set(store, "network", "ws_port", self.ports["ws"])
        for (section, key), value in self.extra_settings.items():
            cfg_set(store, section, key, value)
        store.save()

    def _install_harness_theme(self) -> None:
        target = self.config_dir / "themes" / self.theme
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(HARNESS_THEME, target)

    def _wait_until_serving(self, timeout: float = 180.0) -> None:
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
        query = (f"/themes/{self.theme}/index_{window}.html?window={window}"
                 f"&wsPort={self.ports['ws']}"
                 f"&themeAssetsPort={self.ports['assets']}")
        # What the launcher appends for a device, and the reason it has to be here too:
        # without it the page dials this machine for the library's art, which a device
        # does not have. See `_build_window_url`, which is what does this for real.
        hub_url = str(self.extra_settings.get(("network", "hub_url"), "") or "")
        if hub_url:
            parsed = urllib.parse.urlparse(hub_url)
            query += (f"&hubHost={urllib.parse.quote(parsed.hostname or '', safe='')}"
                      f"&hubPort={parsed.port or self.ports['manager']}"
                      f"&devicePort={self.ports['manager']}"
                      f"&hubAssetsPort={self.hub_assets_port or self.ports['assets']}")
        return self.url(query)

    def api(self, path: str):
        with urllib.request.urlopen(
                f"http://127.0.0.1:{self.ports['manager']}{path}", timeout=10) as handle:
            return json.load(handle)

    def wait_for_api(self, timeout: float = 120.0) -> None:
        """Block until the hub answers. Separate from `_wait_until_serving`, which waits
        on the asset server: the two come up independently, and the api is the slower."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self.proc.poll() is not None:
                raise RuntimeError("VPinFE exited before its api served:\n" + self.output())
            try:
                self.api("/api/v1/library/entries")
                return
            except urllib.error.HTTPError:
                return          # answering at all is what we are waiting for
            except Exception:
                time.sleep(0.25)
        raise TimeoutError("VPinFE never served its api:\n" + self.output())

    def output(self, tail: int = 4000) -> str:
        """Whatever the instance has logged so far. Readable while it is still running,
        which is the moment a test needs it."""
        path = getattr(self, "_log_path", None)
        if path is None or not path.exists():
            return ""
        with suppress(Exception):
            if self._log is not None:
                self._log.flush()
        return path.read_text(encoding="utf-8", errors="replace")[-tail:]
