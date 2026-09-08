"""Building a game library to test against, once.

Thirty-six `setUp` methods opened a temporary directory and registered its cleanup, and
thirteen files wrote a `.info` by hand - so the shape of a game folder was encoded
independently in thirteen places, and a change to it had to be found in all of them.

Two things here. `TempTree` is the setUp; `write_game` is the folder. Neither hides
anything a test needs to be explicit about: what a test cares about it still passes in,
and what it does not care about has one definition instead of thirteen.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace


class TempTree(unittest.TestCase):
    """A test case with `self.root`, a temporary directory cleaned up afterwards."""

    def setUp(self) -> None:
        super().setUp()
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)


def write_game(root: Path | str, name: str = "Example", *,
               info: dict | None = None,
               vpx: bool = True,
               medias: dict[str, bytes] | None = None,
               files: dict[str, bytes] | None = None) -> Path:
    """One game folder: a `.vpx`, its `.info`, and whatever media it needs.

    `info` is written as given, so a test that cares about the metadata says exactly
    what it wants; omit it for a folder with none, which is its own case. `medias` go
    under `medias/`, `files` anywhere under the folder - the two tiers media resolution
    reads, plus whatever else a game carries.
    """
    folder = Path(root) / name
    folder.mkdir(parents=True, exist_ok=True)
    if vpx:
        (folder / f"{name}.vpx").write_bytes(b"not really a vpx")
    if info is not None:
        (folder / f"{name}.info").write_text(json.dumps(info), encoding="utf-8")
    for rel, data in (files or {}).items():
        target = folder / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    for rel, data in (medias or {}).items():
        target = folder / "medias" / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    return folder


def game_info(title: str = "Example", *, vps_id: str = "vps-1", game_id: str = "",
              tables: dict | None = None, **sections) -> dict:
    """A `.info` at schema 2, with only the parts a test names filled in."""
    info: dict = {"Info": {"Title": title, "VPSId": vps_id}, "vpinfe": {"schema": 2}}
    if game_id:
        info["vpinfe"]["game_id"] = game_id
    if tables is not None:
        info["tables"] = tables
    for section, values in sections.items():
        info.setdefault(section, {}).update(values)
    return info


def fake_game(folder: Path | str, name: str = "Example", *,
              meta: dict | None = None, **extra) -> SimpleNamespace:
    """What `GameParser` hands the rest of the app, without parsing anything.

    Thirteen files built this by hand, so the attribute names a consumer reads were
    written out thirteen times and a rename had to find all of them. Anything a test
    needs beyond the four common attributes it passes as `extra`, which is also how the
    optional `*Exists` flags and image paths get set.
    """
    game = SimpleNamespace(
        fullPathGame=str(folder),
        fullPathVPXfile=str(Path(folder) / f"{name}.vpx"),
        gameDirName=name,
        meta_config=meta if meta is not None else {},
    )
    for key, value in extra.items():
        setattr(game, key, value)
    return game
