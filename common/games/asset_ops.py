"""Putting the files VPX finds by name in a game's folder, and taking one out.

`asset_lens` lists them; this writes.
"""

from __future__ import annotations

import logging
import os
import shutil
import tempfile
from pathlib import Path

from common import service_errors
from common.games import asset_lens, game_lens, media_ops, media_placement, table_lens
from common.games.asset_registry import spec_for
from common.games.asset_resolver import VPX_ASSET_KINDS, AssetKind
from common.games.game import Game
from common.games.game_repository import game_to_row
from common.i18n import t

logger = logging.getLogger("vpinfe.common.games.asset_ops")

_KINDS = {kind.key: kind for kind in VPX_ASSET_KINDS}
_EXTENSIONS = frozenset(kind.extension for kind in VPX_ASSET_KINDS)
# The folders a kind lives in whole, as the asset lens reports them.
_FOLDERS = frozenset({"pupvideos", "serum", "vni", "pinmame/altsound", "music"})


def kind_or_refuse(kind: str) -> AssetKind:
    found = _KINDS.get(str(kind or ""))
    if found is None:
        raise service_errors.RefusedError(
            t("error.assets.unknown_kind"),
            details={"unknown": kind, "known": sorted(_KINDS)})
    return found


def _folder(game: Game) -> Path:
    return Path(game.full_path_game or "")


def _stem(game: Game, kind: AssetKind, table_id: str) -> str:
    """The name a file of this kind takes at this tier: the table's, or the folder's."""
    if table_id:
        return media_ops.stem_or_refuse(game, table_id)
    if not kind.folder_fallback:
        raise service_errors.RefusedError(
            t("error.assets.only_for_a_table", label=spec_for(kind.key).label),
            details={"kind": kind.key})
    return _folder(game).name


def _here(game_dir: Path, name: str) -> list[str]:
    """The file already at this name, matched without case as VPX matches it."""
    wanted = name.lower()
    try:
        return sorted(entry.name for entry in game_dir.iterdir()
                      if entry.is_file() and entry.name.lower() == wanted)
    except OSError:
        return []


def placements(game_id: str, kind: str) -> dict:
    """Every name this kind can take in this folder, with what each would replace."""
    found_kind = kind_or_refuse(kind)
    game = game_lens.game_or_refuse(game_id)
    game_dir = _folder(game)
    found = []
    if found_kind.folder_fallback:
        found.append({"table": "", "label": "", "base": game_dir.name,
                      "displaces": _here(game_dir, game_dir.name + found_kind.extension)})
    for table in table_lens.table_rows(game, game_to_row(game)):
        stem = Path(str(table.get("filename") or "")).stem
        if not table.get("id") or not stem or stem in {item["base"] for item in found}:
            continue
        found.append({"table": table["id"], "label": table["filename"], "base": stem,
                      "displaces": _here(game_dir, stem + found_kind.extension)})
    return {"placements": found, "extensions": [found_kind.extension]}


def _extension_or_refuse(kind: AssetKind, filename: str) -> None:
    if Path(filename).suffix.lower() != kind.extension:
        raise service_errors.RefusedError(
            t("error.assets.wrong_extension", label=spec_for(kind.key).label,
              extension=kind.extension),
            details={"kind": kind.key, "file": filename})


def displaced(game_id: str, kind: str, filename: str, table_id: str = "") -> dict:
    """What placing `filename` at this tier would replace, before the bytes are sent."""
    found_kind = kind_or_refuse(kind)
    _extension_or_refuse(found_kind, filename)
    game = game_lens.game_or_refuse(game_id)
    return {"displaced": _here(_folder(game),
                               _stem(game, found_kind, table_id) + found_kind.extension)}


def place_file(game_id: str, kind: str, table_id: str, source: Path,
               filename: str = "") -> dict:
    """Copy `source` in under this tier's name, replacing what was there.

    `filename` is the name the file arrived with, where `source` is a staging copy whose
    own name says nothing.
    """
    found_kind = kind_or_refuse(kind)
    _extension_or_refuse(found_kind, filename or Path(source).name)
    if not Path(source).is_file():
        raise service_errors.RefusedError(t("error.games.not_file"),
                                          details={"path": str(source)})
    game = game_lens.game_or_refuse(game_id)
    game_dir = _folder(game)
    target = game_dir / (_stem(game, found_kind, table_id) + found_kind.extension)
    going = _here(game_dir, target.name)
    # Written beside the target and renamed over it, so a copy that fails part way
    # leaves the old file rather than half of a new one.
    with tempfile.NamedTemporaryFile(dir=game_dir, prefix=".vpinfe-", suffix=".part",
                                     delete=False) as staged:
        staging = Path(staged.name)
    try:
        shutil.copyfile(source, staging)
        for other in going:
            if other != target.name:
                (game_dir / other).unlink()
        os.replace(staging, target)
    finally:
        staging.unlink(missing_ok=True)
    media_placement.record_origin(game_dir, target)
    return {"written": target.name, "displaced": going}


def remove(game_id: str, path: str) -> dict:
    """Delete one asset file, or one kind's folder, named by its path in the game's
    folder."""
    game = game_lens.game_or_refuse(game_id)
    root = _folder(game).resolve()
    found = asset_lens.inside(root, path)
    if found.is_dir() and found.relative_to(root).as_posix().lower() in _FOLDERS:
        shutil.rmtree(found)
    elif found.suffix.lower() in _EXTENSIONS and found.is_file():
        found.unlink()
    else:
        raise service_errors.RefusedError(t("error.assets.not_an_asset_file"),
                                          details={"path": path})
    return {"removed": [path]}


__all__ = ["displaced", "kind_or_refuse", "place_file", "placements", "remove"]
