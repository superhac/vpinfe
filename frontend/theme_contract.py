"""What a theme was written against, and how to serve it.

A theme declares the oldest VPinFE it runs on - `min_vpinfe` in its manifest.json - and
the contract follows from that; absent means the oldest, which is every theme written
before this existed. The payload is always built in the current shape and projected
backwards, never the reverse - the newest shape is the one that is true.

Adding a field, a media kind or a method does not bump the contract: those are visible
at every level and a theme feature-detects them. Only removing or reshaping something a
theme already reads does. That is what keeps a bump rare.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from common.deprecations import announce
from common.games.game_metadata import DETECTION_KEYS, default_table
from common.values import parse_version

logger = logging.getLogger("vpinfe.frontend.theme_contract")

CURRENT_CONTRACT = 2
OLDEST_CONTRACT = 1
MIN_VERSION_KEY = "min_vpinfe"

# The VPinFE version each contract arrived in, newest first. A theme states the oldest
# build it runs on and gets the newest contract that build already served. Contract 1
# has no entry: it is what a theme gets for saying nothing.
_CONTRACT_SINCE = ((2, (3, 0)),)

# What contract 1 calls each table field. The .info renamed these; a theme written
# against 2.x still reads the old spelling, so the projection restores it.
_LEGACY_TABLE_KEYS = {
    "file_hash": "filehash",
    "vbs_hash": "vbsHash",
    "release_date": "releaseDate",
    "save_date": "saveDate",
    "save_rev": "saveRev",
    "detect_nfozzy": "detectnfozzy",
    "detect_fleep": "detectfleep",
    "detect_ssf": "detectssf",
    "detect_lut": "detectlut",
    "detect_scorbit": "detectscorebit",
    "detect_fastflips": "detectfastflips",
    "detect_flex": "detectflex",
    "detect_pinmame": "detectpinmame",
}

# What contract 1 calls each key in the section VPinFE owns. The .info moved these to
# snake_case; the projection restores the spellings a 2.x theme could be reading, the
# same way _LEGACY_TABLE_KEYS does for VPXFile. Keys 3.0 added have no 2.x name and are
# passed through - the gate allows additions, never removals.
_LEGACY_VPINFE_KEYS = {
    "delete_nvram_on_close": "deletedNVRamOnClose",
    "alt_launcher": "altlauncher",
    "plugin_profile": "pluginprofile",
    "alt_title": "alttitle",
    "alt_vpsid": "altvpsid",
}

# What contract 1 calls each top-level row key. These are served identically at both
# contracts until now, so the projection never had to touch anything outside meta.
_LEGACY_ROW_KEYS = {
    "PlayfieldImagePath": "TableImagePath",
    "PlayfieldVideoPath": "TableVideoPath",
    "fullPathGame": "fullPathTable",
    "gameDirName": "tableDirName",
}

# 1  the shape 2.x themes read: meta.VPXFile, and Rom and Authors on meta.Info
# 2  the .info's own shape: meta.tables, meta.vpinfe, and neither of those on Info


def declared_contract(theme_dir) -> int:
    """The contract a theme's declared minimum version implies, clamped to this build.

    Whether that minimum is newer than the build running is answered at install, not
    here - this is reached only once a theme is on disk and being served.
    """
    manifest = Path(theme_dir) / "manifest.json"
    try:
        manifest_data = json.loads(manifest.read_text(encoding="utf-8"))
        minimum = parse_version(manifest_data.get(MIN_VERSION_KEY))
    except (OSError, ValueError, TypeError, AttributeError):
        return OLDEST_CONTRACT

    level = OLDEST_CONTRACT
    for contract, since in _CONTRACT_SINCE:
        if minimum >= since:
            level = max(level, contract)
    return min(level, CURRENT_CONTRACT)


def project(row: dict, level: int) -> dict:
    """One table's payload as the given contract expects it."""
    if level >= CURRENT_CONTRACT:
        return row
    announce("theme-payload-keys", f"contract {level}")
    return _to_contract_1(row)


def _to_bool(value) -> bool:
    """A detect flag as a real boolean. A JSON "false" is truthy to anything that reads
    it without care, and the parser has handed back strings before now."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in ("true", "1", "yes", "on")
    return value == 1


def _legacy_table(meta: dict, row: dict) -> dict:
    """The game's default table as VPXFile, plus the addon flags that rode with it."""
    name, entry = default_table(meta)
    vpx = {_LEGACY_TABLE_KEYS.get(key, key): value for key, value in dict(entry).items()}
    vpx["filename"] = name
    for key in DETECTION_KEYS:
        vpx[_LEGACY_TABLE_KEYS.get(key, key)] = _to_bool(entry.get(key, False))
    for flag in ("altSoundExists", "altColorExists", "pupPackExists"):
        vpx[flag] = bool(row.get(flag))
    return vpx


def _to_contract_1(row: dict) -> dict:
    """Contract 1 never sees the sections that replaced what it reads.

    Serving both shapes would let a theme work by accident against fields it never
    declared, which is the failure this exists to prevent.
    """
    meta = dict(row.get("meta") or {})
    vpx = _legacy_table(meta, row)
    meta["VPXFile"] = vpx

    info = dict(meta.get("Info") or {})
    info.setdefault("Rom", vpx.get("rom", ""))
    info.setdefault("Authors", vpx.get("authors", []))
    meta["Info"] = info

    meta["VPinFE"] = {_LEGACY_VPINFE_KEYS.get(key, key): value
                      for key, value in dict(meta.get("vpinfe") or {}).items()}
    for section in ("tables", "vpinfe", "assets"):
        meta.pop(section, None)

    projected = dict(row)
    projected["meta"] = meta
    # Top-level row keys, not meta - the projection did not reach these until the
    # vocabulary rename moved them, because nothing above meta had ever changed.
    for new, old in _LEGACY_ROW_KEYS.items():
        if new in projected:
            projected[old] = projected.pop(new)
    return projected
