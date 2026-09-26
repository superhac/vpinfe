"""What this machine and this install *are*, as against what they are doing.

Facts, not readings, which is why they sit apart from `metrics` - and why the surface
showing them can offer a copy button. What somebody pastes into a bug report is this,
never a graph.

**Grouped here rather than by whoever draws it.** The screen and the clipboard are two
renderings of one answer, and a page that laid the groups out itself would be a second
place for the order to be decided - which is how the copied text and the visible text
come to disagree.

Nothing here is ever missing. A gap sends the reader looking for the gap, where
"Unknown" says the machine could not answer and that is itself the answer.
"""

from __future__ import annotations

import logging
import os
import platform
import socket
import subprocess
from pathlib import Path
from typing import Any

from common.i18n import t

logger = logging.getLogger("vpinfe.common.host.about")

# Read once per process. Every one of these costs a subprocess, a config read or a walk
# of the install, and none of them changes while VPinFE is running.
_held: list[dict[str, Any]] | None = None


def details(refresh: bool = False) -> list[dict[str, Any]]:
    """Every group, in the order they are read and copied."""
    global _held
    if _held is None or refresh:
        browser = _browser_path()
        _held = [
            {"heading": "VPinFE", "facts": [
                (t("word.version"), _version()),
                (t("about.fact.build"), _build_flavor()),
                (t("about.fact.release_target"), _release_target()),
                (t("about.fact.features"), _features()),
                (t("about.fact.frontend_theme"), _active_theme()),
            ]},
            {"heading": t("about.heading.device"), "facts": [
                (t("about.fact.host"), _hostname()),
                (t("about.fact.operating_system"), _os()),
                (t("about.fact.architecture"), platform.machine() or t("word.unknown")),
                (t("about.fact.windowing_system"), windowing_system()),
                ("Python", platform.python_version()),
                (t("about.fact.graphics"), _graphics()),
            ]},
            {"heading": t("about.heading.browser"), "facts": [
                (t("word.name"), _browser_name(browser)),
                (t("word.version"), _browser_version(browser) or t("word.unknown")),
                (t("word.path"), browser or t("about.not_configured")),
            ]},
            {"heading": t("about.heading.locations"), "facts": _locations()},
        ]
    return _held


def as_text() -> str:
    """The same answer as something to paste. Plain text with no markup: it goes into a
    forum post, a chat message and an issue, and only one of those renders a table."""
    lines: list[str] = []
    for group in details():
        lines.append(f"{group['heading']}:")
        width = max((len(label) for label, _ in group["facts"]), default=0)
        lines += [f"  {label.ljust(width)}  {value}" for label, value in group["facts"]]
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def _version() -> str:
    from common.vpinfe_version import get_version

    return str(get_version() or t("word.unknown"))


def _os() -> str:
    system = platform.system() or t("word.unknown")
    if system == "Darwin":
        return f"macOS {platform.mac_ver()[0] or platform.release()}"
    if system == "Windows":
        return f"Windows {platform.release()} ({platform.version()})"
    return f"{system} {platform.release()}".strip()


def _hostname() -> str:
    try:
        return socket.gethostname() or t("word.unknown")
    except OSError:
        return t("word.unknown")


def _install_context() -> dict[str, Any]:
    try:
        from common.online.app_updater import get_install_context

        return dict(get_install_context() or {})
    except Exception:  # noqa: BLE001 - a report is not worth taking the page down for
        logger.debug("Could not read the install context", exc_info=True)
        return {}


def _build_flavor() -> str:
    """Source, slim, fat or a non-release build. The first thing anybody reading a
    report needs, because it decides what else is even installed."""
    found = _install_context()
    reason = found.get("reason")
    if reason == "source_build":
        return t("about.build.source")
    if reason == "non_release_build":
        return t("about.build.non_release")
    if found.get("slim") is True:
        return t("about.build.slim")
    if found.get("slim") is False:
        return t("about.build.full")
    return t("word.unknown")


def _release_target() -> str:
    return str(_install_context().get("triplet") or t("word.unknown"))


def _features() -> str:
    from common import install_identity
    from common.paths import get_ini_config

    try:
        found = install_identity.features(get_ini_config())
    except Exception:  # noqa: BLE001
        logger.debug("Could not read the enabled features", exc_info=True)
        return t("word.unknown")
    return ", ".join(t(install_identity.LABELS.get(name, name)) for name in found
                     if name != install_identity.CORE) or t("word.none")


def _active_theme() -> str:
    try:
        from common.online import theme_service

        return theme_service.get_active_theme() or t("word.unknown")
    except Exception:  # noqa: BLE001
        logger.debug("Could not read the active theme", exc_info=True)
        return t("word.unknown")


def windowing_system() -> str:
    """What is drawing the windows. On Linux it decides whether a screen grab works at
    all, so it is worth reporting rather than inferring from the OS."""
    system = platform.system()
    if system == "Windows":
        return "Windows"
    if system == "Darwin":
        return "Quartz"
    session = os.environ.get("XDG_SESSION_TYPE", "").strip().lower()
    if os.environ.get("WAYLAND_DISPLAY", "").strip() or session == "wayland":
        return "Wayland"
    if os.environ.get("DISPLAY", "").strip() or session == "x11":
        return "X11"
    return t("word.unknown")


def _graphics() -> str:
    """One line, because a report asks whether there is a card at all. Watching one is
    what the Metrics page is for."""
    from common.host import metrics

    found = metrics.gpu()
    if not found["available"]:
        return found["reason"] or t("about.not_reported")
    return ", ".join(str(card.get("name") or t("word.unknown"))
                     for card in found["gpus"]) or t("word.present")


def _browser_path() -> str:
    try:
        from common import device_client

        return str(device_client.local().browser_path() or "")
    except Exception:  # noqa: BLE001 - an install with no frontend has no browser
        logger.debug("Could not read the browser path", exc_info=True)
        return ""


def _browser_name(path: str) -> str:
    if not path:
        return t("about.not_configured")
    lowered = path.lower()
    for fragment, name in (("msedge", "Microsoft Edge"), ("chromium", "Chromium"),
                           ("chrome", "Google Chrome"), ("firefox", "Firefox")):
        if fragment in lowered:
            return name
    return Path(path).name or t("word.unknown")


def _browser_version(path: str) -> str:
    """Asked of the browser itself. A path says which browser is configured; only
    running it says which build is there."""
    if not path:
        return ""
    if platform.system() == "Windows":
        return _windows_file_version(path)
    try:
        done = subprocess.run([path, "--version"], capture_output=True, text=True,
                              timeout=5, check=False)
    except Exception:  # noqa: BLE001 - a browser that will not answer is not a failure
        logger.debug("Could not ask %s for its version", path, exc_info=True)
        return ""
    return (done.stdout or done.stderr or "").strip()


def _windows_file_version(path: str) -> str:
    """`--version` writes to a console Chrome does not have on Windows, so the file's
    own version resource is the only thing that answers."""
    command = ("(Get-Item -LiteralPath '" + path.replace("'", "''") +
               "').VersionInfo.ProductVersion")
    try:
        done = subprocess.run(["powershell", "-NoProfile", "-Command", command],
                              capture_output=True, text=True, timeout=5, check=False)
    except Exception:  # noqa: BLE001
        logger.debug("Could not read the version of %s", path, exc_info=True)
        return ""
    return (done.stdout or "").strip()


def _locations() -> list[tuple[str, str]]:
    """Where this install keeps its things. In a report because half of what looks like
    a bug is VPinFE reading a different directory than somebody edited."""
    from common.log_setup import log_file
    from common.paths import CONFIG_DIR, VPINFE_INI_PATH

    found = [(t("about.fact.configuration"), str(CONFIG_DIR)),
             (t("about.fact.settings_file"), str(VPINFE_INI_PATH))]
    log = log_file()
    found.append((t("about.fact.log_file"), str(log) if log else t("about.not_written_yet")))
    found.append((t("about.fact.tables"), _tables_root()))
    return found


def _tables_root() -> str:
    from common.config_access import SettingsConfig
    from common.paths import get_ini_config

    try:
        root = SettingsConfig.from_config(get_ini_config()).game_root_dir.strip()
    except Exception:  # noqa: BLE001
        logger.debug("Could not read the tables root", exc_info=True)
        return t("word.unknown")
    return root or t("about.not_set")


def reset_for_tests() -> None:
    global _held
    _held = None
