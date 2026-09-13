"""The one place that knows both vocabularies.

A reader reports what a source calls things; core stores what we call them. Everything
that turns one into the other is here, once, because a mapping decided in four places is
four things to keep in step.

The kind names are asked of core rather than written down, so a build that gains a media
kind does not leave a stale list behind here.
"""

from __future__ import annotations

from .source import SourceGame

# A PinballX media folder is one of our kinds. The pairs are unambiguous in this
# direction: the source files a still and a moving version of one subject in two folders,
# and we hold those as two kinds, so each folder has exactly one answer.
PINBALLX_KINDS = {
    "Table Images": "playfield",
    "Table Videos": "playfield_video",
    "Backglass Images": "backglass",
    "Backglass Videos": "backglass_video",
    "DMD Images": "scoreview",
    "DMD Videos": "scoreview_video",
    "Topper Images": "topper",
    "Topper Videos": "topper_video",
    "Wheel Images": "wheel",
    "Table Audio": "audio",
    "Launch Audio": "audio_launch",
    "Logos": "logo",
}

# EmulationStation names the file on the game rather than filing it in a folder, so the
# element is the kind. Three of them have an answer here; a thumbnail is a smaller copy of
# a picture we already take, and fanart has no slot, so both are reported rather than put
# somewhere approximate.
EMULATIONSTATION_KINDS = {
    "image": "playfield",
    "video": "playfield_video",
    "marquee": "wheel",
}

# Popper files a folder per kind under the emulator's media directory, and unlike
# PinballX it does not split a still from a moving one - a PlayField folder holds both,
# and which we store it as follows the file's own extension.
POPPER_KINDS = {
    "PlayField": "playfield",
    "BackGlass": "backglass",
    "DMD": "scoreview",
    "Wheel": "wheel",
    "Topper": "topper",
    "Loading": "loading",
    "GameInfo": "instruction_card",
    "GameHelp": "rule_sheet",
    "Audio": "audio",
    "AudioLaunch": "audio_launch",
}

# Where a source keeps stills and video together, the extension decides which of ours it
# is. Only the kinds that have both.
MOVING = {
    "playfield": "playfield_video",
    "backglass": "backglass_video",
    "scoreview": "scoreview_video",
    "topper": "topper_video",
}
VIDEO_SUFFIXES = frozenset({".mp4", ".m4v", ".mkv", ".avi", ".mov", ".webm", ".f4v"})

KINDS_BY_SOURCE = {
    "pinballx": PINBALLX_KINDS,
    "popper": POPPER_KINDS,
    "emulationstation": EMULATIONSTATION_KINDS,
}


def media_for(source_id: str, game: SourceGame, known: tuple[str, ...]) -> list[tuple[str, str]]:
    """(kind, path) for every file we have a slot for.

    `known` is what core says it stores. A folder this build has no kind for is left
    behind rather than guessed at - PinballX's full-DMD menu video is a real example, and
    putting it somewhere approximate would be worse than not carrying it.
    """
    table = KINDS_BY_SOURCE.get(source_id, {})
    found = []
    for item in game.media:
        kind = table.get(item.source_kind, "")
        kind = _moving_form(kind, item.path)
        if kind and kind in known:
            found.append((kind, item.path))
    return found


def _moving_form(kind: str, path: str) -> str:
    """The video kind where the file is one and the source did not say.

    PinballX files a still and a moving one apart, so its folder is the answer. Popper
    puts both in one folder, so the extension is - and a playfield video landing in the
    playfield slot would be a video where an image is expected.
    """
    if kind not in MOVING:
        return kind
    from pathlib import Path as _Path

    return MOVING[kind] if _Path(path).suffix.lower() in VIDEO_SUFFIXES else kind


def unmapped_kinds(source_id: str, game: SourceGame, known: tuple[str, ...]) -> list[str]:
    """What the source held that we have nowhere to put, so it can be said out loud."""
    table = KINDS_BY_SOURCE.get(source_id, {})
    return sorted({item.source_kind for item in game.media
                   if _moving_form(table.get(item.source_kind, ""), item.path)
                   not in known})


def folder_name(game: SourceGame) -> str:
    """What to call the game folder.

    What the source shows a person, where it has one: PinballX's is already
    "Title (Manufacturer Year)", which is our own convention arrived at independently, and
    taking it whole keeps a converted library recognizable to whoever converted it.

    Where the source has no display name of its own it is built the way our own import
    builds one, out of the machine's name and what is known about it. The filename stem is
    the last resort, and only because something has to be.
    """
    if game.display_name.strip():
        return game.display_name.strip()

    title = game.title.strip()
    if not title:
        return game.key.strip()
    maker, year = game.manufacturer.strip(), game.year.strip()
    if maker and year:
        return f"{title} ({maker} {year})"
    if maker or year:
        return f"{title} ({maker or year})"
    return title


def _title_from(game: SourceGame, text: str = "") -> str:
    """The machine's name, out of a string that carries more than it.

    PinballX has no title of its own - it holds "Attack from Mars (Bally 1995)" and
    nothing else - so an import that carried it straight across would put the
    manufacturer and the year in the name column beside the columns that already hold
    them, on every imported game and on none of the matched ones.

    Only where the trailing bracket is exactly the manufacturer and year the source also
    gave, so this is a removal of something known rather than a guess at what a name
    ends with. Anything else is left whole.
    """
    described = (text or game.display_name or "").strip()
    maker, year = game.manufacturer.strip(), game.year.strip()
    if not described or not maker or not year:
        return ""
    suffix = f"({maker} {year})"
    if described.endswith(suffix):
        return described[:-len(suffix)].strip()
    return ""


def details_for(game: SourceGame) -> dict:
    """What the source knew about the machine, in our field names.

    Only what it actually said. Sending a field the source left blank would write an
    empty value over nothing, which reads the same on disk but says we examined it and
    found none - and for an unmatched import nobody examined anything.
    """
    found = {
        # Stripped whichever it came from. A source's own title field is not
        # necessarily a bare title: Popper's is usually the whole
        # "Title (Manufacturer Year)" and is sometimes only the title, in one database.
        "title": _title_from(game, game.title) or game.title or _title_from(game),
        "manufacturer": game.manufacturer,
        "year": game.year,
        "type": game.game_type,
        "ipdb_id": game.ipdb_id,
    }
    said = {name: value for name, value in found.items() if str(value or "").strip()}
    if game.themes:
        said["themes"] = list(game.themes)
    return said
