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


def _family_at_tier(game_dir: Path, kind: str, stem: str):
    """Every file already serving this kind at this stem's tier, whatever its extension.

    Both folders, because a library that predates `medias/` keeps its art beside the
    .vpx and the resolver still reads it.
    """
    spec = _SPEC_BY_KIND[kind]
    prefix = f"{spec.token} {stem}"
    for extension in spec.family:
        for folder in (game_dir / "medias", game_dir):
            sibling = folder / f"{prefix}{extension}"
            if sibling.exists():
                yield sibling


def displaced(game_dir: str | Path, kind: str, stem: str, extension: str) -> list[Path]:
    """The files a `place` of this extension would overwrite or delete.

    Answered without the bytes, so a caller can ask before a large upload starts and
    still say what is about to go. It is not only the file with the same name: the
    whole family at this tier goes, so dropping a .jpg over a .png removes the .png.
    """
    game_dir = Path(game_dir)
    target = game_dir / "medias" / target_name(kind, stem, extension)
    going = set(_family_at_tier(game_dir, kind, stem))
    if target.exists():
        going.add(target)
    return sorted(going)


def place(game_dir: str | Path, kind: str, stem: str, source: str | Path) -> Path:
    """Install `source` as this kind's file for `stem`, and return where it landed.

    Siblings in the same family and at the same tier go: they would otherwise sit
    behind the new file forever, waiting for a family order to change and surface a
    file the user believed replaced. `displaced` reports the same set beforehand.
    """
    game_dir = Path(game_dir)
    source = Path(source)
    name = target_name(kind, stem, source.suffix)
    medias = game_dir / "medias"
    medias.mkdir(parents=True, exist_ok=True)
    target = medias / name

    for sibling in list(_family_at_tier(game_dir, kind, stem)):
        if sibling != target:
            try:
                sibling.unlink()
            except OSError:
                logger.warning("Could not remove %s", sibling)

    shutil.copy2(source, target)
    return target


def retier(game_dir: str | Path, kind: str, from_stem: str, to_stem: str) -> Path:
    """Move a placed file to the other tier by renaming it, keeping its extension.

    The tier is the filename, so changing who a file serves is a rename rather than a
    re-upload. Routed through `place`, so a file arriving at the new tier displaces
    what is there by exactly the rule a drop would.
    """
    game_dir = Path(game_dir)
    sources = sorted(_family_at_tier(game_dir, kind, from_stem))
    if not sources:
        raise UnplaceableError(f"There is no {kind} file named for {from_stem}")

    source = sources[0]
    target = place(game_dir, kind, to_stem, source)
    if source != target:
        try:
            source.unlink()
        except OSError:
            logger.warning("Placed %s but could not remove %s", target, source)
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
                    # Forward-slashed: this list is an API payload, and
                    # `os.path.relpath` answers in the host's separator - so the same
                    # library reported "medias/bg.png" on Linux and "medias\\bg.png"
                    # on Windows. `path` is always built under `game_dir` just above.
                    removed.append(path.relative_to(game_dir).as_posix())
                except OSError:
                    logger.warning("Could not remove %s", path)
    return removed
