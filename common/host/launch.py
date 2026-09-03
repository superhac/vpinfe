"""Launching a game, once, for everybody.

The wheel, the Remote Control page and the HTTP API all arrive here. They used to
each run their own version, which is how one of them ended up recording play data
and the others did not.

Everything specific to a caller is a subscriber rather than an argument: the
frontend's window messages and the last-table record are registered in `frontend/`,
peripherals in `peripherals.py`. This module launches a table and says what
happened. See docs/common.md.
"""

from __future__ import annotations

import logging
import os
import platform
import re
import shlex
import subprocess
import sys
import time
from pathlib import Path

from common import events
from common.config_access import SettingsConfig, VPinPlayConfig
from common.games import game_play_service
from common.games.game_metadata import vpinfe_section
from common.games.tables import (
    default_table,
    entry_for_filename,
    table_entries,
    table_names,
)
from common.host import launch_state
from common.host.vpx_log import delete_vpinball_log_on_start_if_configured
from common.online.vpinplay_runtime import (
    add_game_runtime,
    get_active_profile,
    get_game_user_state,
    record_game_start,
    set_game_score,
)
from common.online.vpinplay_service import sync_single_game_meta
from common.paths import PLUGIN_PROFILES_DIR

logger = logging.getLogger("vpinfe.common.host.launch")

# VPX writes this once the table is actually up. Before it, the process exists but
# the player is looking at nothing.
STARTUP_MARKER = "Startup done"


class LaunchUnavailableError(Exception):
    """The game cannot be launched here, and the message says why.

    Raised rather than logged-and-returned so every caller can tell its own user -
    a notification on a page, an error envelope on the API - instead of each one
    inventing its own way to find out.
    """


class UnknownTableError(LaunchUnavailableError):
    """The caller named a file this game does not have. The caller got it wrong,
    rather than the machine being unable, so it is worth telling apart."""


class LaunchBusyError(LaunchUnavailableError):
    """Something is already playing. Its own type because it is the one refusal
    that is about timing rather than configuration, and a caller may want to say
    so differently."""


def _resolve_launcher(game, settings) -> str:
    launcher, source_key, _ = get_effective_launcher(settings.vpx_bin_path,
                                                     getattr(game, "meta_config", {}))
    if not launcher:
        raise LaunchUnavailableError(
            "No launcher configured. Set Settings.vpxbinpath, or VPinFE.altlauncher "
            "on this table.")
    if not launcher.exists():
        raise LaunchUnavailableError(f"Launcher not found ({source_key}): {launcher}")
    return str(launcher)


def _launched_table_id(game, vpx_path: str) -> str:
    """The id of the table being launched, or "" for a folder with none yet."""
    entries = table_entries(getattr(game, "meta_config", {}))
    return entry_for_filename(entries, os.path.basename(vpx_path))[0]


def _resolve_table(game, table: str | None) -> str:
    """The full path of the file to launch.

    A named file is checked against what is actually in the folder, so a caller
    cannot talk this into running something outside the table's directory.
    """
    game_dir = str(getattr(game, "fullPathGame", "") or "")
    if table is None:
        path = str(getattr(game, "fullPathVPXfile", "") or "")
        if not path:
            raise LaunchUnavailableError("This game has no table to launch")
        return path

    listing = []
    if game_dir and os.path.isdir(game_dir):
        listing = [name for name in os.listdir(game_dir)
                   if os.path.isfile(os.path.join(game_dir, name))]
    if table not in table_names(listing):
        raise UnknownTableError(f"No table named {table} in this game")
    return os.path.join(game_dir, table)


def _launch_env(settings) -> dict:
    env = os.environ.copy()
    env.update(parse_launch_env_overrides(settings.vpx_launch_env))

    # PyInstaller bundles libraries that can be incompatible with the local ones,
    # so a frozen build hands VPX back the path it started with.
    if platform.system() == "Linux" and getattr(sys, "frozen", False):
        original = env.get("LD_LIBRARY_PATH_ORIG")
        if original is not None:
            env["LD_LIBRARY_PATH"] = original
    return env


def _command(game, vpx_path: str, launcher: str, settings) -> list[str]:
    return build_vpx_launch_command(
        launcher_path=launcher,
        vpx_path=vpx_path,
        global_ini_override=settings.global_ini_override,
        tableini_override=resolve_launch_tableini_override(
            vpx_path,
            settings.global_game_ini_override_enabled,
            settings.global_game_ini_override_mask,
        ),
        plugin_profile_override=resolve_launch_plugin_profile(
            get_plugin_profile_from_meta(getattr(game, "meta_config", {}))
        ),
    )


def _record_play(game, ini_config, elapsed_seconds: float, profile, table: str = "") -> None:
    """Play data for a finished session. Runs on every path, which it did not use to."""
    if profile is None:
        game_play_service.add_play_time(game, elapsed_seconds, table)
        game_play_service.update_score_from_nvram(game)
        return

    game_key = str(getattr(game, "fullPathGame", "") or getattr(game, "gameDirName", "") or "")
    if not game_key:
        logger.warning("Skipping alternate VPinPlay submission: missing table key")
        return

    add_game_runtime(game_key, elapsed_seconds, profile.profile_key)
    score_data, score_path = game_play_service.parse_score_from_nvram(game)
    if score_data:
        set_game_score(game_key, score_data, profile.profile_key)
        logger.info("Captured alternate User.Score for %s from %s",
                    game.gameDirName, score_path)

    game_meta = game_play_service.build_runtime_submission_meta(
        game, get_game_user_state(game_key, profile.profile_key))
    if not game_meta:
        return

    vpinplay = VPinPlayConfig.from_config(ini_config)
    if not vpinplay.api_endpoint:
        logger.warning("Skipping alternate VPinPlay submission: API endpoint is not configured.")
        return

    try:
        result = sync_single_game_meta(
            service_ip=vpinplay.api_endpoint,
            user_id=profile.user_id,
            initials=profile.initials,
            machine_id=profile.machine_id,
            game_meta=game_meta,
        )
        logger.info("Alternate VPinPlay submit complete for %s: status=%s ok=%s",
                    game.gameDirName, result.get("status_code"), result.get("ok"))
        if not result.get("ok"):
            logger.warning("Alternate VPinPlay submit failed response: %s",
                           result.get("response_body"))
    except Exception:
        logger.exception("Alternate VPinPlay submit failed for %s", game.gameDirName)


def check_launchable(game, ini_config, table: str | None = None) -> str:
    """Raise if this launch could not go ahead, otherwise return the file it would run.

    Separate from `launch_game` because callers that launch on a thread still have
    to answer their own user now: the Remote page shows a notification and the API
    returns an error, and neither can do that from inside a thread it just started.
    """
    # Ordered from the caller's problem outwards: what it asked for, then whether
    # now is a good time, then whether this machine can do it at all. Checking the
    # launcher first would answer a malformed request with a configuration error.
    resolved = _resolve_table(game, table)
    if launch_state.current().launching:
        raise LaunchBusyError("A table is already launching on this machine")
    _resolve_launcher(game, SettingsConfig.from_config(ini_config))
    return resolved


def launch_game(game, ini_config, *, source: str, table: str | None = None,
                 popen=None) -> None:
    """Launch a game and stay with it until it exits. Blocking.

    Callers that must not block run this on a thread; the API and the Remote page
    both do. Raises LaunchUnavailableError before anything is announced if the table
    cannot be launched at all.
    """
    # Looked up here rather than in the signature so a test can patch it.
    popen = popen or subprocess.Popen
    settings = SettingsConfig.from_config(ini_config)
    launcher = _resolve_launcher(game, settings)
    vpx_path = _resolve_table(game, table)

    delete_vpinball_log_on_start_if_configured(settings)

    # Hooks run first and can still stop this - releasing the peripherals is one.
    # Nothing below has happened yet, so a refusal here leaves nothing to undo.
    # The table id says which build of the game this is: a subscriber recording what
    # played cannot work it out from the game, which offers several.
    events.emit(events.TABLE_LAUNCHING, game=game, ini_config=ini_config,
                table_id=_launched_table_id(game, vpx_path))

    started_at = None
    profile = None
    # Everything from here is inside the try, so table.exited is guaranteed to
    # anyone who heard table.launching - which is what stops a failure below from
    # leaving the frontend with its input suppressed for the life of the process.
    try:
        launch_state.set_launching(getattr(game, "gameDirName", None), source=source)
        cmd = _command(game, vpx_path, launcher, settings)
        logger.info("Launching: %s", cmd)
        process = popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            text=True,
            env=_launch_env(settings),
        )
        launch_state.attach(process)
        started_at = time.time()
        profile = get_active_profile()
        if profile is not None:
            record_game_start(str(getattr(game, "fullPathGame", "")
                                   or getattr(game, "gameDirName", "") or ""))
        else:
            game_play_service.increment_start_count(game, os.path.basename(vpx_path))

        # Draining stdout is not optional: the pipe fills and VPX blocks on a write
        # if nobody reads it.
        running = False
        for line in process.stdout:
            if not running and STARTUP_MARKER in line:
                running = True
                events.emit(events.TABLE_LAUNCHED, game=game, ini_config=ini_config)
                logger.info("table running")

        process.wait()
    finally:
        # Before the play data below, so the peripherals come back promptly rather
        # than waiting on an NVRAM parse and possibly a network call.
        launch_state.clear()
        events.emit(events.TABLE_EXITED, game=game, ini_config=ini_config)

    if started_at is not None:
        _record_play(game, ini_config, max(0.0, time.time() - started_at), profile,
                     os.path.basename(vpx_path))
        events.emit(events.TABLE_PLAY_RECORDED, game=game, ini_config=ini_config)
    game_play_service.delete_nvram_if_configured(game)


def table_for(game, table: str | None = None) -> str:
    """The file a launch would use, without launching it."""
    if table is not None:
        return table
    game_dir = str(getattr(game, "fullPathGame", "") or "")
    listing = []
    if game_dir and os.path.isdir(game_dir):
        listing = [name for name in os.listdir(game_dir)
                   if os.path.isfile(os.path.join(game_dir, name))]
    recorded = os.path.basename(str(getattr(game, "fullPathVPXfile", "") or ""))
    return default_table(listing, os.path.basename(game_dir), recorded) or recorded

# ---------------------------------------------------------------------------
# What to launch with: the alt launcher, the plugin profile, the environment
# overrides and the command line they go into. Was common/host/launcher.py -
# one module named launch and another named launcher said nothing about which
# did what, and this half only ever had one caller outside the other half.
# ---------------------------------------------------------------------------

_ENV_KEY_RE = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*$')

# The built-in plugin profile means "use the live VPinballX.ini", so it adds no
# -ini of its own and leaves whatever VPX would normally read in place.
DEFAULT_PROFILE_NAME = "Default"


def get_altlauncher_from_meta(meta_config) -> str:
    """Read VPinFE.altlauncher from game metadata, normalized as a stripped string."""
    if not isinstance(meta_config, dict):
        return ""
    vpinfe = vpinfe_section(meta_config)
    if not isinstance(vpinfe, dict):
        return ""
    return str(vpinfe.get("alt_launcher", "") or "").strip()


def get_plugin_profile_from_meta(meta_config) -> str:
    """Read VPinFE.pluginprofile from game metadata, normalized as a stripped string."""
    if not isinstance(meta_config, dict):
        return ""
    vpinfe = vpinfe_section(meta_config)
    if not isinstance(vpinfe, dict):
        return ""
    return str(vpinfe.get("plugin_profile", "") or "").strip()


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
    source_key = "alt_launcher" if alt_value else "vpxbinpath"

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


def build_masked_tableini_path(vpx_path: str, override_enabled, override_mask: str) -> str:
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

    vpx_file = Path(str(vpx_path or "").strip())
    if not vpx_file.name:
        return ""

    masked_name = f"{vpx_file.stem}.{mask}.ini"
    return str(vpx_file.with_name(masked_name))


def resolve_launch_tableini_override(vpx_path: str, override_enabled, override_mask: str) -> str:
    """
    Resolve a tableini override for launch-time use.

    Returns empty string when disabled, mask is empty, or the resolved ini file does not exist.
    """
    masked_path = build_masked_tableini_path(vpx_path, override_enabled, override_mask)
    if not masked_path:
        return ""

    if not Path(masked_path).is_file():
        logger.info("Masked tableini does not exist; skipping -tableini: %s", masked_path)
        return ""

    return masked_path


def build_vpx_launch_command(
    launcher_path: str,
    vpx_path: str,
    global_ini_override: str = "",
    tableini_override: str = "",
    plugin_profile_override: str = "",
) -> list[str]:
    """
    Build VPX launch command and guarantee '-play <table>' is the last argument pair.

    A game's plugin profile and the global ini override both drive VPX's single
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

    gameini = str(tableini_override or "").strip()
    if gameini:
        cmd.extend(["-tableini", gameini])

    cmd.extend(["-play", str(vpx_path)])
    return cmd
