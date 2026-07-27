"""What belongs in a table export - one answer for every transport.

The VPXZ download and the mobile Web Send are the same operation with different
plumbing, and both used to ship the entire folder: every alternate build, all
media, everything. The default is now a standalone bundle for one game file -
export a game, not a folder - which also makes multi-.vpx folders come out
right. `everything=True` keeps the full-folder behavior as the explicit choice.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

from common.tables.game_files import default_game_file, game_file_names
from managerui.services.asset_registry import (
    is_readme,  # noqa: F401  (one matcher, import and export)
)

# Directories a running game reads, whole. Media is browsing artwork, not part
# of playing the game, so medias/ is deliberately absent.
BUNDLE_DIRS = ("pinmame", "music", "serum", "vni", "altsound", "pupvideos")

# Stem-matched companions of the chosen game file, per the engine's own lookup.
COMPANION_EXTENSIONS = (".ini", ".vbs", ".directb2s", ".pov", ".scv")



def choose_game_file(table_dir: Path, game_file: str | None = None) -> str | None:
    """The bundle's game file: the caller's pick, else the table's default."""
    try:
        listing = [entry.name for entry in table_dir.iterdir() if entry.is_file()]
    except OSError:
        return None
    names = game_file_names(listing)
    if game_file:
        return game_file if game_file in names else None

    recorded = ""
    info_path = table_dir / f"{table_dir.name}.info"
    try:
        recorded = (json.loads(info_path.read_text(encoding="utf-8"))
                    .get("VPXFile", {}) or {}).get("filename", "") or ""
    except (OSError, ValueError):
        pass
    return default_game_file(listing, table_dir.name, recorded) or (names[0] if names else None)


def prune_info(info_text: str, bundled_names: set[str]) -> str:
    """The .info that ships: Medias entries only for files actually in the bundle.

    The manifest should describe the archive, in both modes. Everything else in
    the file - authors, VPS identity, user data - passes through untouched.
    """
    try:
        data = json.loads(info_text)
    except ValueError:
        return info_text
    medias = data.get("Medias")
    if isinstance(medias, dict):
        data["Medias"] = {
            kind: entry for kind, entry in medias.items()
            if isinstance(entry, dict)
            and Path(str(entry.get("Path", ""))).name in bundled_names
        }
    return json.dumps(data, indent=2)


def bundle_paths(table_dir: Path, *, everything: bool = False,
                 game_file: str | None = None) -> Iterator[tuple[Path, str]]:
    """(absolute path, folder-relative arcname) for everything the export holds.

    The .info is included here by name; writers call prune_info on its content
    rather than copying the file raw.
    """
    if everything:
        for path in sorted(table_dir.rglob("*")):
            if path.is_file():
                yield path, str(path.relative_to(table_dir))
        return

    chosen = choose_game_file(table_dir, game_file)
    stem = Path(chosen).stem.lower() if chosen else None
    folder_stem = table_dir.name.lower()

    try:
        entries = sorted(table_dir.iterdir())
    except OSError:
        return
    for entry in entries:
        name = entry.name
        if entry.is_dir():
            if name.lower() in BUNDLE_DIRS:
                for path in sorted(entry.rglob("*")):
                    if path.is_file():
                        yield path, str(path.relative_to(table_dir))
            continue

        lower = name.lower()
        if chosen and name == chosen:
            yield entry, name
        elif lower == f"{folder_stem}.info":
            yield entry, name
        elif is_readme(name):
            yield entry, name
        elif lower.endswith(COMPANION_EXTENSIONS):
            companion_stem = Path(name).stem.lower()
            # The chosen build's own companions, and the folder-named shared
            # fallbacks the engine would resolve for it.
            if companion_stem in (stem, folder_stem):
                yield entry, name
