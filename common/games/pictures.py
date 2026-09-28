"""A game's Pictures: what a player took of its screens during play."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PIL import Image
from PIL.PngImagePlugin import PngInfo

from common.atomic_write import staged_for

FOLDER = "pictures"
SUFFIX = ".png"

# PNG text keywords. The first two are the format's own.
SOFTWARE = "Software"
TAKEN = "Creation Time"
TABLE = "VPinFE Table"


def folder_of(game_dir: str | Path) -> Path:
    return Path(game_dir) / FOLDER


def _free(folder: Path, stem: str) -> Path:
    path = folder / f"{stem}{SUFFIX}"
    count = 2
    while path.exists():
        path = folder / f"{stem} {count}{SUFFIX}"
        count += 1
    return path


def keep(image: Image.Image, game_dir: str | Path, *, table_id: str,
         taken: datetime) -> Path:
    """Write `image` into the game's pictures. Raises OSError where the folder cannot be
    written."""
    folder = folder_of(game_dir)
    folder.mkdir(exist_ok=True)
    path = _free(folder, taken.strftime("%Y-%m-%d %H-%M-%S"))
    said = PngInfo()
    said.add_text(SOFTWARE, "VPinFE")
    said.add_text(TAKEN, taken.isoformat(timespec="seconds"))
    if table_id:
        said.add_text(TABLE, table_id)
    with staged_for(path) as staged:
        image.save(staged, "PNG", pnginfo=said)
    return path
