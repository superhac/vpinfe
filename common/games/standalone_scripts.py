import logging
import os
from pathlib import Path

import requests

from common.games.info_file import MetaConfig
from common.http_client import download_file, get_json

logger = logging.getLogger("vpinfe.common.games.standalone_scripts")

class StandaloneScripts:

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
                for patch in self.hashes:
                    if patch["sha256"] == vpxFileVBSHash:
                        logger.info("Found a match for %s", game.fullPathVPXfile)
                        if os.path.exists(os.path.splitext(game.fullPathVPXfile)[0] + ".vbs"):
                            logger.info("A .vbs sidecar file already exists for that table. Assuming it is a patch.")
                            try:
                                game_dir = os.path.dirname(game.fullPathVPXfile)
                                meta = MetaConfig(os.path.join(game_dir, game.gameDirName + '.info'))
                                meta.set_table_value(vpxFileName, 'patch_applied', True)
                            except Exception:
                                pass
                        else:
                            self.downloadPatch(os.path.splitext(game.fullPathVPXfile)[0] + ".vbs", patch["patched"]["url"])
                            # mark the .info file with patch_applied = true
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
