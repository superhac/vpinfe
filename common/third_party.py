"""Finding and loading the third-party libraries the app ships with.

DOF and libdmdutil are not packaged as Python dependencies - they are dropped into
`third-party/` by the build and imported from a path at runtime, so where they live
depends on whether this is a source checkout or a frozen build. Nothing here is
specific to them; the extension host will want the same primitives.
"""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path
from types import ModuleType

from common.paths import APP_ROOT


def find_named_path(base: Path, names: tuple[str, ...]) -> Path | None:
    if base.is_file() and base.name in names:
        return base
    if not base.exists() or not base.is_dir():
        return None

    for name in names:
        direct = base / name
        if direct.exists():
            return direct

    for name in names:
        hits = sorted(base.rglob(name))
        if hits:
            return hits[0]
    return None


def third_party_base_candidates(env_var: str, package_dir: str) -> list[Path]:
    env_override = os.environ.get(env_var, "").strip()
    candidates: list[Path] = []
    if env_override:
        candidates.append(Path(env_override).expanduser())

    candidates.append(APP_ROOT / "third-party" / package_dir)

    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates.append(Path(meipass) / "third-party" / package_dir)

    exe_dir = Path(sys.executable).resolve().parent
    candidates.append(exe_dir / "third-party" / package_dir)
    candidates.append(exe_dir.parent / "Resources" / "third-party" / package_dir)

    return candidates


def import_module_from_path(path: Path, module_prefix: str = "_vpinfe") -> ModuleType:
    module_name = f"{module_prefix}_{path.stem}"
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Failed to load module spec from: {path}")

    module = importlib.util.module_from_spec(spec)
    module_dir = str(path.parent)
    restore_path = False
    if module_dir not in sys.path:
        sys.path.insert(0, module_dir)
        restore_path = True
    try:
        spec.loader.exec_module(module)
    finally:
        if restore_path:
            try:
                sys.path.remove(module_dir)
            except ValueError:
                pass
    return module
