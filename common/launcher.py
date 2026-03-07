import sys
from pathlib import Path


def get_altlauncher_from_meta(meta_config) -> str:
    """Read VPinFE.altlauncher from table metadata, normalized as a stripped string."""
    if not isinstance(meta_config, dict):
        return ""
    vpinfe = meta_config.get("VPinFE", {})
    if not isinstance(vpinfe, dict):
        return ""
    return str(vpinfe.get("altlauncher", "") or "").strip()


def get_effective_launcher(default_launcher: str, meta_config=None):
    """
    Resolve which executable to launch.
    Uses VPinFE.altlauncher when set, otherwise falls back to vpinfe.ini Settings.vpxbinpath.

    Returns (resolved_path: Path|None, source_key: str, configured_value: str)
    """
    default_value = str(default_launcher or "").strip()
    alt_value = get_altlauncher_from_meta(meta_config)
    configured_value = alt_value or default_value
    source_key = "altlauncher" if alt_value else "vpxbinpath"

    if not configured_value:
        return None, source_key, configured_value

    launcher_path = Path(configured_value).expanduser()

    # macOS App bundle support (same behavior as vpxbinpath handling)
    if sys.platform == "darwin" and launcher_path.suffix.lower() == ".app":
        app_name = launcher_path.stem
        launcher_path = launcher_path / "Contents" / "MacOS" / app_name

    return launcher_path, source_key, configured_value
