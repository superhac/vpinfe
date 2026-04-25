import logging
from common.metaconfig import MetaConfig
import os
from pathlib import Path

import requests

from common.http_client import download_file, get_json


logger = logging.getLogger("vpinfe.common.standalonescripts")

class StandaloneScripts:

    hashsUrl = "https://raw.githubusercontent.com/jsm174/vpx-standalone-scripts/refs/heads/master/hashes.json"
    
    def __init__(self, tables, progress_cb=None, auto_run: bool = True):
        self.hashes = None
        self.tables = tables
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
         total = len(self.tables) if self.tables else 0
         current = 0
         for table in self.tables:
             current += 1
             if self.progress_cb and total:
                 try:
                     self.progress_cb(current - 1, total, f"Checking {table.tableDirName}")
                 except Exception:
                     pass
             basepath = table.fullPathTable
             try:
                meta = MetaConfig(basepath+"/"+table.tableDirName+".info")
                vpxFileVBSHash = meta.data['VPXFile']['vbsHash']
                logger.info("Checking %s", table.tableDirName)
                for patch in self.hashes:
                    if patch["sha256"] == vpxFileVBSHash:
                        logger.info("Found a match for %s", table.fullPathVPXfile)
                        if os.path.exists(os.path.splitext(table.fullPathVPXfile)[0] + ".vbs"):
                            logger.info("A .vbs sidecar file already exists for that table. Assuming it is a patch.")
                            try:
                                table_dir = os.path.dirname(table.fullPathVPXfile)
                                meta = MetaConfig(os.path.join(table_dir, table.tableDirName + '.info'))
                                meta.data['VPXFile']['patch_applied'] = 'true'
                                meta.writeConfig()
                            except Exception:
                                pass
                        else:
                            self.downloadPatch(os.path.splitext(table.fullPathVPXfile)[0] + ".vbs", patch["patched"]["url"])
                            # mark the .info file with patch_applied = true
                            try:
                                meta.data['VPXFile']['patch_applied'] = 'true'
                                meta.writeConfig()
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
                table_dir = os.path.dirname(filename)
                info_filename = os.path.basename(table_dir) + '.info'
                meta = MetaConfig(os.path.join(table_dir, info_filename))
                meta.data['VPXFile']['patch_applied'] = 'true'
                meta.writeConfig()
            except Exception:
                pass
        except requests.RequestException as exc:
            logger.warning("Failed to download %s: %s", filename, exc)
