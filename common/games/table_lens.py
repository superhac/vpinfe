"""A game's launchable artifacts, described one row per table.

Enumerates what is in the folder rather than trusting the single filename the .info
records, because a game folder can hold several. Every answer here is derived from the
folder and the record - nothing is stored, so nothing here can disagree with them.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from common import apps
from common.games import (
    asset_registry,
    asset_resolver,
    game_repository,
    launchers,
    library_discovery,
    tables,
)
from common.games.game_metadata import (
    table_play_record,
    table_rating,
    table_source,
    vpinfe_section,
)
from common.games.game_repository import game_to_row
from common.games.game_service import find_vps_release
from common.games.info_file import VPINFE_SECTION, MetaConfig
from common.games.tables import (
    TABLE_ID_KEY,
    default_table,
    entry_for_filename,
    hidden_tables,
    is_parsed,
    recorded_default,
    table_names,
)
from common.host import pinmame_catalog

logger = logging.getLogger("vpinfe.common.games.table_lens")


def launcher_of(app_id: str, table_id: str) -> dict:
    """The launcher a table would play with, named for a reader.

    Resolved rather than read off the assignment, because a table naming one that is
    switched off falls back - and what a reader is shown has to be what will happen.
    Empty where the install has none: a name invented here would say a table can be
    played on a machine that cannot play it.
    """
    store = launchers.get_launcher_store()
    found = launchers.launcher_for_entry(app_id, table_id, store.launchers(),
                                         store.mappings())
    return {
        "launcher": found.launcher_id if found else "",
        "launcher_name": found.display_name if found else "",
        # Set here against follows, which is the thing a mask can never show: a reader
        # can see which tables were deliberately pointed somewhere, and therefore what
        # changing the default will and will not move.
        "launcher_set_here": bool(store.mapped(table_id)),
        # Whether the program it runs has settings of its own to offer. `generic` has
        # none - it knows a program and arguments and nothing about what that program
        # stores - so the row that leads to them is simply absent rather than opening
        # onto nothing.
        "launcher_app_configurable": _app_configurable(found),
    }


def _app_configurable(launcher) -> bool:
    if launcher is None:
        return False
    app = apps.get(launcher.app)
    return app is not None and app.config is not None


# What the script was seen to use, named for the thing rather than for the .info key
# it sits under. Scorbit is spelled the way the product is - the Manager UI's
# "Scorebit" label is the typo, not the key.
FEATURE_KEYS = {
    "nfozzy": "detect_nfozzy", "fleep": "detect_fleep", "ssf": "detect_ssf",
    "lut": "detect_lut", "scorbit": "detect_scorbit",
    "fastflips": "detect_fastflips", "flexdmd": "detect_flex",
    "pinmame": "detect_pinmame",
}


def table_overrides(entry: dict, folder: dict) -> dict:
    """One table's overrides, falling back to the folder's for a 2.x library."""
    own = entry.get(VPINFE_SECTION) or {}

    def pick(key, default=""):
        value = own.get(key, folder.get(key, default))
        return default if value in ("", None) else value

    return {
        "alt_launcher": str(pick("alt_launcher")),
        "plugin_profile": str(pick("plugin_profile")),
        "delete_nvram_on_close": bool(pick("delete_nvram_on_close", False)),
    }


def table_settings(game_dir: Path) -> dict:
    """Per-table settings from the folder's .info, or {} when unreadable.

    A folder that cannot be parsed must not make its tables vanish - absent
    settings mean everything is visible, which is what an older library looks like.
    """
    try:
        info = game_dir / f"{game_dir.name}.info"
        if info.is_file():
            return MetaConfig(str(info)).game_file_settings()
    except Exception:  # noqa: BLE001 - settings are advisory; never block the listing
        logger.debug("Could not read table settings for %s", game_dir, exc_info=True)
    return {}


def _named_source(described_entry: dict) -> dict | None:
    """A table's binding with the release named, or None where there is no binding.

    The catalog is already loaded here and the client's alternative is asking for the
    whole release list to resolve one id, so the naming happens on this side.
    """
    source = table_source(described_entry)
    if not source.get("vps_file_id"):
        return source or None
    release = find_vps_release(str(source["vps_file_id"]))
    if release:
        source["version"] = str(release.get("version") or "")
        source["authors"] = [str(name) for name in (release.get("authors") or [])]
    return source


def table_rows(game, row: dict) -> list[dict]:
    """The game's launchable artifacts.

    Enumerates what is actually in the folder rather than trusting the single
    filename recorded in the .info: a game folder can hold several .vpx files.
    Sorted, so the answer does not depend on directory order.

    A table the metadata describes but absent from disk is still reported - a
    table pointing at a missing file is something the caller should see - but the
    default falls to one that exists, since the default is what a caller would launch.
    """
    game_dir = Path(row.get("game_dir", ""))
    described = table_settings(game_dir)

    files, subdirs = asset_resolver.folder_listing(game_dir)
    on_disk = table_names(files)

    # (native key, filename, record). The native key is the filename for something in
    # the folder and `app:key` for something with no file, so one list covers all of
    # them and nothing below has to ask which kind it is holding.
    rows: list[tuple[str, str, dict]] = [
        (name, name, entry_for_filename(described, name)[1]) for name in on_disk]
    seen = {name for name, _f, _e in rows}
    for record in described.values():
        native = tables.entry_native_key(record)
        if not native or native in seen:
            continue
        rows.append((native, tables.entry_filename(record), record))
        seen.add(native)
    if not rows:
        return []

    # Same resolver the launcher and the metadata build use, so all three agree.
    recorded = recorded_default(vpinfe_section(game.meta_config), described)
    default = default_table(files or [f for _n, f, _e in rows if f],
                            game_dir.name, recorded)
    if not default:
        # Nothing with a file. The default is then whichever entry the launch path would
        # pick, which is the one thing this must not disagree with.
        default = tables.entry_native_key(
            tables.default_entry(described, game_dir.name, recorded)[1])
    # Why this one, not only which one. `default_table` falls through a recorded choice,
    # a filename matching the folder, then first alphabetically - which its own docstring
    # calls "deterministic rather than correct". A reader does not care which of the last
    # two happened; they care whether they chose it or we did.
    #
    # "user" only where the recorded choice is what actually won: a recorded name whose
    # table has since gone falls through to a derived pick, and calling that a choice
    # would be a lie.
    default_kind = "user" if recorded and recorded == default else "auto"
    hidden = hidden_tables(described)

    # Dependency context, once per request: the alias map and the rom listing are
    # shared by every table in the folder.
    aliases = asset_resolver.read_alias_map(str(game_dir))
    rom_files = asset_resolver.list_rom_files(str(game_dir))

    # 2.x wrote these three at the folder, when a folder was one file. They are the
    # table's now; a folder value is still read as the fallback, so a library written
    # by 2.x keeps working and the one-table case - which is what 2.x had - is
    # unchanged. Writes only ever land on the table.
    folder_vpinfe = vpinfe_section(game.meta_config)

    def _tristate(value):
        """detect* flags are three-valued: yes, no, and never parsed."""
        if isinstance(value, bool):
            return value
        raw = str(value if value is not None else "").strip().lower()
        return True if raw in ("true", "1") else False if raw in ("false", "0") else None

    entries = []
    for native, name, described_entry in rows:
        keyed = bool(tables.entry_key(described_entry))
        reference = tables.entry_reference(described_entry)
        # A reference names a file, so the file says which app plays it - the same
        # question a filename in the folder answers, asked of a name somewhere else.
        claims = os.path.basename(
            tables.resolved_reference(str(game_dir), reference)) if reference else name
        app_id = (tables.entry_app(described_entry) if keyed
                  else (apps.app_for(claims) or apps.default_app()).id)
        points_at = (tables.resolved_reference(str(game_dir), reference)
                     if reference else "")
        reachable = bool(points_at) and os.path.isfile(points_at)
        plays_it = launcher_of(app_id,
                                str(described_entry.get(TABLE_ID_KEY, "") or ""))
        entry = {
            # The table's own id, the same one the play lens uses. Without it the two
            # lenses describe the same table and a client cannot tell that they do -
            # filenames are not identity, which is why ids were minted in the first place.
            "id": str(described_entry.get(TABLE_ID_KEY, "") or ""),
            # Which program plays it, from the registry rather than assumed. Today
            # every table is Visual Pinball's; the point is that the next one is a
            # registry entry and not a search for where ".vpx" was hard-coded.
            "format": app_id,
            "app": app_id,
            # Named as well as identified: a client showing the bare id would be putting
            # one on screen, and would need a second round trip to avoid it.
            "app_name": apps.app_name(app_id),
            # Contained, referenced or keyed, derived from the record rather than
            # stored, so it can never disagree with it.
            "form": tables.entry_form(described_entry),
            # Where a referenced entry points, as stored and as resolved. Both, because
            # what a person typed and what it comes out as are different facts and a
            # relative path is unreadable without the second.
            "reference": ({"path": reference, "resolved": points_at,
                           "reachable": reachable} if reference else None),
            # What its app knows it by, where the entry has no file of its own. Empty
            # for everything in the folder, which is nearly everything.
            "key": tables.entry_key(described_entry),
            # Which launcher actually plays it, and whether that was chosen here or
            # followed from the default. Resolved rather than read off the assignment,
            # because a table naming one that is switched off falls back - and what a
            # reader is shown has to be what will happen.
            **plays_it,
            "filename": name,
            "version": str(described_entry.get("version", "") or ""),
            "authors": [str(a) for a in (described_entry.get("authors") or [])],
            "file_hash": str(described_entry.get("file_hash", "") or ""),
            "vbs_hash": str(described_entry.get("vbs_hash", "") or ""),
            "release_date": str(described_entry.get("release_date", "") or ""),
            "save_date": str(described_entry.get("save_date", "") or ""),
            "save_rev": str(described_entry.get("save_rev", "") or ""),
            "manufacturer": str(described_entry.get("manufacturer", "") or ""),
            "year": str(described_entry.get("year", "") or ""),
            "type": str(described_entry.get("type", "") or ""),
            # Tri-state throughout: a table nobody has parsed answers null for every
            # feature, which is not the same as answering no to all of them.
            "features": {name: _tristate(described_entry.get(key))
                         for name, key in FEATURE_KEYS.items()},
            "overrides": table_overrides(described_entry, folder_vpinfe),
            # Which upstream release this file is, where anything has established it.
            # Absent on almost every table and that is the honest answer: nothing has
            # looked, which is a different state from having looked and found nothing.
            # Named, not just identified - a client showing the bare id would be putting
            # an id on screen, and would need a second round trip to avoid it.
            "source": _named_source(described_entry),
            "default": native == default,
            # Empty on every table that is not the default: the kind is a fact about
            # the one that is, not a field every row carries a blank for.
            "default_kind": default_kind if native == default else "",
            "hidden": native in hidden or described_entry.get("hidden") is True,
            # The table's own rating, which this lens has to carry as well as the play
            # lens - tables are read here and would otherwise all look unrated.
            "rating": table_rating(described_entry),
            "user": table_play_record(described_entry),
            # A file is there or it is not, wherever it is. A key has nothing here to
            # check it against - only the app can say - so what stands in for it is
            # whether this machine has a launcher that would play it at all.
            "available": (bool(plays_it["launcher"]) if keyed
                          else reachable if reference else name in on_disk),
            "absent_since": library_discovery.absent_since(described_entry) or None,
            # An entry with no file has no stem, so nothing is named after it and only
            # the folder's own media applies. That is the honest answer rather than an
            # empty one: a keyed entry's art is the folder's art.
            "assets": asset_resolver.resolve_for_table(name, game_dir.name, files),
        }
        if keyed:
            # Both come out of reading a file, and there is none. Saying "unknown" here
            # would put a dependency on an entry that cannot carry one.
            chain = None
            flex = None
        elif reference:
            # There is a file, but not here - and both of these are read out of this
            # folder. Answering from the folder would report the game's own roms and
            # FlexDMD for a table that is not in it.
            chain = None
            flex = None
        elif is_parsed(described_entry):
            # Every table carries its own ROM and detect flags, so each one answers
            # for itself. This used to be knowable only for the single file the .info
            # described; the rest returned an honest "unknown".
            chain = asset_resolver.resolve_rom_chain(
                described_entry.get("rom", ""), aliases, rom_files,
                _tristate(described_entry.get("detect_pinmame")))
            if chain["effective"]:
                # PinMAME's own audit, from the library the configured VPX ships.
                # No answer leaves the name-match conclusion standing.
                audit = pinmame_catalog.lookup(
                    launchers.default_value("bin_path"),
                    str(game_dir / "pinmame" / "roms"), chain["effective"])
                asset_resolver.apply_audit(chain, audit)
            flex = asset_resolver.flexdmd_state(
                subdirs, _tristate(described_entry.get("detect_flex")))
        else:
            # Never parsed: added since the last metadata build, and the .info may already
            # carry decisions about it - hidden, or where it came from - without
            # anything having read the file itself.
            chain = {"declared": None, "alias_of": None, "effective": None,
                     "required": None, "catalog": None, "clone_of": None,
                     "audit": None, "installed": None,
                     "reason": "unknown: this table has not been parsed yet"}
            flex = asset_resolver.flexdmd_state(subdirs, None)
        if chain is None:
            entry["dependencies"] = None
        else:
            chain["nvram"] = asset_resolver.nvram_state(str(game_dir),
                                                        chain["effective"])
            entry["dependencies"] = {"pinmame": chain, "flexdmd": flex}
        # One answer to "will this run", from the kinds declared required rather than
        # from the two a client happens to be shown.
        entry["launchable"] = asset_registry.launchable(
            entry["available"], bool((chain or {}).get("declared")),
            (chain or {}).get("installed"))
        entries.append(entry)
    return entries


# -- the library seen by launchable file -------------------------------------------
#
# A game's row cannot tell its tables apart, which is the whole of what this is for. Not a
# replacement for the game lens: identity and shared media are the game's, and saying so
# four times over is worse than saying it once. These are peers.


def launch_apps() -> dict[str, Any]:
    """What can launch something in this library, and which files each one claims.

    Answered rather than left as a constant, because a caller showing an App column
    should read the list rather than carry its own copy of it.
    """
    return {"apps": [{"id": app.id, "name": app.name,
                      "suffixes": list(app.claim.suffixes),
                      "accepts_keys": app.claim.accepts_keys}
                     for app in apps.all_apps()]}


def library_rows(limit: int = 0, offset: int = 0, game: str = "") -> dict[str, Any]:
    """One row per launchable file, each carrying the game it belongs to.

    The game's name and maker ride along rather than being a lookup the caller has to
    make: this list is read to be shown, and a table named only by its filename is the
    thing the games lens already fails at.
    """
    found: list[dict] = []
    for game_id, entry in game_repository.catalog().items():
        if game or "":
            if game != game_id:
                continue
        row = game_to_row(entry)
        meta = getattr(entry, "meta_config", {}) or {}
        declared = meta.get("Info")
        info = declared if isinstance(declared, dict) else {}
        for table in table_rows(entry, row):
            if not table.get("id"):
                continue
            found.append({
                "id": table["id"],
                "game_id": game_id,
                "game": str(info.get("Name", "") or row.get("name", "") or ""),
                "manufacturer": str(info.get("Manufacturer", "") or ""),
                "year": str(info.get("Year", "") or ""),
                "filename": table.get("filename") or "",
                # What names this entry where it has no file, and which of the two it
                # is. A row showing a blank in the file column would read as a fault.
                "form": table.get("form") or "contained",
                "key": table.get("key") or "",
                # As stored, which is what identifies the row. Where it resolves to and
                # whether it is there belong to the panel, not to a grid cell.
                "reference": ((table.get("reference") or {}).get("path") or ""),
                "version": table.get("version") or "",
                "authors": table.get("authors") or [],
                "rating": int(table.get("rating") or 0),
                "features": table.get("features") or {},
                "assets": table.get("assets") or {},
                # The rom this file actually resolves to, alias followed. One of the
                # few things that genuinely differs between two tables of one game.
                "rom": str((table.get("dependencies") or {})
                           .get("pinmame", {}).get("effective", "") or ""),
                "rom_installed": ((table.get("dependencies") or {})
                                  .get("pinmame", {}).get("installed")),
                "launchable": table.get("launchable"),
                "user": table.get("user") or {},
                "default": bool(table.get("default")),
                "default_kind": str(table.get("default_kind") or ""),
                "hidden": bool(table.get("hidden")),
                "available": bool(table.get("available")),
                "absent_since": table.get("absent_since"),
                "app": table.get("app") or "",
                "app_name": table.get("app_name") or "",
                # The same three the games lens carries, so the two cannot describe one
                # table differently.
                "launcher": table.get("launcher") or "",
                "launcher_name": table.get("launcher_name") or "",
                "launcher_set_here": bool(table.get("launcher_set_here")),
            })

    found.sort(key=lambda item: (item["game"].lower(),
                                (item["filename"] or item["key"]).lower()))
    total = len(found)
    window = found[offset:offset + limit] if limit else found[offset:]
    return {"total": total, "offset": offset, "count": len(window), "tables": window}
