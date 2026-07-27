from __future__ import annotations

import os
import shutil
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path

from managerui.paths import get_tables_path
from managerui.services.export_bundle import bundle_paths, prune_info


@dataclass(frozen=True)
class VpxzArchive:
    path: str
    temp_dir: str
    filename: str


def resolve_table_dir(table_dir_name: str, tables_path: str | None = None) -> Path:
    """Resolve a table directory name under the configured table root."""
    root = Path(tables_path or get_tables_path()).expanduser().resolve()
    table_dir = (root / table_dir_name).resolve()

    try:
        table_dir.relative_to(root)
    except ValueError as exc:
        raise ValueError("Invalid table path") from exc

    if not table_dir.is_dir():
        raise FileNotFoundError("Table not found")

    return table_dir


def create_vpxz_archive(table_dir_name: str, tables_path: str | None = None, *,
                        everything: bool = False,
                        game_file: str | None = None) -> VpxzArchive:
    """Create a temporary .vpxz archive for a table.

    Default is the standalone bundle for one game file - export a game, not a
    folder. `everything=True` archives the whole directory. Either way the
    layout is folder-wrapped, which is what the mobile importers expect, and
    the shipped .info describes only what the archive actually holds.
    """
    root = Path(tables_path or get_tables_path()).expanduser().resolve()
    table_dir = resolve_table_dir(table_dir_name, str(root))

    tmp_dir = tempfile.mkdtemp()
    vpxz_path = os.path.join(tmp_dir, f"{table_dir.name}.vpxz")

    contents = list(bundle_paths(table_dir, everything=everything, game_file=game_file))
    bundled_names = {Path(arcname).name for _, arcname in contents}
    info_name = f"{table_dir.name}.info"

    with zipfile.ZipFile(vpxz_path, "w", zipfile.ZIP_DEFLATED) as archive:
        for path, arcname in contents:
            member = f"{table_dir.name}/{arcname}"
            if arcname == info_name:
                archive.writestr(member, prune_info(
                    path.read_text(encoding="utf-8", errors="replace"), bundled_names))
            else:
                archive.write(path, member)

    return VpxzArchive(path=vpxz_path, temp_dir=tmp_dir, filename=f"{table_dir.name}.vpxz")


def cleanup_archive(archive: VpxzArchive) -> None:
    shutil.rmtree(archive.temp_dir, ignore_errors=True)
