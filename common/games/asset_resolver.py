"""What a table would use on launch, and what the folder holds for whom.

Two families, split by how the engine finds the thing. An *asset* is resolved by
naming rule - VPX finds it with no help from the script. A *dependency* is declared
by the script and satisfied by content on disk. The rules here mirror VPX's own
lookup code per kind; citations in docs/conventions.md. Everything is computed from
directory listings - nothing here is stored, so nothing here can go stale.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


# Asset kinds resolved by naming rule. `folder_fallback` mirrors VPX: the table's .ini
# and the backglass fall back to a folder-named file; a .pov is stem-only.
@dataclass(frozen=True)
class AssetKind:
    key: str
    extension: str
    folder_fallback: bool


VPX_ASSET_KINDS = (
    AssetKind("backglass", ".directb2s", True),
    AssetKind("settings", ".ini", True),
    AssetKind("script", ".vbs", False),
    AssetKind("pov", ".pov", False),
    AssetKind("scv", ".scv", True),
)

RESOLUTION_DEDICATED = "dedicated"
RESOLUTION_SHARED = "shared"
RESOLUTION_NONE = "none"

BINDING_DEDICATED = "dedicated"
BINDING_SHARED = "shared"
BINDING_ORPHANED = "orphaned"


def _stem(name: str) -> str:
    return os.path.splitext(name)[0]


def _by_lower(names) -> dict[str, str]:
    """lowercase -> actual name. VPX matches companions case-insensitively."""
    return {name.lower(): name for name in names}


def resolve_for_table(table: str, folder_name: str, files,
                          kinds=VPX_ASSET_KINDS) -> dict:
    """The launch lens: what this table would use, kind by kind.

    Mirrors VPX's search order - a file named for the table wins, a file named
    for the folder is the shared fallback, and a kind without a fallback (pov) is
    stem-or-nothing.
    """
    lookup = _by_lower(files)
    stem = _stem(table)
    resolved = {}
    for kind in kinds:
        dedicated = lookup.get((stem + kind.extension).lower())
        if dedicated is not None:
            resolved[kind.key] = {"resolution": RESOLUTION_DEDICATED, "file": dedicated}
            continue
        if kind.folder_fallback:
            shared = lookup.get((folder_name + kind.extension).lower())
            if shared is not None:
                resolved[kind.key] = {"resolution": RESOLUTION_SHARED, "file": shared}
                continue
        resolved[kind.key] = {"resolution": RESOLUTION_NONE}
    return resolved


def inventory(folder_name: str, files, tables, kinds=VPX_ASSET_KINDS) -> dict:
    """The inventory lens: every asset file present, attributed.

    `dedicated` names the table it serves; `shared` is the folder-named
    fallback; `orphaned` is stem-named for a table that is not there - the
    residue of a deleted or renamed table, which is what an audit wants to see.
    """
    stems = {_stem(name).lower(): name for name in tables}
    folder_lower = folder_name.lower()
    result: dict[str, dict] = {kind.key: {"files": []} for kind in kinds}
    for kind in kinds:
        for name in sorted(files):
            if not name.lower().endswith(kind.extension):
                continue
            stem_lower = _stem(name).lower()
            if stem_lower in stems:
                entry = {"file": name, "binding": BINDING_DEDICATED,
                         "table": stems[stem_lower]}
            elif stem_lower == folder_lower:
                entry = {"file": name, "binding": BINDING_SHARED}
            else:
                entry = {"file": name, "binding": BINDING_ORPHANED}
            result[kind.key]["files"].append(entry)
    return result


def parse_alias_file(text: str) -> dict[str, str]:
    """pinmame's alias format: `alias, real` per line, `#` comments.

    Mirrors checkGameAlias in pinmame's Alias.cpp, including its case-insensitive
    match on the alias side.
    """
    aliases: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = [part.strip() for part in line.replace(",", " ").split()]
        if len(parts) >= 2:
            aliases[parts[0].lower()] = parts[1]
    return aliases


def resolve_rom_chain(declared: str, aliases: dict[str, str], rom_files,
                      required: bool | None = None) -> dict:
    """The pinmame dependency chain: declared -> alias -> effective -> installed.

    `required` is whether the script actually drives the emulator - measured from
    the script, not guessed from the name's shape. A declared name with
    required=False is a DOF key; required=True with installed=None is the case a
    doctor should surface. None means the table's metadata predates the detector.

    `installed` is deliberately True-or-None, never False: an unmerged clone set
    can need a parent zip we cannot see the need for, and global rom locations are
    not searched here - so "not found in the table folder" is not "missing".
    """
    declared = (declared or "").strip()
    if not declared:
        return {"declared": None, "alias_of": None, "effective": None,
                "required": required, "catalog": None, "clone_of": None,
                "audit": None, "installed": None, "reason": "no rom declared"}

    real = aliases.get(declared.lower())
    effective = real or declared
    chain = {
        "declared": declared,
        "alias_of": real,
        "effective": effective,
        "required": required,
        "catalog": None,
        "clone_of": None,
        "audit": None,
        "installed": None,
        "reason": None,
    }

    wanted = effective.lower()
    for name in rom_files:
        base, ext = os.path.splitext(name)
        if ext.lower() == ".zip" and base.lower() == wanted:
            chain["installed"] = True
            return chain
    chain["reason"] = "not found in the table's roms folder; global locations not searched"
    return chain


def apply_audit(chain: dict, entry: dict | None) -> dict:
    """Fold PinMAME's own answer into the chain, when there is one.

    The audit outranks the name-match: `found` means the set would actually load,
    chip CRCs and parent zips included, so it is what finally makes
    installed=False sayable. No entry means no answer, and the chain keeps
    whatever the name-match concluded.
    """
    if entry is None:
        chain["audit"] = "unavailable"
        return chain
    if not entry.get("catalog"):
        chain["catalog"] = False
        chain["audit"] = "unknown_set"
        chain["installed"] = None
        chain["reason"] = ("not in this PinMAME's catalog - an alias may be "
                           "needed, or the set is newer than the shipped library")
        return chain
    chain["catalog"] = True
    chain["clone_of"] = entry.get("clone_of")
    chain["description"] = entry.get("description")
    if entry.get("found"):
        chain["audit"] = "ok"
        chain["installed"] = True
        chain["reason"] = None
    else:
        chain["audit"] = "missing"
        chain["installed"] = False
        chain["reason"] = "PinMAME audit: romset missing or incomplete in the table's roms folder"
    return chain


def read_alias_map(game_dir: str) -> dict[str, str]:
    """The per-game alias file, when there is one. Standalone reads
    pinmame/alias.txt; the global VPMAlias.txt is a Windows VPinMAME concern."""
    path = os.path.join(game_dir, "pinmame", "alias.txt")
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            return parse_alias_file(handle.read())
    except OSError:
        return {}


def list_rom_files(game_dir: str) -> list[str]:
    try:
        return os.listdir(os.path.join(game_dir, "pinmame", "roms"))
    except OSError:
        return []


def nvram_state(game_dir: str, effective_rom: str | None) -> dict:
    """Play state keyed by the effective rom, computed per request so
    modified_at is live - a tournament harvester's question is "is there a score
    newer than my last visit", which a scan-time answer cannot serve."""
    if not effective_rom:
        return {"present": False}
    path = os.path.join(game_dir, "pinmame", "nvram", f"{effective_rom}.nv")
    try:
        stat = os.stat(path)
    except OSError:
        return {"present": False}
    return {"present": True, "file": os.path.basename(path),
            "modified_at": int(stat.st_mtime)}


def flexdmd_state(subdirs, detected: bool | None) -> dict:
    """The flexdmd dependency: script-declared project folder, content on disk.

    `declared` stays None until the script extraction exists - the honest
    degradation, same as the rom detector. `installed` reports any .UltraDMD
    content folder in the meantime.
    """
    content = sorted(d for d in subdirs if d.lower().endswith(".ultradmd"))
    return {
        "detected": detected,
        "declared": None,
        "installed": bool(content),
        "content": content,
    }
