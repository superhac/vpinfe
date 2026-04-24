from __future__ import annotations

import os
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

from managerui.paths import get_tables_path


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


def create_vpxz_archive(table_dir_name: str, tables_path: str | None = None) -> VpxzArchive:
    """Create a temporary .vpxz archive for a table directory."""
    root = Path(tables_path or get_tables_path()).expanduser().resolve()
    table_dir = resolve_table_dir(table_dir_name, str(root))

    tmp_dir = tempfile.mkdtemp()
    zip_base = os.path.join(tmp_dir, table_dir.name)
    zip_path = shutil.make_archive(zip_base, "zip", root_dir=str(root), base_dir=table_dir.name)
    vpxz_path = zip_base + ".vpxz"
    os.rename(zip_path, vpxz_path)

    return VpxzArchive(path=vpxz_path, temp_dir=tmp_dir, filename=f"{table_dir.name}.vpxz")


def cleanup_archive(archive: VpxzArchive) -> None:
    shutil.rmtree(archive.temp_dir, ignore_errors=True)
