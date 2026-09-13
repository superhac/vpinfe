"""The DOF helper stops its runner on every way out, not just a clean shutdown."""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from common.paths import APP_ROOT

STUB_RUNNER = '''
import os


class SingleEventDofRunner:
    def __init__(self, rom, **kwargs):
        self._running = False

    def start(self):
        self._running = True
        return True

    def is_running(self):
        return self._running

    def send_event_token(self, event_token, **kwargs):
        pass

    def stop_event(self):
        pass

    def stop(self, timeout=10.0):
        self._running = False
        with open(os.environ["VPINFE_TEST_DOF_MARKER"], "w", encoding="utf-8") as marker:
            marker.write("stopped")
        return True
'''


@unittest.skipIf(sys.platform == "win32", "SIGTERM does not run handlers on Windows")
class DofHelperShutdownTests(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        root = Path(self._tmp.name)
        (root / "dof_runner.py").write_text(STUB_RUNNER, encoding="utf-8")
        self.marker = root / "stopped.marker"

        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"
        env["PYTHONPATH"] = str(APP_ROOT)
        env["VPINFE_DOF_DIR"] = str(root)
        env["VPINFE_CONFIG_DIR"] = str(root / "config")
        env["VPINFE_TEST_DOF_MARKER"] = str(self.marker)

        self.proc = subprocess.Popen(
            [sys.executable, "-m", "common.host.dof_service_worker"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            env=env,
            cwd=str(APP_ROOT),
        )
        self.addCleanup(self._kill_helper)

    def _kill_helper(self):
        if self.proc.poll() is None:
            self.proc.kill()
            self.proc.wait(timeout=5)
        for pipe in (self.proc.stdin, self.proc.stdout):
            if pipe is not None and not pipe.closed:
                pipe.close()

    def _request(self, request_id, command, **payload):
        message = {"id": request_id, "command": command}
        message.update(payload)
        self.proc.stdin.write(json.dumps(message) + "\n")
        self.proc.stdin.flush()

        deadline = time.monotonic() + 15.0
        while time.monotonic() < deadline:
            line = self.proc.stdout.readline()
            if not line:
                self.fail(f"helper exited before answering {command}")
            response = json.loads(line)
            if response.get("type") == "response" and response.get("id") == request_id:
                return response
        self.fail(f"timed out waiting for {command}")

    def _start_with_active_event(self):
        started = self._request(1, "start")
        self.assertTrue(started.get("ok"), started)
        self.assertTrue(started.get("started"), started)
        sent = self._request(2, "send_event_token", event_token="E905")
        self.assertTrue(sent.get("ok"), sent)

    def _assert_runner_stopped(self):
        deadline = time.monotonic() + 10.0
        while time.monotonic() < deadline:
            if self.marker.exists():
                return
            time.sleep(0.05)
        self.fail("helper exited without stopping the runner; DOF outputs stay on")

    def test_sigterm_stops_the_runner(self):
        self._start_with_active_event()

        os.kill(self.proc.pid, signal.SIGTERM)
        self.proc.wait(timeout=10)

        self._assert_runner_stopped()

    def test_sigint_stops_the_runner(self):
        self._start_with_active_event()

        os.kill(self.proc.pid, signal.SIGINT)
        self.proc.wait(timeout=10)

        self._assert_runner_stopped()

    def test_losing_the_parent_stops_the_runner(self):
        self._start_with_active_event()

        self.proc.stdin.close()
        self.proc.wait(timeout=10)

        self._assert_runner_stopped()


if __name__ == "__main__":
    unittest.main()
