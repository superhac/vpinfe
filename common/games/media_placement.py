"""Putting a media file where it will be found, at the tier that was asked for.

The resolution chain has always read three tiers and only ever been able to write the
bottom one - `replace_media_file` writes the fixed name, which is where vpinmediadb
writes. So a user's own art landed in the slot a media refresh owns, and no amount of
resolution work could populate the tiers above it.

The tier is not a setting here. It is which name the file gets: the game's folder name
serves every table, a table's stem serves that build alone. A caller says which by
which thing it addressed, so nobody has to learn what a tier is to use one.

A write reports what it resolved to afterwards, because placing a file is not the same
as winning: a shared file is outranked by any table-specific one, and finding that out
by the art not changing is the worst way to learn it.
"""

from __future__ import annotations

import logging
import os
import shutil
from pathlib import Path

from common.media_specs import MEDIA_SPECS

logger = logging.getLogger("vpinfe.common.games.media_placement")

_SPEC_BY_KIND = {spec.kind: spec for spec in MEDIA_SPECS}

TIER_GAME = "game"
TIER_TABLE = "table"


class UnplaceableError(ValueError):
    """The kind, the tier or the extension is not something we can write."""


def target_name(kind: str, stem: str, extension: str) -> str:
    """The filename that puts this kind at this stem's tier.

    Always the spec token, never an alias: aliases exist so a file someone else named
    still resolves, and writing one would be recommending a spelling we do not.
    """
    spec = _SPEC_BY_KIND.get(kind)
    if spec is None:
        raise UnplaceableError(f"Unknown media kind {kind}")
    if not spec.token:
        raise UnplaceableError(f"{kind} has no spec name, so it can only be a default")
    extension = extension.lower()
    if extension not in spec.family:
        raise UnplaceableError(
            f"{kind} does not accept {extension}; it takes {', '.join(spec.family)}")
    return f"{spec.token} {stem}{extension}"


def place(game_dir: str | Path, kind: str, stem: str, source: str | Path) -> Path:
    """Install `source` as this kind's file for `stem`, and return where it landed.

    Siblings in the same family and at the same tier go: they would otherwise sit
    behind the new file forever, waiting for a family order to change and surface a
    file the user believed replaced.
    """
    game_dir = Path(game_dir)
    source = Path(source)
    name = target_name(kind, stem, source.suffix)
    medias = game_dir / "medias"
    medias.mkdir(parents=True, exist_ok=True)
    target = medias / name

    spec = _SPEC_BY_KIND[kind]
    prefix = f"{spec.token} {stem}"
    for extension in spec.family:
        for folder in (medias, game_dir):
            sibling = folder / f"{prefix}{extension}"
            if sibling != target and sibling.exists():
                try:
                    sibling.unlink()
                except OSError:
                    logger.warning("Could not remove %s", sibling)

    shutil.copy2(source, target)
    return target


def record_origin(game_dir: str | Path, path: Path, host: str = "user") -> None:
    """Note who placed the file, so the surface can say so later."""
    game_dir = Path(game_dir)
    info = game_dir / f"{game_dir.name}.info"
    if not info.is_file():
        return
    try:
        from common.games.info_file import MetaConfig
        MetaConfig(str(info)).add_asset(str(path), host)
    except Exception:
        # The bytes are on disk and resolution never consults the ledger, so a failure
        # here costs provenance, not the file.
        logger.exception("Placed %s but could not record where it came from", path)


def remove(game_dir: str | Path, kind: str, stem: str) -> list[str]:
    """Delete this kind's files at this stem's tier. Never touches another tier."""
    game_dir = Path(game_dir)
    spec = _SPEC_BY_KIND.get(kind)
    if spec is None or not spec.token:
        raise UnplaceableError(f"Cannot address {kind} by name")
    removed = []
    for extension in spec.family:
        for folder in (game_dir / "medias", game_dir):
            path = folder / f"{spec.token} {stem}{extension}"
            if path.exists():
                try:
                    path.unlink()
                    removed.append(os.path.relpath(str(path), str(game_dir)))
                except OSError:
                    logger.warning("Could not remove %s", path)
    return removed
