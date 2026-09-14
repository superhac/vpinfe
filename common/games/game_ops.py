"""What can be done to a game: make one, describe it, rate it, record what it has done.

The game is the machine; `table_ops` handles the launchable files inside it. Everything
here writes the game's `.info` and answers with what a caller would ask for next.
"""

from __future__ import annotations

from pathlib import Path

from common import service_errors
from common.games import game_identity, game_lens, game_service, locations
from common.games.game_metadata import (
    adopt_vps_details,
    load_game_meta,
    reset_game_play_record,
    set_asset_source,
    set_game_favorite,
    set_game_play_record,
    set_game_rating,
    set_game_tags,
    vps_details_differ,
)
from common.i18n import t

# Which keys this level will accept, and what each is called on disk. Declared rather than
# inferred, so sending a table's key here is refused instead of silently doing nothing - a
# write that reports success and changes nothing is the worst of the options.
GAME_OVERRIDES = {"alt_title": "alt_title", "alt_vps_id": "alt_vpsid",
                  "frontend_dof_event": "frontend_dof_event"}


def create(name: str, location_id: str = "") -> dict:
    """Make a folder with a record in it, in the location new games go to.

    The only way to bring a game into being without a file arriving: an upload creates one
    on the way past, and every other write needs a game that already exists.
    """
    try:
        folder = game_service.create_game(name, location_id)
    except FileExistsError as exc:
        raise service_errors.BlockedError(t("error.games.already_folder_name"),
                                          details={"path": str(exc)}) from exc
    except ValueError as exc:
        raise service_errors.RefusedError(
            str(exc), details=_where_else(location_id)) from exc
    except OSError as exc:
        raise service_errors.BlockedError(
            t("error.games.could_not_create", exc=(exc))) from exc

    # Canonically, never by spelling. Re-reading one folder resolves the path it is given,
    # so the game just created carries the real path while every game a scan found carries
    # the location's own spelling - and under /var on macOS those differ.
    wanted = locations.canonical(str(folder))
    made = next((game for game in game_lens.catalog().values()
                 if locations.canonical(str(game.fullPathGame)) == wanted),
                None)
    if made is None:
        # The folder and its record are on disk and the library did not pick them up.
        # Saying so beats a 500: what was asked for happened, and what is wrong is that the
        # location it landed in is not one this install reads.
        raise service_errors.BlockedError(t("error.games.created_install_not_read"),
                                          details={"path": str(folder)})
    return game_lens.detail(game_identity.game_id(made))


def _where_else(wanted: str) -> dict:
    """The locations that would have worked, for a refusal to offer."""
    where = locations.destination(wanted)
    return {"alternatives": [{"location_id": one.location_id, "name": one.name,
                              "path": one.path} for one in where.alternatives]}


def set_details(game_id: str, values: dict) -> dict:
    """Describe a game no catalog has matched.

    Everything in a game's details normally arrives from VPSdb, which leaves nothing for
    one that came from somewhere else - a library converted from another frontend carries
    a year and a manufacturer, and they would otherwise be read and then dropped.

    Not where a VPS id goes. Saying which catalog record a game is claims an identity
    rather than describing a machine, and the alt_vps_id override is where that is said.
    """
    game = game_lens.game_or_refuse(game_id)
    try:
        game_service.set_details(Path(str(game.fullPathGame)), values)
    except FileNotFoundError as exc:
        raise service_errors.BlockedError(t("error.games.game_no_record_write"),
                                          details={"path": str(exc)}) from exc
    except OSError as exc:
        raise service_errors.BlockedError(
            t("error.games.could_not_write_2", exc=(exc))) from exc
    return game_lens.detail(game_id)


def set_rating(game_id: str, rating) -> dict:
    """Set `User.Rating` on a game, 0-5."""
    return {"rating": set_game_rating(game_lens.game_or_refuse(game_id), rating)}


def set_tags(game_id: str, tags) -> dict:
    """The whole set, not a bag: a repeat is dropped, and case is left alone so two
    spellings stay two tags until somebody merges them."""
    return {"tags": set_game_tags(game_lens.game_or_refuse(game_id), list(tags))}


def set_favorite(game_id: str, favorite: bool) -> dict:
    """Set `User.Favorite` on a game."""
    return {"favorite": set_game_favorite(game_lens.game_or_refuse(game_id), favorite)}


def set_play_record(game_id: str, play_count=None, play_time_seconds=None,
                    last_played=None) -> dict:
    """Set a game's counters, for a library that arrives already played.

    A library converted from another frontend carries a play count and a last-played date,
    and dropping them makes a collection that sorts by either of those wrong on arrival.
    A field left out is left alone.
    """
    return set_game_play_record(game_lens.game_or_refuse(game_id),
                                play_count=play_count,
                                run_time_seconds=play_time_seconds,
                                last_played=last_played)


def reset_play_record(game_id: str) -> dict:
    """Put the counters back to nothing, leaving rating, favorite and tags alone.
    Setting a count to a number is the migration case, and is `set_play_record`."""
    return reset_game_play_record(game_lens.game_or_refuse(game_id))


def set_overrides(game_id: str, changes: dict) -> dict:
    """What the user says about the machine, kept beside what VPS said.

    A patch: only what is sent is written, because the overrides are edited one field at a
    time and restating the others would make every save a race with whatever another
    surface changed meanwhile.
    """
    game = game_lens.game_or_refuse(game_id)
    unknown = set(changes) - set(GAME_OVERRIDES)
    if unknown:
        raise service_errors.RefusedError(
            t("error.games.not_game_s_set", join=(", ".join(sorted(unknown)))))

    game_dir = Path(game.fullPathGame)
    for name, value in changes.items():
        if not game_service.update_vpinfe_setting(game_dir, GAME_OVERRIDES[name], value):
            raise service_errors.BlockedError(
                t("error.games.could_not_write", name=(name)))
    return game_lens.detail(game_id)["overrides"]


def set_file_source(game_id: str, path: str, vps_file_id: str) -> dict:
    """Bind one media or asset file to the upstream record somebody says it is.

    Addressed by path rather than by kind and tier, because the ledger is keyed by path and
    a folder can hold several files of one kind. The path is not required to resolve to
    anything: binding a file the resolver currently passes over is legitimate, and refusing
    it would make the tier rules govern what may be recorded.
    """
    game = game_lens.game_or_refuse(game_id)
    try:
        return set_asset_source(game, path, vps_file_id)
    except ValueError as exc:
        raise service_errors.RefusedError(str(exc)) from exc


def vps_details(game_id: str) -> dict:
    """Where the game's details and the entry it is matched to disagree.

    Empty for a game that has never been re-matched: the details were written from the
    entry, so they agree with it by construction. Correcting a match is what fills this,
    and it fills it completely - the details go on describing the machine the game used
    to be.
    """
    game = game_lens.game_or_refuse(game_id)
    entry = game_service.matched_vps_entry(game)
    if not entry:
        return {"differs": []}
    found = vps_details_differ(load_game_meta(game), entry)
    return {"differs": [{"field": field, "ours": _said(ours), "theirs": _said(theirs)}
                        for field, (ours, theirs) in found.items()]}


def adopt_details(game_id: str) -> dict:
    """Make the game's details describe the entry it is matched to.

    All of them together: they are one machine's facts, and a library holding this one's
    year beside that one's maker describes no machine at all. `Info.VPSId` is not among
    them - it is what VPS supplied, and the value a surface offers to revert a corrected
    match to.
    """
    game = game_lens.game_or_refuse(game_id)
    entry = game_service.matched_vps_entry(game)
    if not entry:
        raise service_errors.NotFoundError(t("error.games.game_matched_no_vps"),
                                           details={"game_id": game_id})
    adopt_vps_details(game, entry)
    return vps_details(game_id)


def _said(value) -> str:
    """One line a person reads, whatever the field holds - a year is a number and themes
    are a list, and a caller rendering a comparison wants neither shape."""
    if isinstance(value, list):
        return ", ".join(str(item) for item in value)
    return str(value if value is not None else "")
