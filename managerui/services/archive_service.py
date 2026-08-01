from __future__ import annotations

import os
import shutil
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path

from managerui.paths import get_games_path
from managerui.services.export_bundle import bundle_paths, prune_info


@dataclass(frozen=True)
class VpxzArchive:
    path: str
    temp_dir: str
    filename: str


def resolve_game_dir(game_dir_name: str, games_path: str | None = None) -> Path:
    """Resolve a table directory name under the configured table root."""
    root = Path(games_path or get_games_path()).expanduser().resolve()
    game_dir = (root / game_dir_name).resolve()

    try:
        game_dir.relative_to(root)
    except ValueError as exc:
        raise ValueError("Invalid table path") from exc

    if not game_dir.is_dir():
        raise FileNotFoundError("Table not found")

    return game_dir


def create_vpxz_archive(game_dir_name: str, games_path: str | None = None, *,
                        everything: bool = False,
                        game_file: str | None = None) -> VpxzArchive:
    """Create a temporary .vpxz archive for a table.

    Default is the standalone bundle for one game file - export a game, not a
    folder. `everything=True` archives the whole directory. Either way the
    layout is folder-wrapped, which is what the mobile importers expect, and
    the shipped .info describes only what the archive actually holds.
    """
    root = Path(games_path or get_games_path()).expanduser().resolve()
    game_dir = resolve_game_dir(game_dir_name, str(root))

    tmp_dir = tempfile.mkdtemp()
    vpxz_path = os.path.join(tmp_dir, f"{game_dir.name}.vpxz")

    contents = list(bundle_paths(game_dir, everything=everything, game_file=game_file))
    # Forward slashes: an arcname carries the OS separator, an assets key never does.
    bundled_arcnames = {str(arcname).replace(os.sep, "/") for _, arcname in contents}
    info_name = f"{game_dir.name}.info"

    with zipfile.ZipFile(vpxz_path, "w", zipfile.ZIP_DEFLATED) as archive:
        for path, arcname in contents:
            member = f"{game_dir.name}/{arcname}"
            if arcname == info_name:
                archive.writestr(member, prune_info(
                    path.read_text(encoding="utf-8", errors="replace"), bundled_arcnames))
            else:
                archive.write(path, member)

    return VpxzArchive(path=vpxz_path, temp_dir=tmp_dir, filename=f"{game_dir.name}.vpxz")


def cleanup_archive(archive: VpxzArchive) -> None:
    shutil.rmtree(archive.temp_dir, ignore_errors=True)
