"""Launching a table, once, for everybody.

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
import subprocess
import sys
import time

from common import events
from common.config_access import SettingsConfig, VPinPlayConfig
from common.host import launch_state
from common.host.launcher import (
    build_vpx_launch_command,
    get_effective_launcher,
    get_plugin_profile_from_meta,
    parse_launch_env_overrides,
    resolve_launch_plugin_profile,
    resolve_launch_tableini_override,
)
from common.host.vpx_log import delete_vpinball_log_on_start_if_configured
from common.online.vpinplay_runtime import (
    add_table_runtime,
    get_active_profile,
    get_table_user_state,
    record_table_start,
    set_table_score,
)
from common.online.vpinplay_service import sync_single_table_meta
from common.tables import table_play_service
from common.tables.game_files import default_game_file, game_file_names

logger = logging.getLogger("vpinfe.common.host.launch")

# VPX writes this once the table is actually up. Before it, the process exists but
# the player is looking at nothing.
STARTUP_MARKER = "Startup done"


class LaunchUnavailableError(Exception):
    """The table cannot be launched here, and the message says why.

    Raised rather than logged-and-returned so every caller can tell its own user -
    a notification on a page, an error envelope on the API - instead of each one
    inventing its own way to find out.
    """


class UnknownGameFileError(LaunchUnavailableError):
    """The caller named a file this table does not have. The caller got it wrong,
    rather than the machine being unable, so it is worth telling apart."""


class LaunchBusyError(LaunchUnavailableError):
    """Something is already playing. Its own type because it is the one refusal
    that is about timing rather than configuration, and a caller may want to say
    so differently."""


def _resolve_launcher(table, settings) -> str:
    launcher, source_key, _ = get_effective_launcher(settings.vpx_bin_path,
                                                     getattr(table, "metaConfig", {}))
    if not launcher:
        raise LaunchUnavailableError(
            "No launcher configured. Set Settings.vpxbinpath, or VPinFE.altlauncher "
            "on this table.")
    if not launcher.exists():
        raise LaunchUnavailableError(f"Launcher not found ({source_key}): {launcher}")
    return str(launcher)


def _resolve_game_file(table, game_file: str | None) -> str:
    """The full path of the file to launch.

    A named file is checked against what is actually in the folder, so a caller
    cannot talk this into running something outside the table's directory.
    """
    table_dir = str(getattr(table, "fullPathTable", "") or "")
    if game_file is None:
        path = str(getattr(table, "fullPathVPXfile", "") or "")
        if not path:
            raise LaunchUnavailableError("This table has no game file to launch")
        return path

    listing = []
    if table_dir and os.path.isdir(table_dir):
        listing = [name for name in os.listdir(table_dir)
                   if os.path.isfile(os.path.join(table_dir, name))]
    if game_file not in game_file_names(listing):
        raise UnknownGameFileError(f"No game file named {game_file} in this table")
    return os.path.join(table_dir, game_file)


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


def _command(table, vpx_path: str, launcher: str, settings) -> list[str]:
    return build_vpx_launch_command(
        launcher_path=launcher,
        vpx_table_path=vpx_path,
        global_ini_override=settings.global_ini_override,
        tableini_override=resolve_launch_tableini_override(
            vpx_path,
            settings.global_table_ini_override_enabled,
            settings.global_table_ini_override_mask,
        ),
        plugin_profile_override=resolve_launch_plugin_profile(
            get_plugin_profile_from_meta(getattr(table, "metaConfig", {}))
        ),
    )


def _record_play(table, ini_config, elapsed_seconds: float, profile) -> None:
    """Play data for a finished session. Runs on every path, which it did not use to."""
    if profile is None:
        table_play_service.add_runtime_minutes(table, elapsed_seconds)
        table_play_service.update_score_from_nvram(table)
        return

    table_key = str(getattr(table, "fullPathTable", "") or getattr(table, "tableDirName", "") or "")
    if not table_key:
        logger.warning("Skipping alternate VPinPlay submission: missing table key")
        return

    add_table_runtime(table_key, elapsed_seconds, profile.profile_key)
    score_data, score_path = table_play_service.parse_score_from_nvram(table)
    if score_data:
        set_table_score(table_key, score_data, profile.profile_key)
        logger.info("Captured alternate User.Score for %s from %s",
                    table.tableDirName, score_path)

    table_meta = table_play_service.build_runtime_submission_meta(
        table, get_table_user_state(table_key, profile.profile_key))
    if not table_meta:
        return

    vpinplay = VPinPlayConfig.from_config(ini_config)
    if not vpinplay.api_endpoint:
        logger.warning("Skipping alternate VPinPlay submission: API endpoint is not configured.")
        return

    try:
        result = sync_single_table_meta(
            service_ip=vpinplay.api_endpoint,
            user_id=profile.user_id,
            initials=profile.initials,
            machine_id=profile.machine_id,
            table_meta=table_meta,
        )
        logger.info("Alternate VPinPlay submit complete for %s: status=%s ok=%s",
                    table.tableDirName, result.get("status_code"), result.get("ok"))
        if not result.get("ok"):
            logger.warning("Alternate VPinPlay submit failed response: %s",
                           result.get("response_body"))
    except Exception:
        logger.exception("Alternate VPinPlay submit failed for %s", table.tableDirName)


def check_launchable(table, ini_config, game_file: str | None = None) -> str:
    """Raise if this launch could not go ahead, otherwise return the file it would run.

    Separate from `launch_table` because callers that launch on a thread still have
    to answer their own user now: the Remote page shows a notification and the API
    returns an error, and neither can do that from inside a thread it just started.
    """
    # Ordered from the caller's problem outwards: what it asked for, then whether
    # now is a good time, then whether this machine can do it at all. Checking the
    # launcher first would answer a malformed request with a configuration error.
    resolved = _resolve_game_file(table, game_file)
    if launch_state.current().launching:
        raise LaunchBusyError("A table is already launching on this machine")
    _resolve_launcher(table, SettingsConfig.from_config(ini_config))
    return resolved


def launch_table(table, ini_config, *, source: str, game_file: str | None = None,
                 popen=None) -> None:
    """Launch a table and stay with it until it exits. Blocking.

    Callers that must not block run this on a thread; the API and the Remote page
    both do. Raises LaunchUnavailableError before anything is announced if the table
    cannot be launched at all.
    """
    # Looked up here rather than in the signature so a test can patch it.
    popen = popen or subprocess.Popen
    settings = SettingsConfig.from_config(ini_config)
    launcher = _resolve_launcher(table, settings)
    vpx_path = _resolve_game_file(table, game_file)

    delete_vpinball_log_on_start_if_configured(settings)
    table_play_service.track_table_play(table)

    # Hooks run first and can still stop this - releasing the peripherals is one.
    # Nothing below has happened yet, so a refusal here leaves nothing to undo.
    events.emit(events.TABLE_LAUNCHING, table=table, ini_config=ini_config)

    started_at = None
    profile = None
    # Everything from here is inside the try, so table.exited is guaranteed to
    # anyone who heard table.launching - which is what stops a failure below from
    # leaving the frontend with its input suppressed for the life of the process.
    try:
        launch_state.set_launching(getattr(table, "tableDirName", None), source=source)
        cmd = _command(table, vpx_path, launcher, settings)
        logger.info("Launching: %s", cmd)
        process = popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            text=True,
            env=_launch_env(settings),
        )
        started_at = time.time()
        profile = get_active_profile()
        if profile is not None:
            record_table_start(str(getattr(table, "fullPathTable", "")
                                   or getattr(table, "tableDirName", "") or ""))
        else:
            table_play_service.increment_start_count(table)

        # Draining stdout is not optional: the pipe fills and VPX blocks on a write
        # if nobody reads it.
        running = False
        for line in process.stdout:
            if not running and STARTUP_MARKER in line:
                running = True
                events.emit(events.TABLE_LAUNCHED, table=table, ini_config=ini_config)
                logger.info("table running")

        process.wait()
    finally:
        # Before the play data below, so the peripherals come back promptly rather
        # than waiting on an NVRAM parse and possibly a network call.
        launch_state.clear()
        events.emit(events.TABLE_EXITED, table=table, ini_config=ini_config)

    if started_at is not None:
        _record_play(table, ini_config, max(0.0, time.time() - started_at), profile)
    table_play_service.delete_nvram_if_configured(table)


def game_file_for(table, game_file: str | None = None) -> str:
    """The file a launch would use, without launching it."""
    if game_file is not None:
        return game_file
    table_dir = str(getattr(table, "fullPathTable", "") or "")
    listing = []
    if table_dir and os.path.isdir(table_dir):
        listing = [name for name in os.listdir(table_dir)
                   if os.path.isfile(os.path.join(table_dir, name))]
    recorded = os.path.basename(str(getattr(table, "fullPathVPXfile", "") or ""))
    return default_game_file(listing, os.path.basename(table_dir), recorded) or recorded
