from __future__ import annotations

import json
import logging
import sys
from typing import Any

from common import dof_service as dof_parent


logger = logging.getLogger("vpinfe.common.dof_service_worker")


class _Worker:
    def __init__(self) -> None:
        self._runner = None
        self._current_event: str | None = None

    def _emit(self, payload: dict[str, Any]) -> None:
        sys.stdout.write(json.dumps(payload) + "\n")
        sys.stdout.flush()

    def _reply(self, request_id: int | None, ok: bool, **extra: Any) -> None:
        payload = {"type": "response", "ok": ok}
        if request_id is not None:
            payload["id"] = request_id
        payload.update(extra)
        self._emit(payload)

    def _log_callback(self, level: Any, message: str) -> None:
        self._emit(
            {
                "type": "log",
                "level": getattr(level, "name", str(level)).upper(),
                "message": message or "",
            }
        )

    def _start(self) -> tuple[bool, str]:
        if self._runner is not None:
            try:
                if self._runner.is_running():
                    return False, "already_running"
            except Exception:
                self._runner = None

        runner_class, dof_dir = dof_parent._load_runner_class()
        if runner_class is None:
            return False, "runner_unavailable"

        self._runner = runner_class(
            rom="pinupmenu",
            debug=logger.isEnabledFor(logging.DEBUG),
            log_callback=self._log_callback,
        )
        started = bool(self._runner.start())
        if started:
            self._current_event = None
            return True, str(dof_dir)
        return False, "already_running"

    def _stop(self, timeout: float = 10.0) -> bool:
        runner = self._runner
        if runner is None:
            self._current_event = None
            return True

        try:
            stopped = bool(runner.stop(timeout=timeout))
        finally:
            self._runner = None
            self._current_event = None
        return stopped

    def _send_event_token(self, event_token: str) -> bool:
        if self._runner is None or not self._runner.is_running():
            raise RuntimeError("runner_not_running")
        self._runner.send_event_token(event_token)
        self._current_event = event_token
        return True

    def _clear_event(self) -> bool:
        if self._runner is None or not self._runner.is_running():
            return False
        self._runner.stop_event()
        self._current_event = None
        return True

    def handle(self, request: dict[str, Any]) -> bool:
        request_id = request.get("id")
        command = request.get("command")

        try:
            if command == "start":
                started, detail = self._start()
                self._reply(request_id, True, started=started, detail=detail)
                return True
            if command == "stop":
                stopped = self._stop(float(request.get("service_timeout", 10.0)))
                self._reply(request_id, True, stopped=stopped)
                return True
            if command == "send_event_token":
                sent = self._send_event_token(str(request.get("event_token", "")))
                self._reply(request_id, True, sent=sent)
                return True
            if command == "clear_event":
                cleared = self._clear_event()
                self._reply(request_id, True, cleared=cleared)
                return True
            if command == "shutdown":
                self._stop(float(request.get("service_timeout", 10.0)))
                self._reply(request_id, True, shutdown=True)
                return False
            self._reply(request_id, False, error=f"unknown_command:{command}")
            return True
        except Exception as exc:
            self._reply(request_id, False, error=str(exc))
            return True


def main() -> int:
    worker = _Worker()

    for raw_line in sys.stdin:
        line = raw_line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as exc:
            worker._reply(None, False, error=f"invalid_json:{exc}")
            continue
        if not worker.handle(payload):
            return 0

    worker._stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
