import logging
import threading
from pathlib import Path

from common.external_service import find_named_path, import_module_from_path, third_party_base_candidates

_LOCK = threading.Lock()
_CONTROLLER = None
_CURRENT_IMAGE = None
_WRAPPER_NAMES = ('libdmdutil_wrapper.py',)
_DEFAULT_REALDMD_IMAGE = Path(__file__).resolve().parents[1] / "web" / "images" / "vpinfe_realdmd.png"
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
    return find_named_path(base, names)


def _find_wrapper_path(base: Path) -> Path | None:
    return _find_named_path(base, _WRAPPER_NAMES)


def _get_libdmdutil_base_candidates() -> list[Path]:
    return third_party_base_candidates('VPINFE_LIBDMDUTIL_DIR', 'libdmdutil')


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
    try:
        module = import_module_from_path(wrapper_path)
    except Exception as e:
        logger.error("Failed importing libdmdutil_wrapper.py: %s", e)
        return None, module_dir

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


def _resolve_display_image_path(image_path: str | Path | None) -> Path | None:
    resolved_path = Path(image_path).expanduser().resolve() if image_path else None
    if resolved_path is not None and resolved_path.exists():
        return resolved_path
    if _DEFAULT_REALDMD_IMAGE.exists():
        return _DEFAULT_REALDMD_IMAGE
    return None


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

    resolved_path = _resolve_display_image_path(image_path)

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
        if resolved_path is None:
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
