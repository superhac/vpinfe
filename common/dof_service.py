import importlib.util
import logging
import os
import sys
import threading
from pathlib import Path

_LOCK = threading.Lock()
_RUNNER = None
_RUNNER_NAMES = ('dof_runner.py', 'random_dof_runner.py')
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


def is_running() -> bool:
    global _RUNNER
    with _LOCK:
        if _RUNNER is None:
            return False
        try:
            return bool(_RUNNER.is_running())
        except Exception:
            _RUNNER = None
            return False


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

    runner_class = getattr(module, 'RandomDofRunner', None)
    if runner_class is None:
        logger.error("RandomDofRunner class not found in dof_runner.py")
        return None, dof_dir
    return runner_class, dof_dir


def _dof_log_callback(level, message: str) -> None:
    level_name = getattr(level, "name", str(level)).upper()
    message = message or ""
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


def start_dof_service_if_enabled(iniconfig) -> bool:
    global _RUNNER
    if not _is_enabled(iniconfig):
        return False

    with _LOCK:
        if _RUNNER is not None:
            try:
                if _RUNNER.is_running():
                    return False
            except Exception:
                _RUNNER = None

        runner_class, dof_dir = _load_runner_class()
        if runner_class is None:
            return False

        try:
            _RUNNER = runner_class(
                rom='pinupmenu',
                random_interval_sec=1.1,
                random_min=901,
                random_max=990,
                random_on_value=1,
                debug=logger.isEnabledFor(logging.DEBUG),
                log_callback=_dof_log_callback,
            )
            started = bool(_RUNNER.start())
            if started:
                logger.info("Service started using dof_runner.py from %s", dof_dir)
            else:
                logger.info("Service start requested but runner was already active.")
            return started
        except Exception as e:
            _RUNNER = None
            logger.error("Failed to start service: %s", e)
            return False


def stop_dof_service(timeout: float = 10.0) -> bool:
    global _RUNNER
    with _LOCK:
        runner = _RUNNER
        if runner is None:
            return True

    logger.info("Stopping service...")
    try:
        stopped = bool(runner.stop(timeout=timeout))
    except Exception as e:
        logger.error("Error while stopping service: %s", e)
        stopped = False

    with _LOCK:
        if _RUNNER is runner and (stopped or not _RUNNER.is_running()):
            _RUNNER = None
    return stopped


def restart_dof_service_if_enabled(iniconfig) -> bool:
    stop_dof_service()
    return start_dof_service_if_enabled(iniconfig)
