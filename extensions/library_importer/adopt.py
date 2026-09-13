"""Turning what a source holds into entries of ours.

It only ever creates. Nothing of the source is written to and nothing already in the
library is changed, so an import that fails partway leaves both exactly as they were
apart from the folders it had already made - and those are new, complete, and named.

Every write goes through the context. Nothing here opens a file of ours or knows where
the library is.
"""

from __future__ import annotations

from pathlib import Path

from . import mapping
from .source import SourceGame, SourceLibrary

# Where a ROM set and the folders keyed on it are placed, by the kind the registry knows
# them as. A colour set comes in two formats and the file decides which, so both are
# tried against what is actually there.
ALT_KINDS = {".crz": "altcolor_serum", ".cromc": "altcolor_serum",
             ".vni": "altcolor_vni", ".pal": "altcolor_vni"}


def _bring_rom(ctx, game_id: str, rom: str, roms_dir: str) -> int:
    """The ROM set itself, if that folder has one by this name."""
    found = next((one for one in Path(roms_dir).glob(f"{rom}.*")
                  if one.is_file()), None)
    if found is None:
        return 0
    try:
        ctx.games.put_asset(game_id, "rom", found)
        return 1
    except FileExistsError:
        return 0
    except Exception as exc:
        ctx.logger.warning("%s did not come across: %s", found.name, exc)
        return 0


def _bring_alt_data(ctx, game_id: str, rom: str, alt_dir: str) -> int:
    """Sound banks and colour sets, which sit in folders named for the ROM.

    The layout is the one PIN2DMD and altsound document: `altcolor/<rom>/` and
    `altsound/<rom>/`, beside each other under one root.
    """
    brought = 0
    root = Path(alt_dir)
    for folder, kind in (("altsound", "altsound"), ("altcolor", ""), ("serum", "")):
        here = root / folder / rom
        if not here.is_dir():
            continue
        if kind:
            brought += _put(ctx, game_id, kind, here, rom)
            continue
        # A colour set's format is the file's to declare, not the folder's.
        for one in sorted(here.iterdir()):
            said = ALT_KINDS.get(one.suffix.lower())
            if said:
                brought += _put(ctx, game_id, said, one, rom)
    return brought


def _remember(ctx, game_id: str, played) -> int:
    """What the old frontend remembered about playing this game.

    The counters go through the one call that sets them; rating, favourite and tags are
    opinions with routes of their own and go through those. A value the source never
    wrote is left alone rather than sent as a zero - a game nobody played and a game
    whose count was never recorded are different, and only one of them should overwrite
    what is already here.
    """
    brought = 0
    try:
        if any(one is not None for one in (played.play_count, played.play_time_seconds,
                                           played.last_played)):
            ctx.games.set_play_record(
                game_id, play_count=played.play_count,
                play_time_seconds=played.play_time_seconds,
                last_played=played.last_played)
            brought = 1
        if played.tags:
            ctx.games.set_tags(game_id, list(played.tags))
            brought = 1
        if played.rating:
            ctx.games.rate_game(game_id, played.rating)
        if played.favorite:
            ctx.games.set_favorite(game_id, True)
    except Exception as exc:
        ctx.logger.warning("Could not carry the play history for %s: %s", game_id, exc)
        return 0
    return brought


def _put(ctx, game_id: str, kind: str, path: Path, rom: str) -> int:
    try:
        ctx.games.put_asset(game_id, kind, path, rom)
        return 1
    except FileExistsError:
        return 0
    except Exception as exc:
        ctx.logger.warning("%s did not come across: %s", path.name, exc)
        return 0


def _one(ctx, source_id: str, game: SourceGame, kinds: tuple[str, ...],
         location: str, name: str = "", sources=None, history=None) -> dict:
    """One game, and what became of it. Returns a row for the report.

    The name is handed in because the caller has already asked core what folder it
    becomes. Working it out again here would give the unsanitized one, and then the same
    game is counted under two names.
    """
    name = name or mapping.folder_name(game)
    row = {"key": game.key, "name": name, "game_id": "", "table": False,
           "media": 0, "companions": 0, "roms": 0, "altdata": 0, "history": 0,
           "skipped_media": [], "error": ""}
    try:
        game_id = ctx.games.create(name, location)
    except Exception as exc:
        row["error"] = str(exc)
        return row

    row["game_id"] = game_id
    details = mapping.details_for(game)
    if details:
        ctx.games.set_details(game_id, **details)

    # The table first, because a media file named for a game file needs that file's name
    # to exist. Its absence is not a failure: a source whose tables are still on the old
    # machine imports as entries with artwork and no game file, which is a state the
    # library has a word for.
    stem, rom = "", ""
    if game.table_file:
        try:
            landed = ctx.games.add_table(game_id, game.table_file)
            row["table"] = True
            row["companions"] = len(landed["companions"])
            rom = landed.get("rom", "")
        except Exception as exc:
            row["error"] = f"the game file did not come across: {exc}"

    for kind, path in mapping.media_for(source_id, game, kinds):
        try:
            ctx.games.put_media(game_id, kind, path, stem)
            row["media"] += 1
        except Exception as exc:
            ctx.logger.warning("%s: %s did not come across: %s", name, kind, exc)
    row["skipped_media"] = mapping.unmapped_kinds(source_id, game, kinds)

    # After the table, because the ROM comes out of the table. A game with no ROM has
    # nothing keyed on it, which is most of a library and not a failure.
    if row["table"] and sources:
        if rom:
            if sources.get("roms"):
                row["roms"] = _bring_rom(ctx, game_id, rom, sources["roms"])
            if sources.get("altdata"):
                row["altdata"] = _bring_alt_data(ctx, game_id, rom, sources["altdata"])

    played = (history or {}).get(game.display_name.strip().lower())
    if played is not None:
        row["history"] = _remember(ctx, game_id, played)
    return row


def _another_build(ctx, game: SourceGame, name: str, game_id: str) -> dict:
    """A second build of a machine the run has already made a game for.

    Its file joins that game rather than starting another one. The artwork does not:
    what is already there was placed for the same machine, and a second build's playfield
    would replace it with a picture of the same table.
    """
    row = {"key": game.key, "name": name, "game_id": game_id, "table": False,
           "media": 0, "companions": 0, "roms": 0, "altdata": 0, "history": 0,
           "skipped_media": [], "error": "", "joined": True}
    if not game.table_file:
        return row
    try:
        landed = ctx.games.add_table(game_id, game.table_file)
        row["table"] = True
        row["companions"] = len(landed["companions"])
    except Exception as exc:
        row["error"] = f"the game file did not come across: {exc}"
    return row


def _history(path: str) -> dict:
    """What the source remembers, by the name it files a game under.

    Keyed on the display name because that is what the stats file writes - the same name
    the artwork is filed under, not the table's filename. Folded, because two frontends
    disagree about case and nobody typed either of them twice.
    """
    if not path:
        return {}
    from . import gamestats

    found, _notes = gamestats.read(path)
    return {one.name.strip().lower(): one for one in found}


def run(ctx, library: SourceLibrary, systems: list[str], location: str = "",
        plan=None) -> dict:
    """Convert the chosen systems. Answers with a row per game and the counts.

    A game that fails is recorded and the next one is tried. An import of six hundred
    stopping on the one folder somebody already had would be worse than useless: it is
    the case this exists for, and the answer is to say which one and carry on.

    A game the library already holds is left alone unless the plan says to fill in what
    it is missing. Rewriting what somebody has curated since the last run is the worse
    mistake, so it is not the default.
    """
    kinds = ctx.games.kinds()
    wanted = [system for system in library.systems
              if not systems or system.name in systems]
    held = {one.key: one for one in (plan.matches if plan else [])}
    sources = {one.key: one.path for one in (plan.sources if plan else ()) if one.active}
    history = _history(sources.get("history", ""))
    fill = bool(plan and plan.on_existing == "fill")

    rows, skipped = [], []
    # What this run has already made, by folder name. A source holds several builds of
    # the same machine - three of Kiss (Bally 1979), by different authors - and they are
    # one game with three tables here, not three games. Without this the first wins the
    # folder and the rest fail on a name that is already taken.
    made_here: dict[str, str] = {}
    for system in wanted:
        for game in system.games:
            match = held.get(game.key)
            if match is not None and match.existing and not fill:
                skipped.append({"key": game.key, "name": match.folder,
                                "game_id": match.game_id, "how": match.how})
                continue
            # Asked of core, not worked out here: the folder a name becomes is core's
            # rule, and a copy of it drifts without saying so.
            name = ctx.games.folder_name_for(mapping.folder_name(game))
            seen = made_here.get(name.lower())
            if seen:
                rows.append(_another_build(ctx, game, name, seen))
                continue
            row = _one(ctx, library.source_id, game, kinds, location, name, sources,
                       history)
            if row["game_id"]:
                made_here[name.lower()] = row["game_id"]
            rows.append(row)
    made = [row for row in rows if row["game_id"]]
    return {
        "games": len({row["name"].lower() for row in made}),
        "tables": sum(1 for row in made if row["table"]),
        "media": sum(row["media"] for row in made),
        "companions": sum(row["companions"] for row in made),
        "roms": sum(row["roms"] for row in made),
        "altdata": sum(row["altdata"] for row in made),
        "history": sum(row["history"] for row in made),
        "failed": len(rows) - len(made),
        # Named rather than counted: after a partial run somebody wants to know which
        # ones were left, not how many.
        "already_here": skipped,
        "rows": rows,
    }
