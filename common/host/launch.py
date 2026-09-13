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
from common.extensions import services as ext_services
from common.games import game_play_service, info_file, launchers, tables
from common.games.tables import (
    default_table,
    entry_for_filename,
    table_entries,
    table_names,
)
from common.host import commands, launch_state, table_commands
from common.host.vpx_log import delete_vpinball_log_on_start_if_configured
from common.launcher_path import resolve_launcher_path
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


def _launcher_for(table_id: str, entry: dict):
    """Which launcher plays this entry, and whether it is the one it asked for.

    Returns (launcher, asked_for). They differ when an entry names a launcher that has
    since been switched off, which falls back rather than refusing - and the caller says
    so at launch, because a table quietly running on something else is the question
    nobody can answer weeks later.
    """
    store = launchers.get_launcher_store()
    asked_for = store.mapped(table_id)
    return (launchers.launcher_for_entry(_app_of(entry), table_id, store.launchers(),
                                         store.mappings()),
            asked_for)


def _app_of(entry: dict) -> str:
    """Which app plays an entry.

    A file says so by its own suffix, wherever that file is - a reference names one, so
    it answers the same way a table in the folder does. Something with no file at all
    has to declare it, because nothing about a key says whose it is.
    """
    app = tables.entry_app(entry)
    if app:
        return app
    # The reference first where there is one: it is what the entry actually plays, and
    # a stray `filename` beside it would answer for a file this folder does not have.
    reference = tables.entry_reference(entry)
    named = (os.path.basename(reference) if reference
             else tables.entry_filename(entry))
    found = apps.app_for(named)
    return found.id if found is not None else ""


def binary_for(table_id: str, filename: str) -> str:
    """The program that would play this table, for anything that needs to run Visual
    Pinball without starting a session - extracting a script, say.

    Through the same resolution the launch path uses, so what a surface reports and what
    would actually run can never be two different programs. That divergence is the whole
    reason resolution is one function.
    """
    store = launchers.get_launcher_store()
    found = apps.app_for(filename)
    launcher = launchers.launcher_for_entry(found.id if found else "", table_id,
                                            store.launchers(), store.mappings())
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


def _resolve_entry(game, named: str | None) -> tuple[str, dict]:
    """(table id, entry) for the thing to launch.

    `named` is what a caller asked for by its native key - a filename for something in
    the folder, `app:key` for something the app finds itself. A filename is checked
    against what is actually in the folder, so a caller cannot talk this into running
    something outside the game's directory. A key has nothing to check it against, which
    is the point of a key: the app is the only thing that can say whether it resolves.

    The record answers first and the folder answers second. A folder that has a table but
    no record for it yet is still launchable - which is the same rule discovery follows,
    and the alternative is a game nothing can play until a scan has been round.
    """
    entries = table_entries(getattr(game, "meta_config", {}))
    if named is None:
        found = tables.default_entry(
            entries, getattr(game, "gameDirName", "") or "",
            tables.recorded_default(
                (getattr(game, "meta_config", None) or {}).get(info_file.VPINFE_SECTION),
                entries))
        if found[0] or found[1]:
            return found
        path = str(getattr(game, "fullPathVPXfile", "") or "")
        if not path:
            raise LaunchUnavailableError("This game has nothing to launch")
        return "", {tables.TABLE_FILENAME_KEY: os.path.basename(path)}

    wanted = str(named).strip()
    for entry_id, entry in entries.items():
        if tables.entry_native_key(entry) != wanted:
            continue
        # A key and a path are both only in the record - the folder has never heard of
        # either, so there is nothing to check them against here. What answers for a
        # reference is whether the file is there, and that is `check_launchable`'s job
        # rather than a name lookup's.
        if tables.entry_key(entry) or tables.entry_reference(entry):
            return entry_id, entry

    # A filename, so the folder decides whether it is real - not the record, which can
    # describe a file somebody has since deleted.
    game_dir = str(getattr(game, "fullPathGame", "") or "")
    listing = []
    if game_dir and os.path.isdir(game_dir):
        listing = [name for name in os.listdir(game_dir)
                   if os.path.isfile(os.path.join(game_dir, name))]
    if wanted not in table_names(listing):
        raise UnknownTableError(f"No table named {named} in this game")
    found_id, found = entry_for_filename(entries, wanted)
    return found_id, found or {tables.TABLE_FILENAME_KEY: wanted}


def _path_of(game, entry: dict) -> str:
    """The file an entry names, or "" for one with no file. Every path is built here, so
    nothing above this line handles one at all."""
    game_dir = str(getattr(game, "fullPathGame", "") or "")
    reference = tables.entry_reference(entry)
    if reference:
        return tables.resolved_reference(game_dir, reference)
    filename = tables.entry_filename(entry)
    if not filename:
        return ""
    return os.path.join(game_dir, filename)


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


def _plan(entry: apps.Entry, binary: str, launcher) -> tuple[list[str], str]:
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
    return (app.launch.command(entry, settings),
            app.launch.session(settings).readiness_marker)


def _record_play(game, ini_config, elapsed_seconds: float, table: str = "") -> None:
    """Play data for a finished session. Runs on every path, which it did not use to.

    A guest takes the session if one is signed in - their half hour is theirs and must
    not land in the play count of a library that is not theirs. Nothing answering means
    nobody is, which is also what an install without that extension looks like. The
    hardware is read once on either path.
    """
    if ext_services.ask("guest.active") is None:
        game_play_service.add_play_time(game, elapsed_seconds, table)
        game_play_service.update_score_from_nvram(game)
        return

    game_key = str(getattr(game, "fullPathGame", "")
                   or getattr(game, "gameDirName", "") or "")
    if not game_key:
        logger.warning("Skipping a guest's session: nothing identifies the table")
        return

    score_data, score_path = game_play_service.parse_score_from_nvram(game)
    ext_services.ask("guest.record_play", game_key, elapsed_seconds, score_data)
    if score_data:
        logger.info("Captured a guest's score for %s from %s",
                    game.gameDirName, score_path)


def check_launchable(game, ini_config, table: str | None = None) -> str:
    """Raise if this launch could not go ahead, otherwise return the file it would run.

    Separate from `launch_game` because callers that launch on a thread still have
    to answer their own user now: the Remote page shows a notification and the API
    returns an error, and neither can do that from inside a thread it just started.
    """
    # Ordered from the caller's problem outwards: what it asked for, then whether
    # now is a good time, then whether this machine can do it at all. Checking the
    # launcher first would answer a malformed request with a configuration error.
    table_id, entry = _resolve_entry(game, table)
    _reference_is_reachable(game, entry)
    if launch_state.current().launching:
        raise LaunchBusyError("A table is already launching on this machine")
    _binary_of(*_launcher_for(table_id, entry))
    return _path_of(game, entry) or tables.entry_native_key(entry)


class ReferenceUnreachableError(LaunchUnavailableError):
    """A table that lives somewhere else, and that somewhere is not there right now.

    Its own type because it is not the same as a table being gone: the record and the
    media are here and nothing is lost, so a surface should say the location is
    unreachable rather than offer to forget the entry.
    """


def _reference_is_reachable(game, entry: dict) -> None:
    """A reference is only as good as the thing it points at, and the usual reason it
    fails is a share that has not mounted - which is temporary, and reads nothing like a
    deleted file."""
    if not tables.entry_reference(entry):
        return
    path = _path_of(game, entry)
    if path and os.path.isfile(path):
        return
    raise ReferenceUnreachableError(
        f"This table lives at {path or tables.entry_reference(entry)}, which is not "
        "reachable from here.")


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
    table_id, entry = _resolve_entry(game, table)
    vpx_path = _path_of(game, entry)
    launcher, asked_for = _launcher_for(table_id, entry)
    binary = _binary_of(launcher, asked_for)
    playing = apps.Entry(entry_id=table_id, table=vpx_path,
                         game_dir=str(getattr(game, "fullPathGame", "") or ""),
                         key=tables.entry_key(entry))

    delete_vpinball_log_on_start_if_configured(
        launcher.value("log_delete_on_start"), str(launcher.value("ini_path") or ""))

    started_at = None
    # Outside everything, including our own hooks. What a person writes here sets the
    # machine up for a table, so "before the table" has to mean before all of it -
    # anywhere further in and its meaning shifts as our sequence changes.
    around = table_commands.Around()
    try:
        try:
            around = table_commands.before(game, playing, launcher, ini_config)
        except commands.CommandRefusedError as exc:
            raise LaunchUnavailableError(str(exc)) from exc

        # Hooks run next and can still stop this - releasing the peripherals is one.
        # Nothing below has happened yet, so a refusal here leaves nothing to undo.
        # The table id says which build of the game this is: a subscriber recording what
        # played cannot work it out from the game, which offers several.
        events.emit(events.TABLE_LAUNCHING, game=game, ini_config=ini_config,
                    table_id=table_id)

        # Everything from here is inside the try, so table.exited is guaranteed to
        # anyone who heard table.launching - which is what stops a failure below from
        # leaving the frontend with its input suppressed for the life of the process.
        try:
            launch_state.set_launching(getattr(game, "gameDirName", None), source=source)
            cmd, marker = _plan(playing, binary, launcher)
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
            # A guest's play is not the library's. Whoever is signed in takes the
            # session, and the game's own count moves only when nobody is.
            started = ext_services.ask(
                "guest.record_start",
                str(getattr(game, "fullPathGame", "")
                    or getattr(game, "gameDirName", "") or ""))
            if not started:
                game_play_service.increment_start_count(
                    game, tables.entry_native_key(entry))

            # An app that cannot say when it is up is up as soon as it is spawned.
            # Waiting for a marker that will never come would leave the table launched
            # and nothing ever told about it.
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
            around.values["exit_code"] = str(process.returncode)
        finally:
            # Before the play data below, so the peripherals come back promptly rather
            # than waiting on an NVRAM parse and possibly a network call.
            launch_state.clear()
            events.emit(events.TABLE_EXITED, game=game, ini_config=ini_config)
    finally:
        # Whenever the ones before ran, even where the program never started - they are
        # what puts the machine back, and it is in that state either way.
        table_commands.after(around, started_at=started_at)

    if started_at is not None:
        _record_play(game, ini_config, max(0.0, time.time() - started_at),
                     tables.entry_native_key(entry))
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


