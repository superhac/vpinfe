import importlib.util
import logging
import os
import sys
import threading
from pathlib import Path

_LOCK = threading.Lock()
_CONTROLLER = None
_CURRENT_IMAGE = None
_WRAPPER_NAMES = ('libdmdutil_wrapper.py',)
logger = logging.getLogger("vpinfe.common.libdmdutil_service")


def _is_enabled(iniconfig) -> bool:
    try:
        return iniconfig.config.getboolean('libdmdutil', 'enabled', fallback=False)
    except Exception:
        raw = str(
            iniconfig.config.get('libdmdutil', 'enabled', fallback='false')
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


def _find_wrapper_path(base: Path) -> Path | None:
    return _find_named_path(base, _WRAPPER_NAMES)


def _get_libdmdutil_base_candidates() -> list[Path]:
    env_override = os.environ.get('VPINFE_LIBDMDUTIL_DIR', '').strip()
    candidates = []
    if env_override:
        candidates.append(Path(env_override).expanduser())

    project_root = Path(__file__).resolve().parents[1]
    candidates.append(project_root / 'third-party' / 'libdmdutil')

    meipass = getattr(sys, '_MEIPASS', None)
    if meipass:
        candidates.append(Path(meipass) / 'third-party' / 'libdmdutil')

    exe_dir = Path(sys.executable).resolve().parent
    candidates.append(exe_dir / 'third-party' / 'libdmdutil')
    candidates.append(exe_dir.parent / 'Resources' / 'third-party' / 'libdmdutil')

    return candidates


def _load_controller_class():
    candidates = _get_libdmdutil_base_candidates()
    wrapper_path = None
    for candidate in candidates:
        found = _find_wrapper_path(candidate)
        if found is not None:
            wrapper_path = found
            break

    if wrapper_path is None:
        logger.warning(
            "libdmdutil enabled but wrapper not found. Checked: %s",
            ", ".join(str(c) for c in candidates),
        )
        return None, candidates[0]

    module_dir = wrapper_path.parent
    module_name = f"_vpinfe_{wrapper_path.stem}"
    spec = importlib.util.spec_from_file_location(module_name, wrapper_path)
    if spec is None or spec.loader is None:
        logger.error("Failed to load module spec from: %s", wrapper_path)
        return None, module_dir

    module = importlib.util.module_from_spec(spec)
    module_dir_str = str(module_dir)
    restore_path = False
    if module_dir_str not in sys.path:
        sys.path.insert(0, module_dir_str)
        restore_path = True
    try:
        spec.loader.exec_module(module)
    except Exception as e:
        logger.error("Failed importing libdmdutil_wrapper.py: %s", e)
        return None, module_dir
    finally:
        if restore_path:
            try:
                sys.path.remove(module_dir_str)
            except ValueError:
                pass

    controller_class = getattr(module, 'DMDController', None)
    if controller_class is None:
        logger.error("DMDController class not found in libdmdutil_wrapper.py")
        return None, module_dir
    return controller_class, module_dir


def find_libdmdutil_file(*names: str) -> Path | None:
    candidates = _get_libdmdutil_base_candidates()
    valid_names = tuple(name for name in names if name)
    if not valid_names:
        return None

    for candidate in candidates:
        found = _find_named_path(candidate, valid_names)
        if found is not None:
            return found
    return None


def _build_controller_kwargs(iniconfig) -> dict[str, str]:
    raw_device = str(
        iniconfig.config.get('libdmdutil', 'zedmddevice', fallback='')
    ).strip()
    if raw_device:
        return {'device': raw_device}

    raw_host = str(
        iniconfig.config.get('libdmdutil', 'zedmdwifiaddr', fallback='')
    ).strip()
    if raw_host:
        return {'host': raw_host}

    return {}


def is_running() -> bool:
    with _LOCK:
        return _CONTROLLER is not None


def start_libdmdutil_service_if_enabled(iniconfig) -> bool:
    global _CONTROLLER, _CURRENT_IMAGE
    if not _is_enabled(iniconfig):
        return False

    with _LOCK:
        if _CONTROLLER is not None:
            return False

        controller_class, module_dir = _load_controller_class()
        if controller_class is None:
            return False

        kwargs = _build_controller_kwargs(iniconfig)
        try:
            controller = controller_class(**kwargs)
            info = controller.load()
            _CONTROLLER = controller
            _CURRENT_IMAGE = None
            logger.info(
                "libdmdutil service started from %s with %s",
                module_dir,
                kwargs or {'auto': True},
            )
            if info:
                logger.info("libdmdutil device info: %s", info)
            return True
        except Exception as e:
            _CONTROLLER = None
            _CURRENT_IMAGE = None
            logger.error("Failed to start libdmdutil service: %s", e)
            return False


def stop_libdmdutil_service(clear: bool = False) -> bool:
    global _CONTROLLER, _CURRENT_IMAGE
    with _LOCK:
        controller = _CONTROLLER
        if controller is None:
            return True
        _CONTROLLER = None
        _CURRENT_IMAGE = None

    try:
        try:
            controller.stop(clear=clear)
        except Exception:
            if clear:
                try:
                    controller.clear()
                except Exception:
                    pass
        controller.unload()
        logger.info("libdmdutil service stopped.")
        return True
    except Exception as e:
        logger.error("Error while stopping libdmdutil service: %s", e)
        return False


def restart_libdmdutil_service_if_enabled(iniconfig) -> bool:
    stop_libdmdutil_service(clear=False)
    return start_libdmdutil_service_if_enabled(iniconfig)


def show_image(iniconfig, image_path: str | Path | None) -> bool:
    global _CURRENT_IMAGE
    if not _is_enabled(iniconfig):
        return False

    resolved_path = Path(image_path).expanduser().resolve() if image_path else None

    with _LOCK:
        controller = _CONTROLLER
        current_image = _CURRENT_IMAGE

    if controller is None:
        started = start_libdmdutil_service_if_enabled(iniconfig)
        if not started and not is_running():
            return False
        with _LOCK:
            controller = _CONTROLLER
            current_image = _CURRENT_IMAGE

    if controller is None:
        return False

    try:
        if resolved_path is None or not resolved_path.exists():
            controller.clear()
            with _LOCK:
                _CURRENT_IMAGE = None
            logger.debug("Cleared libdmdutil display because image was missing.")
            return False

        image_str = str(resolved_path)
        if current_image == image_str:
            return True

        controller.hold_image(image_str)
        with _LOCK:
            _CURRENT_IMAGE = image_str
        logger.debug("Displayed real DMD image: %s", image_str)
        return True
    except Exception as e:
        logger.error("Failed to display real DMD image %s: %s", resolved_path, e)
        return False
