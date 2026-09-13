"""The community script patches that make a table run under VPX Standalone."""

import logging
import os
from pathlib import Path

import requests

from common.games.info_file import MetaConfig
from common.http_client import download_file, get_json

logger = logging.getLogger("vpinfe.common.games.standalone_scripts")

# What a table's script is doing about the published fixes. Three states, because
# "patched" and "nothing published for it" are different answers and a surface that
# folded them together would report a table as fine for two unrelated reasons.
OFFERED = "offered"      # a fix exists and this table does not have it yet
ALREADY = "already"      # a .vbs sidecar is beside the table, so it is running one
NOTHING = "nothing"      # nothing published matches this table's script


def match_for(vbs_hash: str, hashes) -> dict | None:
    """The published fix for one table's script, or None.

    Matched on the hash of the script the table actually runs, not on its name: the
    whole point of the index is that one table's script can appear under a dozen
    filenames and a fix is only correct for the bytes it was built against.
    """
    if not vbs_hash:
        return None
    for patch in hashes or ():
        if patch.get("sha256") == vbs_hash:
            return patch
    return None


def state_of(vpx_path: str, vbs_hash: str, hashes) -> tuple[str, dict | None]:
    """What is offered for one table, and what it is already doing.

    A `.vbs` sidecar wins over anything published: the program runs that file in place
    of the script the table ships with, so whatever is there is what the table is
    running, and replacing it would be overwriting somebody's own work.
    """
    found = match_for(vbs_hash, hashes)
    if found is None:
        return NOTHING, None
    if os.path.exists(os.path.splitext(vpx_path)[0] + ".vbs"):
        return ALREADY, found
    return OFFERED, found

class StandaloneScripts:

    """The community script patches, fetched and applied to a table that needs one."""

    hashsUrl = "https://raw.githubusercontent.com/jsm174/vpx-standalone-scripts/refs/heads/master/hashes.json"

    def __init__(self, games, progress_cb=None, auto_run: bool = True):
        self.hashes = None
        self.games = games
        self.progress_cb = progress_cb
        logger.info("VPX-Standalone-Scripts Patching System initialized.")
        if auto_run:
            self.apply_patches()

    def downloadHashes(self):
        try:
            self.hashes = get_json(StandaloneScripts.hashsUrl)
            logger.info("Retrieved hash file from VPX-Standalone-Scripts with %s patched tables.", len(self.hashes))
        except (requests.RequestException, ValueError):
            self.hashes = []
            logger.warning("Failed to download hash file from VPX-Standalone-Scripts")
        return self.hashes

    def download_hashes(self):
        return self.downloadHashes()

    def apply_patches(self):
        self.downloadHashes()
        self.checkForPatches()

    def checkForPatches(self):
         if not self.hashes:
             return
         total = len(self.games) if self.games else 0
         current = 0
         for game in self.games:
             current += 1
             if self.progress_cb and total:
                 try:
                     self.progress_cb(current - 1, total, f"Checking {game.gameDirName}")
                 except Exception:
                     pass
             basepath = game.fullPathGame
             try:
                meta = MetaConfig(basepath+"/"+game.gameDirName+".info")
                vpxFileName = os.path.basename(game.fullPathVPXfile)
                vpxFileVBSHash = meta.game_file_value(vpxFileName, 'vbs_hash')
                if not vpxFileVBSHash:
                    raise KeyError('vbs_hash')
                logger.info("Checking %s", game.gameDirName)
                # One matching rule, shared with what the report offers. Two would be
                # two answers to "does this table need a fix", and the one somebody was
                # shown would not be the one that ran.
                state, patch = state_of(game.fullPathVPXfile, vpxFileVBSHash, self.hashes)
                if state == ALREADY:
                    logger.info("A .vbs sidecar file already exists for that table. Assuming it is a patch.")
                    try:
                        meta.set_table_value(vpxFileName, 'patch_applied', True)
                    except Exception:
                        pass
                elif state == OFFERED:
                    logger.info("Found a match for %s", game.fullPathVPXfile)
                    self.downloadPatch(os.path.splitext(game.fullPathVPXfile)[0] + ".vbs",
                                       patch["patched"]["url"])
                    try:
                        meta.set_table_value(vpxFileName, 'patch_applied', True)
                    except Exception:
                        pass
             except KeyError:
                 pass

    def checkIfVBSFileExists(self, file):
        if file.is_file():
            return True
        else:
            return False

    def downloadPatch(self, filename, url):
        #logger.debug(f"Patched file installed: {filename}")
        try:
            download_file(url, Path(filename), chunk_size=1024)
            logger.info("File downloaded successfully: %s", filename)
            # also set patch_applied in .info if possible (derive from filename)
            try:
                game_dir = os.path.dirname(filename)
                info_filename = os.path.basename(game_dir) + '.info'
                meta = MetaConfig(os.path.join(game_dir, info_filename))
                # The .vbs sits beside the .vpx it patches and shares its stem, so
                # the flag lands on that table rather than on the whole game.
                vpx_name = os.path.splitext(os.path.basename(filename))[0] + '.vpx'
                meta.set_table_value(vpx_name, 'patch_applied', True)
            except Exception:
                pass
        except requests.RequestException as exc:
            logger.warning("Failed to download %s: %s", filename, exc)


def offered_for(games, hashes=None) -> dict:
    """What the published index has for this library, without changing anything.

    Its own pass rather than a flag on the applier, because what a person is deciding is
    whether to let something reach into every game folder and write a file. Being able to
    ask first is the difference between a confirm and a leap.

    `hashes` is fetched when it is not given. An index that cannot be reached is not an
    empty index - the caller is told so rather than being shown a library with nothing
    to do.
    """
    if hashes is None:
        hashes = StandaloneScripts(games=[], auto_run=False).downloadHashes()
    if not hashes:
        return {"reachable": False, "offered": [], "already": 0, "checked": 0}

    offered, already, checked = [], 0, 0
    for game in games or ():
        vpx_path = getattr(game, "fullPathVPXfile", "") or ""
        folder = getattr(game, "fullPathGame", "") or ""
        name = getattr(game, "gameDirName", "") or ""
        if not vpx_path or not name:
            continue
        try:
            meta = MetaConfig(os.path.join(folder, name + ".info"))
            vbs_hash = meta.game_file_value(os.path.basename(vpx_path), "vbs_hash")
        except Exception:
            continue
        if not vbs_hash:
            # Nothing has read this table, so there is no script to match on. Not
            # counted as checked: reporting it as "nothing published" would be a
            # statement about a file nobody has opened.
            continue
        checked += 1
        state, _patch = state_of(vpx_path, vbs_hash, hashes)
        if state == OFFERED:
            offered.append(name)
        elif state == ALREADY:
            already += 1
    return {"reachable": True, "offered": sorted(offered), "already": already,
            "checked": checked}
