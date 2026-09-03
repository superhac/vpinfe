"""Every asset file in the library, as its own lens on it.

The same shape as `GET /media` and for the same reason: a row is a file, or the absence
of one, because that is what a gap is countable in and what a bulk action can be handed.

What differs is the resolution. Five kinds are found by VPX's own naming rule, so a file
named for a table beats a file named for the folder - and two of those five take no
folder-named fallback at all, which makes a folder-named `.vbs` or `.pov` a file nothing
will ever load. The rest belong to the folder and have no per-table answer.

Media is not here and assets are not there. The two lenses answer different questions,
and a matrix that mixes them is neither.
"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, Query

from common.games import asset_origin, asset_resolver
from common.games.asset_registry import spec_for

from . import models, scopes
from .auth import requires

logger = logging.getLogger("vpinfe.httpapi.assets")

router = APIRouter(prefix="/assets", tags=["assets"])

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


@router.get("", summary="Every asset file in the library",
            dependencies=[requires(scopes.GAMES_READ)])
def list_assets(limit: int = Query(0, ge=0), offset: int = Query(0, ge=0),
                game: str = Query(""), kind: str = Query("")) -> models.AssetSlotList:
    """One row per asset file the library holds, plus one per file it does not.

    A file named for a table gets its own row. A file named for nothing - the residue of
    a table that was renamed or deleted - gets one too, and says so: it is the thing an
    audit of a folder wants to see, and nothing has ever shown it.
    """
    from .games import _catalog, _listing, _tables, game_to_row, table_names

    kinds = [item.key for item in asset_resolver.VPX_ASSET_KINDS]
    folder_kinds = list(_FOLDER_KINDS)
    if kind:
        kinds = [item for item in kinds if item == kind]
        folder_kinds = [item for item in folder_kinds if item == kind]
    fallback = {item.key: item.folder_fallback for item in asset_resolver.VPX_ASSET_KINDS}

    found: list[dict] = []
    for game_id, entry in _catalog().items():
        if game and game != game_id:
            continue
        row = game_to_row(entry)
        game_dir = Path(getattr(entry, "fullPathGame", "") or "")
        try:
            files, subdirs = _listing(game_dir)
        except OSError:
            logger.warning("assets: cannot read %s", game_dir)
            continue

        tables = [table for table in _tables(entry, row) if table.get("id")]
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

    found.sort(key=lambda item: (item["game"].lower(), item["label"].lower(),
                                 str(item.get("table_file") or "")))
    total = len(found)
    window = found[offset:offset + limit] if limit else found[offset:]
    return {"total": total, "offset": offset, "count": len(window), "assets": window}
