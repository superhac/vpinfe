import importlib.util
import json
import logging
import os
import random
import re
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any

_LOCK = threading.Lock()
_HELPER = None
_CURRENT_EVENT = None
_RUNNER_NAMES = ('dof_runner.py', 'runner_dof.py', 'random_dof_runner.py')
_EVENT_TOKEN_RE = re.compile(r'^([A-Za-z])(\d+)$')
logger = logging.getLogger("vpinfe.common.dof_service")


def _is_enabled(iniconfig) -> bool:
    try:
        return iniconfig.config.getboolean('DOF', 'enabledof', fallback=False)
    except Exception:
        raw = str(
            iniconfig.config.get('DOF', 'enabledof', fallback='false')
        ).strip().lower()
        return raw in ('1', 'true', 'yes', 'on')


def _find_named_path(base: Path, names: tuple[str, ...]) -> Path | None:
    if base.is_file() and base.name in names:
        return base
    if not base.exists() or not base.is_dir():
        return None

    for name in names:
        direct = base / name
        if direct.exists():
            return direct

    for name in names:
        hits = sorted(base.rglob(name))
        if hits:
            return hits[0]
    return None


def _find_runner_path(base: Path) -> Path | None:
    return _find_named_path(base, _RUNNER_NAMES)


def _get_dof_base_candidates() -> list[Path]:
    env_override = os.environ.get('VPINFE_DOF_DIR', '').strip()
    candidates = []
    if env_override:
        candidates.append(Path(env_override).expanduser())

    project_root = Path(__file__).resolve().parents[1]
    candidates.append(project_root / 'third-party' / 'dof')

    meipass = getattr(sys, '_MEIPASS', None)
    if meipass:
        candidates.append(Path(meipass) / 'third-party' / 'dof')

    exe_dir = Path(sys.executable).resolve().parent
    candidates.append(exe_dir / 'third-party' / 'dof')
    candidates.append(exe_dir.parent / 'Resources' / 'third-party' / 'dof')

    return candidates


def _load_runner_class():
    candidates = _get_dof_base_candidates()
    runner_path = None
    for candidate in candidates:
        found = _find_runner_path(candidate)
        if found is not None:
            runner_path = found
            break

    if runner_path is None:
        logger.warning(
            "enabledof=true but runner not found. Checked: %s",
            ", ".join(str(c) for c in candidates),
        )
        return None, candidates[0]

    dof_dir = runner_path.parent

    module_name = f"_vpinfe_{runner_path.stem}"
    spec = importlib.util.spec_from_file_location(module_name, runner_path)
    if spec is None or spec.loader is None:
        logger.error("Failed to load module spec from: %s", runner_path)
        return None, dof_dir

    module = importlib.util.module_from_spec(spec)
    dof_dir_str = str(dof_dir)
    restore_path = False
    if dof_dir_str not in sys.path:
        sys.path.insert(0, dof_dir_str)
        restore_path = True
    try:
        spec.loader.exec_module(module)
    except Exception as e:
        logger.error("Failed importing dof_runner.py: %s", e)
        return None, dof_dir
    finally:
        if restore_path:
            try:
                sys.path.remove(dof_dir_str)
            except ValueError:
                pass

    runner_class = getattr(module, 'SingleEventDofRunner', None)
    if runner_class is None:
        logger.error("SingleEventDofRunner class not found in dof_runner.py")
        return None, dof_dir
    return runner_class, dof_dir


class _DofHelperProcess:
    def __init__(self) -> None:
        self._proc: subprocess.Popen[str] | None = None
        self._reader_thread: threading.Thread | None = None
        self._pending: dict[int, dict[str, Any]] = {}
        self._cv = threading.Condition()
        self._next_request_id = 1
        self._expected_shutdown = False
        self._unexpected_exit_code: int | None = None

    def _command(self) -> list[str]:
        if getattr(sys, 'frozen', False):
            return [sys.executable, '--dof-helper']
        return [sys.executable, '-m', 'common.dof_service_worker']

    def _ensure_started(self) -> bool:
        if self._proc is not None and self._proc.poll() is None:
            return True

        cmd = self._command()
        env = os.environ.copy()
        env['PYTHONUNBUFFERED'] = '1'
        project_root = str(Path(__file__).resolve().parents[1])
        try:
            self._expected_shutdown = False
            self._unexpected_exit_code = None
            self._proc = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                env=env,
                cwd=project_root,
            )
        except Exception as exc:
            logger.error("Failed to launch DOF helper: %s", exc)
            self._proc = None
            return False

        self._reader_thread = threading.Thread(
            target=self._reader_main,
            name="dof-helper-reader",
            daemon=True,
        )
        self._reader_thread.start()
        return True

    def _reader_main(self) -> None:
        proc = self._proc
        if proc is None or proc.stdout is None:
            return

        try:
            for raw_line in proc.stdout:
                line = raw_line.rstrip('\n')
                if not line:
                    continue
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError:
                    logger.error("[libdof helper] %s", line)
                    continue

                if payload.get("type") == "log":
                    self._handle_log(payload)
                    continue
                if payload.get("type") == "response":
                    with self._cv:
                        request_id = payload.get("id")
                        pending = self._pending.get(request_id)
                        if pending is not None:
                            pending["response"] = payload
                            self._cv.notify_all()
                    continue
                logger.debug("Unhandled DOF helper payload: %s", payload)
        finally:
            return_code = proc.poll()
            with self._cv:
                for pending in self._pending.values():
                    pending["response"] = {
                        "type": "response",
                        "ok": False,
                        "error": f"helper_exited:{return_code}",
                    }
                self._cv.notify_all()

            if not self._expected_shutdown:
                self._unexpected_exit_code = return_code
            if not self._expected_shutdown and return_code not in (None, 0):
                logger.error("DOF helper exited unexpectedly with code %s", return_code)
            elif not self._expected_shutdown:
                logger.warning("DOF helper exited unexpectedly with code %s", return_code)

    def _handle_log(self, payload: dict[str, Any]) -> None:
        level_name = str(payload.get("level", "INFO")).upper()
        message = str(payload.get("message", ""))
        if level_name == "DEBUG":
            logger.debug("[libdof] %s", message)
        elif level_name == "INFO":
            logger.info("[libdof] %s", message)
        elif level_name in {"WARN", "WARNING"}:
            logger.warning("[libdof] %s", message)
        elif level_name == "ERROR":
            logger.error("[libdof] %s", message)
        else:
            logger.info("[libdof] %s", message)

    def request(self, command: str, timeout: float = 10.0, **payload: Any) -> dict[str, Any] | None:
        if not self._ensure_started():
            return None

        proc = self._proc
        if proc is None or proc.stdin is None:
            return None

        with self._cv:
            request_id = self._next_request_id
            self._next_request_id += 1
            self._pending[request_id] = {}

        message = {"id": request_id, "command": command}
        message.update(payload)
        encoded = json.dumps(message) + "\n"

        try:
            proc.stdin.write(encoded)
            proc.stdin.flush()
        except Exception as exc:
            logger.error("Failed sending DOF helper command %s: %s", command, exc)
            with self._cv:
                self._pending.pop(request_id, None)
            return None

        with self._cv:
            state = self._pending[request_id]
            got_response = self._cv.wait_for(lambda: "response" in state, timeout=timeout)
            response = state.get("response")
            self._pending.pop(request_id, None)

        if not got_response or response is None:
            logger.error("Timed out waiting for DOF helper command: %s", command)
            return None
        return response

    def is_alive(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def consume_unexpected_exit_code(self) -> int | None:
        code = self._unexpected_exit_code
        self._unexpected_exit_code = None
        return code

    def close(self, timeout: float = 10.0) -> bool:
        proc = self._proc
        if proc is None:
            return True

        self._expected_shutdown = True
        self.request("shutdown", timeout=timeout, service_timeout=timeout)
        try:
            proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.terminate()
            try:
                proc.wait(timeout=2.0)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=2.0)

        self._proc = None
        return True


def is_running() -> bool:
    global _HELPER
    with _LOCK:
        if _HELPER is None:
            return False
        if _HELPER.is_alive():
            return True
        exit_code = _HELPER.consume_unexpected_exit_code()
        if exit_code is not None:
            logger.warning("Detected stopped DOF helper process; last exit code was %s", exit_code)
        _HELPER = None
        return False


def find_dof_file(*names: str) -> Path | None:
    candidates = _get_dof_base_candidates()
    valid_names = tuple(name for name in names if name)
    if not valid_names:
        return None

    for candidate in candidates:
        found = _find_named_path(candidate, valid_names)
        if found is not None:
            return found
    return None


def _get_helper() -> _DofHelperProcess:
    global _HELPER
    if _HELPER is None:
        _HELPER = _DofHelperProcess()
    return _HELPER


def start_dof_service_if_enabled(iniconfig) -> bool:
    global _HELPER, _CURRENT_EVENT
    if not _is_enabled(iniconfig):
        return False

    with _LOCK:
        restarting_after_crash = False
        if _HELPER is not None and not _HELPER.is_alive():
            exit_code = _HELPER.consume_unexpected_exit_code()
            if exit_code is not None:
                restarting_after_crash = True
                logger.warning(
                    "Restarting DOF helper after unexpected exit (code %s)",
                    exit_code,
                )
            _HELPER = None
        helper = _get_helper()
        response = helper.request("start", timeout=10.0)

    if response is None:
        return False
    if not response.get("ok", False):
        logger.error("Failed to start DOF helper: %s", response.get("error", "unknown"))
        return False

    started = bool(response.get("started"))
    if started:
        _CURRENT_EVENT = None
        logger.info("Service started using dof_runner.py from %s", response.get("detail"))
        if restarting_after_crash:
            logger.info("DOF helper recovered and is running again.")
    else:
        logger.info("Service start requested but runner was already active.")
    return started


def stop_dof_service(timeout: float = 10.0) -> bool:
    global _HELPER, _CURRENT_EVENT
    with _LOCK:
        helper = _HELPER
        if helper is None:
            return True
        _HELPER = None

    logger.info("Stopping service...")
    stopped = helper.close(timeout=timeout)
    _CURRENT_EVENT = None
    return stopped


def restart_dof_service_if_enabled(iniconfig) -> bool:
    stop_dof_service()
    return start_dof_service_if_enabled(iniconfig)


def _normalize_event_token(event_token: str | None) -> str | None:
    token = str(event_token or '').strip().upper()
    if not token:
        return None

    match = _EVENT_TOKEN_RE.fullmatch(token)
    if not match:
        raise ValueError(f"Invalid DOF event token: {event_token!r}")

    type_char, number_text = match.groups()
    return f"{type_char}{int(number_text)}"


def _resolve_frontend_event_token(event_token: str | None) -> str:
    normalized = _normalize_event_token(event_token)
    if normalized:
        return normalized
    return f"E{random.randint(900, 990)}"


def send_dof_event_token(iniconfig, event_token: str) -> bool:
    global _CURRENT_EVENT
    if not _is_enabled(iniconfig):
        return False

    resolved_event = _normalize_event_token(event_token)
    if not resolved_event:
        raise ValueError("DOF event token is required.")

    with _LOCK:
        current_event = _CURRENT_EVENT

    if current_event == resolved_event:
        return False

    if not is_running():
        started = start_dof_service_if_enabled(iniconfig)
        if not started and not is_running():
            return False

    with _LOCK:
        helper = _get_helper()
        response = helper.request(
            "send_event_token",
            timeout=5.0,
            event_token=resolved_event,
        )

    if response is None or not response.get("ok", False):
        logger.error(
            "Failed to send frontend DOF event %s: %s",
            resolved_event,
            None if response is None else response.get("error", "unknown"),
        )
        return False

    _CURRENT_EVENT = resolved_event
    logger.debug("Sent frontend DOF event: %s", resolved_event)
    return True


def clear_active_dof_event(iniconfig) -> bool:
    global _CURRENT_EVENT
    if not _is_enabled(iniconfig):
        return False

    if not is_running():
        return False

    with _LOCK:
        helper = _get_helper()
        response = helper.request("clear_event", timeout=5.0)

    if response is None or not response.get("ok", False):
        logger.error(
            "Failed to clear active DOF event: %s",
            None if response is None else response.get("error", "unknown"),
        )
        return False

    _CURRENT_EVENT = None
    logger.debug("Cleared active frontend DOF event")
    return bool(response.get("cleared", False))


def send_frontend_dof_event(iniconfig, event_token: str | None = None) -> bool:
    resolved_event = _resolve_frontend_event_token(event_token)
    return send_dof_event_token(iniconfig, resolved_event)
