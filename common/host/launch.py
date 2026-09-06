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

from common import apps, events
from common.config_access import VPinPlayConfig
from common.games import game_play_service, launchers
from common.games.tables import (
    default_table,
    entry_for_filename,
    table_entries,
    table_names,
)
from common.host import launch_state
from common.host.vpx_log import delete_vpinball_log_on_start_if_configured
from common.launcher_path import resolve_launcher_path
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


def _launcher_for(game, vpx_path: str):
    """Which launcher plays this table, and whether it is the one the table asked for.

    Returns (launcher, asked_for). They differ when a table names a launcher that has
    since been switched off, which falls back rather than refusing - and the caller says
    so at launch, because a table quietly running on something else is the question
    nobody can answer weeks later.
    """
    store = launchers.get_launcher_store()
    held = store.launchers()
    table_id = _launched_table_id(game, vpx_path)
    asked_for = store.mapped(table_id)
    return (launchers.launcher_for_table(os.path.basename(vpx_path), table_id,
                                         held, store.mappings()),
            asked_for)


def binary_for(table_id: str, filename: str) -> str:
    """The program that would play this table, for anything that needs to run Visual
    Pinball without starting a session - extracting a script, say.

    Through the same resolution the launch path uses, so what a surface reports and what
    would actually run can never be two different programs. That divergence is the whole
    reason resolution is one function.
    """
    store = launchers.get_launcher_store()
    launcher = launchers.launcher_for_table(filename, table_id, store.launchers(),
                                            store.mappings())
    return _binary_of(launcher, store.mapped(table_id))


def _binary_of(launcher, asked_for: str) -> str:
    """The program a launcher runs, checked before anything is announced."""
    if launcher is None:
        raise LaunchUnavailableError(
            "No launcher configured. Add one under System, or point the one you have "
            "at Visual Pinball.")
    if asked_for and asked_for != launcher.launcher_id:
        logger.warning("Table asked for launcher %s, which is not available; "
                       "launching with %s instead", asked_for, launcher.display_name)
    configured = str(launcher.value("bin_path") or "").strip()
    if not configured:
        raise LaunchUnavailableError(
            f"{launcher.display_name} has no program set.")
    resolved = resolve_launcher_path(configured)
    if not resolved.exists():
        raise LaunchUnavailableError(
            f"{launcher.display_name} points at something that is not there: {resolved}")
    return str(resolved)


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


def _launch_env(launcher) -> dict:
    env = os.environ.copy()
    env.update(parse_launch_env_overrides(str(launcher.value("launch_env") or "")))

    # PyInstaller bundles libraries that can be incompatible with the local ones,
    # so a frozen build hands VPX back the path it started with.
    if platform.system() == "Linux" and getattr(sys, "frozen", False):
        original = env.get("LD_LIBRARY_PATH_ORIG")
        if original is not None:
            env["LD_LIBRARY_PATH"] = original
    return env


def _plan(table: str, binary: str, launcher) -> tuple[list[str], str]:
    """What to run, and what the app writes once it is actually up.

    Both come from the app the launcher wraps. `bin_path` is overwritten with the
    resolved executable, because what a person picked may be a macOS bundle and the app
    is handed something it can spawn.
    """
    app = apps.get(getattr(launcher, "app", "")) or apps.default_app()
    if app.launch is None:
        raise LaunchUnavailableError(
            f"{apps.app_name(app.id)} does not know how to start anything.")

    settings = {declared.key: launcher.value(declared.key)
                for declared in launcher.fields()}
    settings["bin_path"] = binary
    return (app.launch.command(apps.Entry(table=table), settings),
            app.launch.session(settings).readiness_marker)


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
    _binary_of(*_launcher_for(game, resolved))
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
    # The table first: which launcher plays it is a question about the file, so there is
    # nothing to resolve until the file is known.
    vpx_path = _resolve_table(game, table)
    launcher, asked_for = _launcher_for(game, vpx_path)
    binary = _binary_of(launcher, asked_for)

    delete_vpinball_log_on_start_if_configured(
        launcher.value("log_delete_on_start"), str(launcher.value("ini_path") or ""))

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
        cmd, marker = _plan(vpx_path, binary, launcher)
        logger.info("Launching: %s", cmd)
        process = popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            text=True,
            env=_launch_env(launcher),
        )
        launch_state.attach(process)
        started_at = time.time()
        profile = get_active_profile()
        if profile is not None:
            record_game_start(str(getattr(game, "fullPathGame", "")
                                   or getattr(game, "gameDirName", "") or ""))
        else:
            game_play_service.increment_start_count(game, os.path.basename(vpx_path))

        # An app that cannot say when it is up is up as soon as it is spawned. Waiting
        # for a marker that will never come would leave the table launched and nothing
        # ever told about it.
        running = not marker
        if running:
            events.emit(events.TABLE_LAUNCHED, game=game, ini_config=ini_config)

        # Draining stdout is not optional: the pipe fills and the child blocks on a
        # write if nobody reads it.
        for line in process.stdout:
            if not running and marker in line:
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


