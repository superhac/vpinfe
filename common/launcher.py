import sys
import logging
import re
import shlex
from pathlib import Path

logger = logging.getLogger("vpinfe.common.launcher")
_ENV_KEY_RE = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*$')


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
