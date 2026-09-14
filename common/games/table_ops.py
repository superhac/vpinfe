"""What can be done to one of a game's tables: name it, rate it, bind it, forget it.

A table is the launchable artifact; the game is the machine. Everything here writes the
game's `.info` and answers with the table as the lens describes it, because a caller that
just changed one is about to redraw the row.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

from common import apps, service_errors
from common.games import game_lens, locations, table_lens, tables
from common.games.game_metadata import (
    load_game_meta,
    meta_file_path,
    reset_table_play_record,
    set_table_rating,
    set_table_source,
    vpinfe_section,
)
from common.games.game_repository import game_to_row
from common.games.ids import new_id
from common.games.info_file import MetaConfig
from common.games.tables import ABSENT_SINCE_KEY, entry_filename, table_entries
from common.host import launch
from common.i18n import t

# Which keys each level will accept. Declared rather than inferred, so sending a table's
# key to the game route is refused instead of silently doing nothing - a write that
# reports success and changes nothing is the worst of the options.
TABLE_OVERRIDES = ("alt_launcher", "plugin_profile", "delete_nvram_on_close")


def rows_of(game_id: str) -> dict:
    """Every table this game offers."""
    game = game_lens.game_or_refuse(game_id)
    return {"tables": table_lens.table_rows(game, game_to_row(game))}


def row_or_refuse(game, table_id: str) -> dict:
    """One table as the lens describes it, or a refusal naming it."""
    found = next((row for row in table_lens.table_rows(game, game_to_row(game))
                  if row.get("id") == table_id), None)
    if found is None:
        raise service_errors.NotFoundError(t("error.games.game_no_such_table"),
                                           details={"table": table_id})
    return found


def filename_or_refuse(game, table_id: str) -> str:
    """The .vpx an id names. Distinct from the media lens's stem lookup: this one wants
    the name on disk, not the stem a file would be named after."""
    entry = table_entries(load_game_meta(game)).get(table_id)
    filename = entry_filename(entry) if isinstance(entry, dict) else ""
    if not filename:
        raise service_errors.NotFoundError(
            t("error.games.game_no_such_table"),
            details={"game": game.game_dir_name, "table": table_id})
    return filename


def set_hidden(game_id: str, table_id: str, hidden: bool) -> dict:
    """Take a table out of play without taking it off disk.

    The two are different acts and only one is reversible by itself: a hidden table is
    still there with its stats and its match, and a patch base that stopped being offered
    is exactly what this is for.
    """
    game = game_lens.game_or_refuse(game_id)
    filename = filename_or_refuse(game, table_id)
    MetaConfig(str(meta_file_path(game))).set_table_hidden(filename, bool(hidden))
    game.meta_config = load_game_meta(game)
    return row_or_refuse(game, table_id)


def extract_script(game_id: str, table_id: str) -> dict:
    """Write the table's script out as a `<table>.vbs` next to the .vpx.

    **This changes which script the table runs.** VPX loads a sidecar in place of the one
    inside the .vpx, so extracting is how a table is patched - and it is why the install
    reports the script as internal or external rather than as merely extracted.

    Runs the configured launcher, so it answers for the machine it is called on: an
    install with no VPX cannot do this.
    """
    from common.games import game_service

    game = game_lens.game_or_refuse(game_id)
    filename = filename_or_refuse(game, table_id)
    game_dir = Path(game.full_path_game or "")
    if not (game_dir / filename).is_file():
        raise service_errors.NotFoundError(t("error.games.table_s_file_not"),
                                           details={"table": table_id})
    table_id = tables.entry_for_filename(table_entries(game.meta_config), filename)[0]
    # Asked before the work rather than read out of the failure: with the table's file
    # accounted for, every remaining launcher error means this machine cannot do it,
    # which is what /launch already answers - not a missing resource.
    try:
        launch.binary_for(table_id, filename)
    except launch.LaunchUnavailableError as exc:
        raise service_errors.UnavailableError(
            t("error.games.extracting_script_runs_visual", exc=(exc))) from exc
    try:
        game_service.extract_vbs(game_dir, filename, table_id)
    except Exception as exc:
        raise service_errors.RefusedError(
            t("error.games.could_not_extract_script", exc=(exc))) from exc
    return row_or_refuse(game, table_id)


def delete_script(game_id: str, table_id: str) -> dict:
    """Take the sidecar away, which puts the table back on the script inside its .vpx.

    Whatever the sidecar held goes with it - a patch, an edit - and nothing else knows
    what was in it, which is why the surface asks first.
    """
    from common.games import media_ops

    game = game_lens.game_or_refuse(game_id)
    game_dir = Path(game.full_path_game or "")
    script = game_dir / f"{media_ops.stem_or_refuse(game, table_id)}.vbs"
    if not script.is_file():
        raise service_errors.NotFoundError(t("error.games.table_no_script_beside"),
                                           details={"table": table_id})
    script.unlink()
    return row_or_refuse(game, table_id)


def set_rating(game_id: str, table_id: str, rating) -> dict:
    """A table's own rating, which refines the game's rather than replacing it."""
    game = game_lens.game_or_refuse(game_id)
    set_table_rating(game, filename_or_refuse(game, table_id), rating)
    game.meta_config = load_game_meta(game)
    return row_or_refuse(game, table_id)


def set_source(game_id: str, table_id: str, vps_file_id: str) -> dict:
    """Bind one table to the upstream release somebody says it is, or unbind it.

    A person picking from a list, never a guess: the identifier this records was retired
    at chance and is confidently wrong more often than not, so nothing here proposes an
    answer. An empty id takes the claim back.
    """
    game = game_lens.game_or_refuse(game_id)
    set_table_source(game, filename_or_refuse(game, table_id), vps_file_id)
    game.meta_config = load_game_meta(game)
    return row_or_refuse(game, table_id)


def reset_play_record(game_id: str, table_id: str) -> dict:
    """One table's counters. The game's total is not touched: they are two records of two
    things, and a game played on one build has still been played."""
    game = game_lens.game_or_refuse(game_id)
    return reset_table_play_record(game, filename_or_refuse(game, table_id))


def set_default(game_id: str, table_id: str) -> dict:
    """Record the choice, or clear it by naming nothing.

    A game's default is the one a member naming only the game resolves to, so this is the
    difference between a collection playing the VR build and the desktop one.
    """
    game = game_lens.game_or_refuse(game_id)
    if table_id:
        filename_or_refuse(game, table_id)
    try:
        MetaConfig(str(meta_file_path(game))).set_default_table(table_id)
    except ValueError as exc:
        raise service_errors.RefusedError(str(exc),
                                          details={"table": table_id}) from exc
    game.meta_config = load_game_meta(game)
    return {"tables": table_lens.table_rows(game, game_to_row(game))}


def set_overrides(game_id: str, table_id: str, changes: dict) -> dict:
    """What the user says about one launchable file.

    Written onto the table's own entry, never onto the folder - a folder value is read as
    a fallback for a 2.x library but is not where anything lands now.
    """
    from common.games import game_service

    game = game_lens.game_or_refuse(game_id)
    unknown = set(changes) - set(TABLE_OVERRIDES)
    if unknown:
        raise service_errors.RefusedError(
            t("error.games.not_table_s_set", join=(", ".join(sorted(unknown)))))

    game_dir = Path(game.full_path_game)
    if table_id not in table_entries(load_game_meta(game)):
        raise service_errors.NotFoundError(
            t("error.games.no_table_id_game", table_id=(table_id), game_id=(game_id)))
    for name, value in changes.items():
        if not game_service.update_table_vpinfe_setting(game_dir, table_id, name, value):
            raise service_errors.BlockedError(
                t("error.games.could_not_write", name=(name)))
    fresh = game_lens.game_or_refuse(game_id)
    return table_lens.table_overrides(
        table_entries(load_game_meta(fresh)).get(table_id) or {},
        vpinfe_section(fresh.meta_config))


def import_file(game_id: str, path: str) -> dict:
    """Bring a game file in from a path this install may read.

    One call rather than pointing at it and then bringing it in: an import interrupted
    between those two leaves a library of entries referencing a folder that was only ever
    meant to be read from. A copy, not a move.
    """
    from common.games import game_service

    game = game_lens.game_or_refuse(game_id)
    source = Path(path)
    if not source.is_file():
        raise service_errors.RefusedError(t("error.games.not_file"),
                                          details={"path": str(path)})
    if apps.app_for(source.name) is None:
        raise service_errors.RefusedError(
            t("error.games.nothing_build_knows_plays", name=(source.name)))

    game_dir = Path(game.full_path_game or "")
    table_id = new_id()
    try:
        game_service.add_table_file(game_dir, source, table_id)
    except FileExistsError as exc:
        raise service_errors.BlockedError(t("error.games.game_already_file_name"),
                                          details={"filename": str(exc)}) from exc
    except (OSError, ValueError) as exc:
        raise service_errors.BlockedError(
            t("error.games.could_not_bring", exc=(exc))) from exc

    game.meta_config = load_game_meta(game)
    return row_or_refuse(game, table_id)


def add_keyed(game_id: str, app_id: str, key: str) -> dict:
    """Record a ROM, a Pinball FX table, or anything else its program finds by name.

    Nothing is scanned into existence here, and nothing can be: a folder scan finds files,
    and this is the one kind of entry that has none.

    We never resolve the key. The whole reason a key is not a path is that the program
    already looks it up, and better - pointing at `roms/mm.zip` would break the moment
    somebody reorganized their rompath.
    """
    game = game_lens.game_or_refuse(game_id)
    app_id = str(app_id or "").strip()
    app = apps.get(app_id)
    if app is None:
        raise service_errors.RefusedError(
            t("error.games.no_app_called_build", app_id=(app_id),
              join=(", ".join(one.id for one in apps.all_apps()))))
    if not app.claim.accepts_keys:
        raise service_errors.RefusedError(
            t("error.games.plays_files_not_names", app_name=(apps.app_name(app_id))))
    key = str(key or "").strip()
    if not key:
        raise service_errors.RefusedError(t("error.games.say_what_program_calls"))

    table_id = new_id()
    if not MetaConfig(str(meta_file_path(game))).add_keyed_table(app_id, key, table_id):
        raise service_errors.BlockedError(t("error.games.game_already_one"),
                                          details={"app": app_id, "key": key})
    game.meta_config = load_game_meta(game)
    return row_or_refuse(game, table_id)


def add_referenced(game_id: str, path: str) -> dict:
    """A game file that lives somewhere else - on a read-only share, or one file two games
    both point at.

    Checked against the disk now, because a path that is wrong the moment it is typed is a
    typo and should be refused rather than kept as a broken record. A path that stops
    resolving later is a different thing: the location is unreachable, the entry stands,
    and nothing here is lost.
    """
    game = game_lens.game_or_refuse(game_id)
    game_dir = str(game.full_path_game or "")
    target = os.path.expanduser(str(path or "").strip())
    if not target:
        raise service_errors.RefusedError(t("error.games.say_where_file"))
    if not os.path.isabs(target):
        raise service_errors.RefusedError(t("error.games.give_full_path_file"))
    if not os.path.isfile(target):
        raise service_errors.NotFoundError(t("error.games.no_file"),
                                           details={"path": target})
    if apps.app_for(os.path.basename(target)) is None:
        raise service_errors.RefusedError(
            t("error.games.nothing_build_knows_plays", name=(os.path.basename(target))))
    if locations.canonical(os.path.dirname(target)) == locations.canonical(game_dir):
        raise service_errors.RefusedError(t("error.games.file_already_game_s"))

    # Relative where it survives the library moving, absolute where it would not.
    stored = locations.portable_reference(game_dir, target)
    table_id = new_id()
    if not MetaConfig(str(meta_file_path(game))).add_referenced_table(stored, table_id):
        raise service_errors.BlockedError(t("error.games.game_already_points_file"),
                                          details={"path": stored})
    game.meta_config = load_game_meta(game)
    return row_or_refuse(game, table_id)


def contain(game_id: str, table_id: str) -> dict:
    """Bring the referenced file into the game folder, so the entry stops depending on
    somewhere else being there.

    The id survives, which is the point - a collection that named this table and the play
    record on it both stay pointed at it. The file is copied and not moved: what it
    references may be read-only, shared with another game, or somebody else's.
    """
    game = game_lens.game_or_refuse(game_id)
    entry = table_entries(load_game_meta(game)).get(table_id)
    if not isinstance(entry, dict) or not tables.entry_reference(entry):
        raise service_errors.NotFoundError(t("error.games.game_no_such_reference"),
                                           details={"table": table_id})

    game_dir = Path(game.full_path_game or "")
    source = Path(tables.resolved_reference(str(game_dir), tables.entry_reference(entry)))
    if not source.is_file():
        raise service_errors.BlockedError(t("error.games.file_not_reachable_nothing"),
                                          details={"path": str(source)})
    landing = game_dir / source.name
    if landing.exists():
        raise service_errors.BlockedError(t("error.games.game_already_file_name"),
                                          details={"filename": source.name})

    try:
        shutil.copy2(source, landing)
    except OSError as exc:
        raise service_errors.BlockedError(
            t("error.games.could_not_copy", exc=(exc))) from exc

    if not MetaConfig(str(meta_file_path(game))).contain_referenced_table(table_id,
                                                                         source.name):
        # The copy landed and the record did not, which is the one state worth undoing: a
        # file in the folder with nothing describing it becomes a second table on the next
        # scan, beside the reference that is still there.
        landing.unlink(missing_ok=True)
        raise service_errors.BlockedError(t("error.games.could_not_record"),
                                          details={"table": table_id})
    game.meta_config = load_game_meta(game)
    return row_or_refuse(game, table_id)


def forget(game_id: str, table_id: str) -> dict:
    """Drop the record of a table whose file is no longer there.

    No file is deleted, because there is none - what goes is the entry describing it.
    Refused while the .vpx is on disk: that entry describes something the user owns, and
    the next refresh would mint it again anyway.
    """
    game = game_lens.game_or_refuse(game_id)
    entry = table_entries(load_game_meta(game)).get(table_id)
    if not isinstance(entry, dict):
        raise service_errors.NotFoundError(
            t("error.games.game_no_such_table"),
            details={"game": game.game_dir_name, "table": table_id})
    meta = MetaConfig(str(meta_file_path(game)))
    if tables.entry_key(entry) or tables.entry_reference(entry):
        # Nothing in this folder will mint one of these again, which is exactly why
        # forgetting it is safe where forgetting a table that is there is not. A reference
        # forgotten leaves the file it pointed at alone.
        meta.forget_keyed_table(table_id)
    elif not entry.get(ABSENT_SINCE_KEY):
        raise service_errors.BlockedError(
            t("error.games.table_s_file_still"),
            details={"table": table_id, "filename": entry.get("filename", "")})
    else:
        meta.forget_table(table_id)
    # The scan's copy still describes the table that just went.
    game.meta_config = load_game_meta(game)
    return {"forgotten": table_id}
