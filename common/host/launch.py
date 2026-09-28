"""Launching a game, once, for everybody.

The wheel, the Remote Control page and the HTTP API all arrive here, so there is one
launch path and not three that drift - play data is recorded for all of them or none.

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
import shutil
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from common import apps, events, players
from common.config_store import ConfigStore
from common.extensions import services as ext_services
from common.failures import why
from common.games import (
    game_identity,
    game_play_service,
    game_repository,
    high_scores,
    info_file,
    launchers,
    locations,
    score_parser,
    tables,
)
from common.games.game import Game
from common.games.game_metadata import game_private, load_game_meta
from common.games.info_file import InvalidMetaConfigError
from common.games.tables import (
    entry_for_filename,
    table_entries,
    table_names,
)
from common.host import commands, launch_state, table_commands
from common.host.vpx_log import delete_vpinball_log_on_start_if_configured
from common.i18n import t
from common.launcher_path import resolve_launcher_path
from common.paths import CONFIG_DIR, PLUGIN_PROFILES_DIR

logger = logging.getLogger("vpinfe.common.host.launch")

# Where a capture launch's app writes what the table is launched with, while it runs.
CAPTURE_LAUNCH_DIR = CONFIG_DIR / "capture" / "launch"


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


def this_devices_copy(game: Any) -> Game:
    """The game to launch here for one that may have come from another device's library.
    Raises LaunchUnavailableError when this device has no copy of it."""
    here = game_repository.on_this_device(game)
    if here is None:
        raise LaunchUnavailableError(t("error.launch.not_on_this_device"))
    return here


def _launcher_for(table_id: str, entry: dict) -> tuple[launchers.Launcher | None, str]:
    """Which launcher plays this entry, and whether it is the one it asked for.

    Returns (launcher, asked_for). They differ when an entry names a launcher that has
    since been switched off, which falls back rather than refusing - and the caller says
    so at launch, because a table quietly running on something else is the question
    nobody can answer weeks later.
    """
    store = launchers.get_launcher_store()
    asked_for = store.mapped(table_id)
    return (launchers.launcher_for_entry(tables.app_of(entry), table_id,
                                         store.launchers(), store.mappings()),
            asked_for)


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
    return _binary_of(launcher)


def _binary_of(launcher: launchers.Launcher | None) -> str:
    """The program a launcher runs, checked before anything is announced."""
    if launcher is None:
        raise LaunchUnavailableError(t("error.launch.no_launcher_configured"))
    configured = str(launcher.value("bin_path") or "").strip()
    if not configured:
        raise LaunchUnavailableError(
            t("said.no_program_set", launcher_name=launcher.display_name))
    resolved = resolve_launcher_path(configured)
    if not resolved.exists():
        raise LaunchUnavailableError(t("said.program_not_there",
                                       launcher_name=launcher.display_name, path=resolved))
    return str(resolved)


def _resolve_entry(game: Game, named: str | None) -> tuple[str, dict]:
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
        chosen = tables.default_entry(entries, tables.recorded_default(
            (getattr(game, "meta_config", None) or {}).get(info_file.VPINFE_SECTION)))
        if chosen[0] or chosen[1]:
            return chosen
        path = str(game.full_path_vpx_file or "")
        if not path:
            raise LaunchUnavailableError(t("error.launch.nothing_to_launch"))
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
    game_dir = str(game.full_path_game or "")
    listing = []
    if game_dir and os.path.isdir(game_dir):
        listing = [name for name in os.listdir(game_dir)
                   if os.path.isfile(os.path.join(game_dir, name))]
    if wanted not in table_names(listing):
        raise UnknownTableError(t("error.launch.no_table_named", table=named))
    found_id, found = entry_for_filename(entries, wanted)
    return found_id, found or {tables.TABLE_FILENAME_KEY: wanted}


def _path_of(game: Game, entry: dict) -> str:
    """The file an entry names, or "" for one with no file. Every path is built here, so
    nothing above this line handles one at all."""
    game_dir = str(game.full_path_game or "")
    reference = tables.entry_reference(entry)
    if reference:
        return tables.resolved_reference(game_dir, reference)
    filename = tables.entry_filename(entry)
    if not filename:
        return ""
    return os.path.join(game_dir, filename)


def _launch_env(launcher: launchers.Launcher) -> dict:
    env = os.environ.copy()
    env.update(parse_launch_env_overrides(str(launcher.value("launch_env") or "")))

    # PyInstaller bundles libraries that can be incompatible with the local ones,
    # so a frozen build hands VPX back the path it started with.
    if platform.system() == "Linux" and getattr(sys, "frozen", False):
        original = env.get("LD_LIBRARY_PATH_ORIG")
        if original is not None:
            env["LD_LIBRARY_PATH"] = original
    return env


def _plan(entry: apps.Entry, binary: str, launcher: launchers.Launcher, *,
          capture: Path | None = None,
          record_sound: bool = False) -> tuple[list[str], str]:
    """What to run, and what the app writes once it is actually up.

    Both come from the app the launcher wraps. `bin_path` is overwritten with the
    resolved executable, because what a person picked may be a macOS bundle and the app
    is handed something it can spawn. With `capture`, the folder for a recording, the
    app's capture hook answers the command where it has one.
    """
    app = apps.get(getattr(launcher, "app", "")) or apps.default_app()
    if app.launch is None:
        raise LaunchUnavailableError(
            t("error.launch.app_starts_nothing", app_name=apps.app_name(app.id)))

    settings = {declared.key: launcher.value(declared.key)
                for declared in launcher.fields()}
    settings["bin_path"] = binary
    marker = app.launch.session(settings).readiness_marker
    if capture is not None and app.capture is not None:
        return (app.capture.command(entry, settings, sound=record_sound,
                                    folder=str(capture)), marker)
    return app.launch.command(entry, settings), marker


def _capture_folder() -> Path:
    """Emptied first: one still there was left by a launch that never got to close."""
    shutil.rmtree(CAPTURE_LAUNCH_DIR, ignore_errors=True)
    CAPTURE_LAUNCH_DIR.mkdir(parents=True)
    return CAPTURE_LAUNCH_DIR


def _is_private(game: Game) -> bool:
    """Off the file, not `game.meta_config`: that record can predate a Private switch
    thrown during the game."""
    try:
        return game_private(load_game_meta(game))
    except (OSError, InvalidMetaConfigError):
        return game_private(getattr(game, "meta_config", {}))


def _counts_in_the_library(up: list[players.Player]) -> bool:
    return not up or any(player.owner for player in up)


def _record_play(game: Game, elapsed_seconds: float, table: str, rom: str,
                 up: list[players.Player], before: dict | None) -> dict[str, Any]:
    """Play data for a finished session, and what `table.play_recorded` says about it.
    Runs on every path.

    A guest signed in through an extension takes the session - nothing answering means
    nobody is, which is also what an install without that extension looks like. The
    hardware is read once on every path.
    """
    after, score_path = game_play_service.parse_score_from_nvram(game, rom, initials="")
    if after:
        game_play_service.keep_high_scores(game, rom, after, before, score_path)
    one = up[0] if len(up) == 1 else None
    reading = _with_initials(after, one.initials if one else "")

    if ext_services.ask("guest.active") is not None:
        game_key = str(game.full_path_game or game.game_dir_name or "")
        if not game_key:
            logger.warning("Skipping a guest's session: nothing identifies the table")
        else:
            ext_services.ask("guest.record_play", game_key, elapsed_seconds, reading)
            if reading:
                logger.info("Captured a guest's score for %s from %s",
                            game.game_dir_name, score_path)
    elif _counts_in_the_library(up):
        game_play_service.add_play_time(game, elapsed_seconds, table)

    return {"up": [player.as_payload() for player in up],
            "seconds": int(round(elapsed_seconds)),
            "reading": reading,
            "new_entries": _whose_new_entries(before, after, up)}


def _with_initials(reading: dict | None, initials: str) -> dict | None:
    if not reading or "entries" not in reading:
        return reading
    return {**reading,
            "entries": score_parser.entries_with_initials(reading["entries"], initials)}


def _whose_new_entries(before: dict | None, after: dict | None,
                       up: list[players.Player]) -> list[dict[str, Any]]:
    roster = players.get_roster()
    credited: dict[str, tuple[players.Player, list[dict]]] = {}
    for entry in score_parser.new_entries(before, after):
        player = roster.whose_score(str(entry.get("initials") or ""), up)
        if player is not None:
            credited.setdefault(player.player_id, (player, []))[1].append(entry)
    return [{"player": player.as_payload(),
             "entries": score_parser.entries_with_initials(entries, player.initials)}
            for player, entries in credited.values()]


def check_launchable(game: Game, ini_config: ConfigStore,
                     table: str | None = None) -> str:
    """Raise if this launch could not go ahead, otherwise return the file it would run.

    Separate from `launch_game` because callers that launch on a thread still have
    to answer their own user now: the Remote page shows a notification and the API
    returns an error, and neither can do that from inside a thread it just started.
    """
    # Ordered from the caller's problem outwards: what it asked for, then whether
    # now is a good time, then whether this machine can do it at all. Checking the
    # launcher first would answer a malformed request with a configuration error.
    table_id, entry = _resolve_entry(game, table)
    _location_is_reachable(game)
    _reference_is_reachable(game, entry)
    if launch_state.current().launching:
        raise LaunchBusyError(t("error.launch.already_launching"))
    _binary_of(_launcher_for(table_id, entry)[0])
    return _path_of(game, entry) or tables.entry_native_key(entry)


class ReferenceUnreachableError(LaunchUnavailableError):
    """A table that lives somewhere else, and that somewhere is not there right now.

    Its own type because it is not the same as a table being gone: the record and the
    media are here and nothing is lost, so a surface should say the location is
    unreachable rather than offer to forget the entry.
    """


def _location_is_reachable(game: Game) -> None:
    location = locations.get_location_store().get(game.location_id)
    if location is None:
        return
    state = locations.states_of([location], wait=locations.MOUNT_SECONDS)[
        location.location_id]
    if not state.reachable:
        raise ReferenceUnreachableError(t("error.locations.not_reachable",
                                          name=location.name, reason=state.reason))


def _reference_is_reachable(game: Game, entry: dict) -> None:
    """A reference is only as good as the thing it points at, and the usual reason it
    fails is a share that has not mounted - which is temporary, and reads nothing like a
    deleted file."""
    if not tables.entry_reference(entry):
        return
    path = _path_of(game, entry)
    if path and os.path.isfile(path):
        return
    raise ReferenceUnreachableError(t("error.launch.reference_unreachable",
                                      path=path or tables.entry_reference(entry)))


def launch_game(game: Game, ini_config: ConfigStore, *, source: str,
                table: str | None = None,
                popen: Callable[..., subprocess.Popen[Any]] | None = None,
                record_sound: bool = False) -> None:
    """Launch a game and stay with it until it exits. Blocking.

    Callers that must not block run this on a thread; the API and the Remote page
    both do. Raises LaunchUnavailableError before anything is announced if the table
    cannot be launched at all.

    A `SOURCE_CAPTURE` launch is a recording: nobody is up for it, it writes no play
    data, and `table.play_recorded` is not announced. Its app's capture hook says how it
    is launched, told by `record_sound` whether the table's sound is recorded too.
    """
    # Looked up here rather than in the signature so a test can patch it.
    popen = popen or subprocess.Popen
    capturing = source == launch_state.SOURCE_CAPTURE
    # The table first: which launcher plays it is a question about the file, so there is
    # nothing to resolve until the file is known.
    table_id, entry = _resolve_entry(game, table)
    _location_is_reachable(game)
    vpx_path = _path_of(game, entry)
    rom = high_scores.rom_of(entry)
    launcher, asked_for = _launcher_for(table_id, entry)
    binary = _binary_of(launcher)
    # _binary_of refuses a launcher that is missing or cannot run, so there is one here.
    assert launcher is not None
    if asked_for and asked_for != launcher.launcher_id:
        named = launchers.get_launcher_store().get(asked_for)
        logger.warning("%s names launcher %s, which is switched off; "
                       "launching with %s instead",
                       os.path.basename(vpx_path) or tables.entry_native_key(entry),
                       named.display_name if named else asked_for,
                       launcher.display_name)
    playing = apps.Entry(entry_id=table_id, table=vpx_path,
                         game_dir=str(game.full_path_game or ""),
                         key=tables.entry_key(entry))

    delete_vpinball_log_on_start_if_configured(
        launcher.value("log_delete_on_start"), str(launcher.in_effect("ini_path") or ""))

    started_at = None
    folder: Path | None = None
    # The commands' {player} and the session's up are this one reading.
    up: list[players.Player] = [] if capturing else players.get_roster().up()
    before: dict | None = None
    # Outside everything, including our own hooks. What a person writes here sets the
    # machine up for a table, so "before the table" has to mean before all of it -
    # anywhere further in and its meaning shifts as our sequence changes.
    around = table_commands.Around()
    try:
        try:
            around = table_commands.before(game, playing, launcher, ini_config, up=up)
        except commands.CommandRefusedError as exc:
            raise LaunchUnavailableError(why(exc)) from exc

        # Hooks run next and can still stop this - releasing the peripherals is one.
        # Nothing below has happened yet, so a refusal here leaves nothing to undo.
        # The table id says which build of the game this is: a subscriber recording what
        # played cannot work it out from the game, which offers several.
        events.emit(events.TABLE_LAUNCHING, game=game, ini_config=ini_config,
                    table_id=table_id, source=source)

        # Everything from here is inside the try, so table.exited is guaranteed to
        # anyone who heard table.launching - which is what stops a failure below from
        # leaving the frontend with its input suppressed for the life of the process.
        try:
            launch_state.set_launching(game.game_dir_name, source=source)
            folder = _capture_folder() if capturing else None
            cmd, marker = _plan(playing, binary, launcher, capture=folder,
                                record_sound=record_sound)
            if not capturing:
                before, _ = game_play_service.parse_score_from_nvram(game, rom, initials="")
            launched = {"game": game, "ini_config": ini_config, "table_id": table_id,
                        "game_id": game_identity.game_id(game), "source": source,
                        "up": [player.as_payload() for player in up],
                        "private": _is_private(game)}
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
            if not capturing:
                started = ext_services.ask(
                    "guest.record_start",
                    str(game.full_path_game or game.game_dir_name or ""))
                if not started and _counts_in_the_library(up):
                    game_play_service.increment_start_count(
                        game, tables.entry_native_key(entry))

            # An app that cannot say when it is up is up as soon as it is spawned.
            # Waiting for a marker that will never come would leave the table launched
            # and nothing ever told about it.
            running = not marker
            if running:
                events.emit(events.TABLE_LAUNCHED, **launched)

            # Draining stdout is not optional: the pipe fills and the child blocks on a
            # write if nobody reads it.
            for line in process.stdout or ():
                if not running and marker in line:
                    running = True
                    events.emit(events.TABLE_LAUNCHED, **launched)
                    logger.info("table running")

            process.wait()
            around.values["exit_code"] = str(process.returncode)
        finally:
            # Before the play data below, so the peripherals come back promptly rather
            # than waiting on an NVRAM parse and possibly a network call.
            launch_state.clear()
            if folder is not None:
                shutil.rmtree(folder, ignore_errors=True)
            events.emit(events.TABLE_EXITED, game=game, ini_config=ini_config,
                        table_id=table_id, source=source)
    finally:
        # Whenever the ones before ran, even where the program never started - they are
        # what puts the machine back, and it is in that state either way.
        table_commands.after(around, started_at=started_at)

    if started_at is not None and not capturing:
        recorded = _record_play(game, max(0.0, time.time() - started_at),
                                tables.entry_native_key(entry), rom, up, before)
        events.emit(events.TABLE_PLAY_RECORDED, game=game, ini_config=ini_config,
                    table_id=table_id, game_id=game_identity.game_id(game),
                    source=source, private=_is_private(game), **recorded)
    game_play_service.delete_nvram_if_configured(game, entry)


# ---------------------------------------------------------------------------
# What to launch with: the alt launcher, the plugin profile, the environment
# overrides and the command line they go into.
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


