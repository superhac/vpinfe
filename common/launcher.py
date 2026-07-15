import sys
import logging
import re
import shlex
from pathlib import Path

from common.paths import PLUGIN_PROFILES_DIR

logger = logging.getLogger("vpinfe.common.launcher")
_ENV_KEY_RE = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*$')

# The built-in plugin profile means "use the live VPinballX.ini", so it adds no
# -ini of its own and leaves whatever VPX would normally read in place.
DEFAULT_PROFILE_NAME = "Default"


def get_altlauncher_from_meta(meta_config) -> str:
    """Read VPinFE.altlauncher from table metadata, normalized as a stripped string."""
    if not isinstance(meta_config, dict):
        return ""
    vpinfe = meta_config.get("VPinFE", {})
    if not isinstance(vpinfe, dict):
        return ""
    return str(vpinfe.get("altlauncher", "") or "").strip()


def get_plugin_profile_from_meta(meta_config) -> str:
    """Read VPinFE.pluginprofile from table metadata, normalized as a stripped string."""
    if not isinstance(meta_config, dict):
        return ""
    vpinfe = meta_config.get("VPinFE", {})
    if not isinstance(vpinfe, dict):
        return ""
    return str(vpinfe.get("pluginprofile", "") or "").strip()


def is_default_plugin_profile(profile_name: str) -> bool:
    return str(profile_name or "").strip().lower() == DEFAULT_PROFILE_NAME.lower()


def plugin_profile_ini_path(profile_name: str) -> Path | None:
    """Resolve a plugin profile name to its .ini path in the profiles folder.

    Returns None for the built-in Default profile and for blank names, since
    neither maps to a file of its own.
    """
    name = str(profile_name or "").strip()
    if not name or is_default_plugin_profile(name):
        return None
    return PLUGIN_PROFILES_DIR / f"{name}.ini"


def resolve_launch_plugin_profile(profile_name: str) -> str:
    """
    Resolve a table's plugin profile to an ini path for launch-time use.

    Returns empty string when unset, when set to Default, or when the profile
    file has been deleted — in each case VPX falls back to its normal ini.
    """
    profile_path = plugin_profile_ini_path(profile_name)
    if profile_path is None:
        return ""

    if not profile_path.is_file():
        logger.warning(
            "Plugin profile '%s' not found; skipping -ini: %s", profile_name, profile_path
        )
        return ""

    return str(profile_path)


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


def parse_launch_env_overrides(raw_value: str) -> dict[str, str]:
    """
    Parse configured launch env overrides into a dict.

    Accepted forms:
    - Single line: KEY=value OTHER=value2
    - Multi line: one KEY=value per line
    - Semicolon separated: KEY=value;OTHER=value2
    """
    text = str(raw_value or "").strip()
    if not text:
        return {}

    normalized = text.replace('\r\n', '\n').replace('\r', '\n').replace(';', '\n')
    tokens: list[str] = []
    for line in normalized.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            tokens.extend(shlex.split(line, comments=True, posix=True))
        except ValueError:
            # Fall back to raw token so we can still parse simple KEY=value.
            tokens.append(line)

    parsed: dict[str, str] = {}
    for token in tokens:
        if '=' not in token:
            logger.warning("Ignoring launch env token without '=': %s", token)
            continue

        key, value = token.split('=', 1)
        key = key.strip()
        if not _ENV_KEY_RE.match(key):
            logger.warning("Ignoring launch env token with invalid key: %s", token)
            continue
        parsed[key] = value

    return parsed


def _to_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in ("1", "true", "yes", "on")


def build_masked_tableini_path(vpx_table_path: str, override_enabled, override_mask: str) -> str:
    """
    Build a masked table ini path for VPX -tableini override.

    Pattern: {VPX_FILENAME_NO_EXT}.{MASK}.ini
    Result path lives next to the source VPX file.
    """
    if not _to_bool(override_enabled):
        return ""

    mask = str(override_mask or "").strip()
    if not mask:
        logger.warning("Global tableini override enabled, but mask is empty; skipping -tableini")
        return ""

    table_path = Path(str(vpx_table_path or "").strip())
    if not table_path.name:
        return ""

    masked_name = f"{table_path.stem}.{mask}.ini"
    return str(table_path.with_name(masked_name))


def resolve_launch_tableini_override(vpx_table_path: str, override_enabled, override_mask: str) -> str:
    """
    Resolve a tableini override for launch-time use.

    Returns empty string when disabled, mask is empty, or the resolved ini file does not exist.
    """
    masked_path = build_masked_tableini_path(vpx_table_path, override_enabled, override_mask)
    if not masked_path:
        return ""

    if not Path(masked_path).is_file():
        logger.info("Masked tableini does not exist; skipping -tableini: %s", masked_path)
        return ""

    return masked_path


def build_vpx_launch_command(
    launcher_path: str,
    vpx_table_path: str,
    global_ini_override: str = "",
    tableini_override: str = "",
    plugin_profile_override: str = "",
) -> list[str]:
    """
    Build VPX launch command and guarantee '-play <table>' is the last argument pair.

    A table's plugin profile and the global ini override both drive VPX's single
    -ini argument, so they cannot both be passed. The per-table profile wins when
    set, mirroring how VPinFE.altlauncher takes precedence over Settings.vpxbinpath.
    """
    cmd = [str(launcher_path)]
    profile_override = str(plugin_profile_override or "").strip()
    ini_override = profile_override or str(global_ini_override or "").strip()
    if profile_override and str(global_ini_override or "").strip():
        logger.info(
            "Plugin profile ini takes precedence over Settings.globalinioverride: %s",
            profile_override,
        )
    if ini_override:
        cmd.extend(["-ini", ini_override])

    tableini = str(tableini_override or "").strip()
    if tableini:
        cmd.extend(["-tableini", tableini])

    cmd.extend(["-play", str(vpx_table_path)])
    return cmd
