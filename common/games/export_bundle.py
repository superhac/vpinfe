"""What belongs in a game export - one answer for every transport.

The VPXZ download and the mobile Web Send are the same operation with different
plumbing, and both used to ship the entire folder: every alternate table, all
media, everything. The default is now a standalone bundle for one table -
export a game, not a folder - which also makes multi-.vpx folders come out
right. `everything=True` keeps the full-folder behavior as the explicit choice.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

from common.games.asset_registry import (
    is_readme,  # noqa: F401  (one matcher, import and export)
)
from common.games.asset_resolver import resolve_for_table
from common.games.game_metadata import vpinfe_section
from common.games.info_file import ASSETS_KEY
from common.games.tables import (
    default_table,
    recorded_default,
    table_entries,
    table_names,
)

# Directories a running game reads, whole. Media is browsing artwork, not part
# of playing the game, so medias/ is deliberately absent.
#
# VPX's list, and the one part of a bundle still named for one engine. The file-level
# question next to it is already app-agnostic - `resolve_for_table` takes its `kinds`
# as a parameter, so its rule (a dedicated file wins, a folder-named one is the shared
# fallback) holds for whatever the launcher is. `VPinFE.altlauncher` already lets a game
# declare a different one. When a second app arrives, this tuple is what moves beside
# `VPX_ASSET_KINDS` into that app's description rather than being extended in place.
BUNDLE_DIRS = ("pinmame", "music", "serum", "vni", "altsound", "pupvideos")

# Stem-matched companions of the chosen table, per the engine's own lookup.
COMPANION_EXTENSIONS = (".ini", ".vbs", ".directb2s", ".pov", ".scv")



def choose_table(game_dir: Path, table: str | None = None) -> str | None:
    """The bundle's table: the caller's pick, else the game's default."""
    try:
        listing = [entry.name for entry in game_dir.iterdir() if entry.is_file()]
    except OSError:
        return None
    names = table_names(listing)
    if table:
        return table if table in names else None

    recorded = ""
    info_path = game_dir / f"{game_dir.name}.info"
    try:
        meta = json.loads(info_path.read_text(encoding="utf-8"))
        recorded = recorded_default(vpinfe_section(meta), table_entries(meta))
    except (OSError, ValueError):
        pass
    return default_table(listing, game_dir.name, recorded) or (names[0] if names else None)


def prune_info(info_text: str, bundled_arcnames: set[str]) -> str:
    """The .info that ships: assets entries only for files actually in the bundle.

    The manifest should describe the archive, in both modes. Everything else in
    the file - authors, VPS identity, user data - passes through untouched.

    Both keys are folder-relative paths, so this is a direct comparison. It used to
    match basenames out of the old Medias `Path` field, which could not tell
    medias/wheel.png from a wheel.png at the folder root.
    """
    try:
        data = json.loads(info_text)
    except ValueError:
        return info_text
    assets = data.get(ASSETS_KEY)
    if isinstance(assets, dict):
        data[ASSETS_KEY] = {
            path: entry for path, entry in assets.items() if path in bundled_arcnames
        }
    return json.dumps(data, indent=2)


def bundle_paths(game_dir: Path, *, everything: bool = False,
                 table: str | None = None) -> Iterator[tuple[Path, str]]:
    """(absolute path, folder-relative arcname) for everything the export holds.

    The .info is included here by name; writers call prune_info on its content
    rather than copying the file raw.
    """
    if everything:
        for path in sorted(game_dir.rglob("*")):
            if path.is_file():
                yield path, str(path.relative_to(game_dir))
        return

    chosen = choose_table(game_dir, table)
    folder_stem = game_dir.name.lower()

    try:
        entries = sorted(game_dir.iterdir())
    except OSError:
        return

    # What VPX would actually open for this table, asked of the resolver rather than
    # matched by hand. Stem-matching here accepted the table's own companion *and* the
    # folder-named fallback, but the resolver takes the dedicated one and stops - so a
    # table with its own .directb2s shipped the shadowed one too. On one real game that
    # was 54MB of 245MB the far side could never load.
    resolved_companions = {
        str(picked["file"]).lower()
        for picked in resolve_for_table(
            chosen or "", game_dir.name,
            [entry.name for entry in entries if entry.is_file()]).values()
        if picked.get("file")
    }
    for entry in entries:
        name = entry.name
        if entry.is_dir():
            if name.lower() in BUNDLE_DIRS:
                for path in sorted(entry.rglob("*")):
                    if path.is_file():
                        yield path, str(path.relative_to(game_dir))
            continue

        lower = name.lower()
        if chosen and name == chosen:
            yield entry, name
        elif lower == f"{folder_stem}.info":
            yield entry, name
        elif is_readme(name):
            yield entry, name
        elif lower in resolved_companions:
            yield entry, name
