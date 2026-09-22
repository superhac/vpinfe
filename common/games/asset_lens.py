"""Every asset file in the library, as its own lens on it.

The same shape as the media lens and for the same reason: a row is a file, or the absence
of one, because that is what a gap is countable in and what a bulk action can be handed.

What differs is the resolution. Five kinds are found by VPX's own naming rule, so a file
named for a table beats a file named for the folder - and two of those five take no
folder-named fallback at all, which makes a folder-named `.vbs` or `.pov` a file nothing
will ever load. The rest belong to the folder and have no per-table answer.

Media is not here and assets are not there. The two lenses answer different questions, and
a matrix that mixes them is neither.
"""

from __future__ import annotations

import codecs
import logging
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from common import collation, media_probe, service_errors
from common.games import asset_origin, asset_resolver, game_lens, game_repository, table_lens
from common.games.asset_registry import spec_for
from common.games.game_repository import game_to_row
from common.games.tables import table_names
from common.i18n import t

logger = logging.getLogger("vpinfe.common.games.asset_lens")


# Kinds the folder holds as a whole, with no per-table naming. Not the registry's list:
# `rom` is a declared dependency whose `installed` is true-or-unknown by design, so a row
# calling it missing would call every EM table broken.
_FOLDER_KINDS = ("pup_pack", "alt_color", "alt_sound", "music")

# A row with no file still carries every field one with a file does, so nothing reading
# these has to ask which shape it got.
_ABSENT = {"binding": "none", "present": False, "table": "", "table_file": "",
           "file": None, "path": None, "origin": None, "matched_to": None,
           "serves": None}

_BY_BINDING = {asset_resolver.BINDING_DEDICATED: "table",
               asset_resolver.BINDING_SHARED: "game",
               asset_resolver.BINDING_ORPHANED: "orphaned"}


def _label(kind: str) -> str:
    try:
        return spec_for(kind).label
    except Exception:
        return kind.replace("_", " ").title()


def _row(game_id: str, row: dict, kind: str) -> dict:
    return {"game_id": game_id, "game": str(row.get("name") or ""),
            "manufacturer": str(row.get("manufacturer") or ""),
            "year": str(row.get("year") or ""),
            "kind": kind, "label": _label(kind),
            "label_key": f"asset.kind.{kind}.label",
            "vps_id": str(row.get("vpsid") or "")}


def _folder_state(kind: str, game_dir: Path, subdirs: list[str]) -> str:
    """Where this kind lives in the folder, or "" for not here.

    The same tests the game resource makes, so the two lenses cannot disagree about one
    folder. These kinds are directories rather than files, and the path is what the row
    shows: naming the kind again would be a column repeating its neighbour.
    """
    names = {name.lower(): name for name in subdirs}
    if kind == "pup_pack":
        return names.get("pupvideos", "")
    if kind == "alt_color":
        return next((names[key] for key in ("serum", "vni") if key in names), "")
    if kind == "alt_sound":
        return "pinmame/altsound" if (game_dir / "pinmame" / "altsound").is_dir() else ""
    if kind == "music":
        return names.get("music", "")
    return ""


def _held(item: dict, kind: str, base: dict, game_dir: Path, tables: list[dict],
          by_filename: dict, recorded: dict, hosts: dict, fallback: bool) -> dict:
    """One file that is here: whose it is, and what is recorded about it."""
    path = game_dir / item["file"]
    owner = by_filename.get(str(item.get("table") or ""), {})
    binding = _BY_BINDING.get(item["binding"], item["binding"])
    # A folder-named file for a kind VPX resolves stem-only serves no table at all. It
    # reads as shared because of its name and is inert in fact, so the count says so.
    serves = (len(tables) if binding == "game" and fallback
              else 0 if binding in ("game", "orphaned") else 1)
    # An orphan names a table that is not here, so the inventory has no table to give
    # it. The stem is the name it was written for, which is the whole of what makes the
    # row actionable: it says which build went away.
    named_for = (str(item.get("table") or "")
                 or (Path(item["file"]).stem if binding == "orphaned" else ""))
    return {**base,
            "id": f"{base['game_id']}:{kind}:{item['file']}",
            "table": str(owner.get("id") or ""),
            "table_file": named_for,
            "binding": binding,
            "present": True,
            "serves": serves,
            "file": item["file"],
            "path": asset_origin.path_of(game_dir, path) or None,
            "origin": asset_origin.origin_of(hosts, game_dir, path) or None,
            "matched_to": asset_origin.match_of(recorded, game_dir, path) or None}


def listing(limit: int = 0, offset: int = 0, game: str = "",
            kind: str = "") -> dict[str, Any]:
    """One row per asset file the library holds, plus one per file it does not.

    A file named for a table gets its own row. A file named for nothing - the residue of
    a table that was renamed or deleted - gets one too, and says so: it is the thing an
    audit of a folder wants to see, and nothing has ever shown it.
    """
    kinds = [item.key for item in asset_resolver.VPX_ASSET_KINDS]
    folder_kinds = list(_FOLDER_KINDS)
    if kind:
        kinds = [item for item in kinds if item == kind]
        folder_kinds = [item for item in folder_kinds if item == kind]
    fallback = {item.key: item.folder_fallback for item in asset_resolver.VPX_ASSET_KINDS}

    found: list[dict] = []
    for game_id, entry in game_repository.catalog().items():
        if game and game != game_id:
            continue
        row = game_to_row(entry)
        game_dir = Path(entry.full_path_game or "")
        try:
            files, subdirs = asset_resolver.folder_listing(game_dir)
        except OSError:
            logger.warning("assets: cannot read %s", game_dir)
            continue

        tables = [table for table in table_lens.table_rows(entry, row) if table.get("id")]
        by_filename = {str(table.get("filename") or ""): table for table in tables}
        inventory = asset_resolver.inventory(game_dir.name, files, table_names(files))
        recorded = asset_origin.sources(game_dir)
        hosts = {key: str(source.get("host", "") or "").strip()
                 for key, source in recorded.items()
                 if str(source.get("host", "") or "").strip()}

        for name in kinds:
            base = _row(game_id, row, name)
            held = (inventory.get(name) or {}).get("files") or []
            shared = [item for item in held
                      if item["binding"] == asset_resolver.BINDING_SHARED]
            others = [item for item in held
                      if item["binding"] != asset_resolver.BINDING_SHARED]
            if shared:
                found.extend(_held(item, name, base, game_dir, tables, by_filename,
                                   recorded, hosts, fallback[name])
                             for item in shared)
            else:
                dedicated = sum(1 for item in others
                                if item["binding"] == asset_resolver.BINDING_DEDICATED)
                serves = len(tables) - dedicated
                # No row where nothing would use one. A folder whose every table has a
                # file of its own is not missing the shared file, and reporting it as a
                # gap would be the same invention as an empty per-table row.
                if serves > 0:
                    found.append({**base, **_ABSENT, "id": f"{game_id}:{name}:"})
            found.extend(_held(item, name, base, game_dir, tables, by_filename,
                               recorded, hosts, fallback[name])
                         for item in others)

        for name in folder_kinds:
            here = _folder_state(name, game_dir, subdirs)
            found.append({**_row(game_id, row, name), **_ABSENT,
                          "id": f"{game_id}:{name}:",
                          "binding": "game" if here else "none", "present": bool(here),
                          "file": here or None, "path": here or None,
                          "serves": len(tables) if here else None})

    found.sort(key=lambda item: (collation.sort_key(item["game"]),
                                 collation.sort_key(item["label"]),
                                 collation.sort_key(str(item.get("table_file") or ""))))
    total = len(found)
    window = found[offset:offset + limit] if limit else found[offset:]
    return {"total": total, "offset": offset, "count": len(window), "assets": window}


# Files read as text for their first lines. A backglass is XML too, and is left out: its
# lines are embedded pictures.
_TEXT = frozenset({".vbs", ".ini", ".pov", ".txt", ".md", ".nfo", ".cfg"})
HEAD_LINES = 40
# Enough for a whole script, and a bound on what one request can make this read.
_ALL_LINES_BYTES = 4 * 1024 * 1024


def _stamp(seconds: float) -> str:
    return datetime.fromtimestamp(seconds, tz=UTC).isoformat()


def _inside(game_dir: Path, path: str) -> Path:
    root = game_dir.resolve()
    target = (root / path).resolve()
    if not path.strip() or target != root and root not in target.parents:
        raise service_errors.RefusedError(t("error.assets.outside_folder"),
                                          details={"path": path})
    return target


def _head(path: Path, lines: int) -> str:
    """The first `lines` lines, or all of them for 0. UTF-8 where it is, and otherwise
    the Windows code page most scripts were written in."""
    with path.open("rb") as handle:
        data = handle.read(_ALL_LINES_BYTES if lines == 0 else 256 * max(lines, 1))
    try:
        text = codecs.getincrementaldecoder("utf-8")().decode(data, final=False)
    except UnicodeDecodeError:
        text = data.decode("cp1252", errors="replace")
    kept = text.lstrip("\ufeff").splitlines()
    return "\n".join(kept if lines == 0 else kept[:lines])


def file_detail(game_id: str, path: str, lines: int = HEAD_LINES) -> dict[str, Any]:
    """One asset file or folder, by the path the listing gives it."""
    game = game_lens.game_or_refuse(game_id)
    game_dir = Path(game.full_path_game or "")
    target = _inside(game_dir, path)
    shown = {"path": target.relative_to(game_dir.resolve()).as_posix(), "file": target.name,
             "folder": False, "files": None, "size_bytes": None, "modified": None,
             "format": None, "head": None}
    if target.is_dir():
        count, total, newest = 0, 0, 0.0
        for root, _dirs, names in os.walk(target):
            for name in names:
                try:
                    stat = (Path(root) / name).stat()
                except OSError:
                    continue
                count, total = count + 1, total + stat.st_size
                newest = max(newest, stat.st_mtime)
        return {**shown, "folder": True, "files": count, "size_bytes": total,
                "modified": _stamp(newest) if count else None}
    try:
        stat = target.stat()
    except OSError:
        raise service_errors.NotFoundError(t("error.assets.no_such_file", path=path),
                                           details={"path": path}) from None
    return {**shown, "size_bytes": stat.st_size, "modified": _stamp(stat.st_mtime),
            "format": media_probe.probe(target)["format"],
            "head": _head(target, lines) if target.suffix.lower() in _TEXT else None}
