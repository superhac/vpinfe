import requests
import metaconfig

#remove
import olefile
import hashlib
import sys
import os

from logger import get_logger

class StandaloneScripts:

    logger = None

    hashsUrl = "https://raw.githubusercontent.com/jsm174/vpx-standalone-scripts/refs/heads/master/hashes.json"
    
    def __init__(self, tables):
        global logger
        logger = get_logger()

        self.hashes = None
        self.tables = tables
        logger.info("VPX-Standalone-Scripts Patching System initialized.")
        self.downloadHashes()
        self.checkForPatches()
        #logger.debug(self.hashes)
        
    def downloadHashes(self):
        response = requests.get(StandaloneScripts.hashsUrl)
        if response.status_code == 200:
            self.hashes = response.json()
            logger.info(f"Retrieved hash file from VPX-Standalone-Scripts with {len(self.hashes)} patched tables.")
        else:
            logger.error('Failed to download hash file from VPX-Standalone-Scripts')
            
        #debug
        #logger.debug(f"{self.hashes[0]["file"]} {self.hashes[0]["sha256"]} {self.hashes[0]["patched"]["file"]}")
      
    def checkForPatches(self):
         for table in self.tables:
             basepath = table.fullPathTable
             try:
                meta = metaconfig.MetaConfig(basepath+"/"+"meta.ini")
                vpxFileVBSHash = meta.config['VPXFile']['vbsHash']
                logger.info(f"Checking {table.tableDirName}")
                for patch in self.hashes:
                    if patch["sha256"] == vpxFileVBSHash:
                        logger.info(f"Found a match for {table.fullPathVPXfile}")
                        if os.path.exists(os.path.splitext(table.fullPathVPXfile)[0] + ".vbs"):
                            logger.info(f"A .vbs sidecar file already exists for that table. Skipped.")
                        else:
                            self.downloadPatch(os.path.splitext(table.fullPathVPXfile)[0] + ".vbs", patch["patched"]["url"])
                            
                    #logger.debug(f"{patch["file"]} {patch["sha256"]} {patch["patched"]["file"]}")
             except KeyError:
                 pass
    
    def checkIfVBSFileExists(self, file):
        if file.is_file():
            return True
        else:
            return False
            
    def downloadPatch(self, filename, url):
        #logger.debug(f"Patched file installed: {filename}")
        response = requests.get(url, stream=True)
        if response.status_code == 200:
            with open(filename, "wb") as file:
                for chunk in response.iter_content(chunk_size=1024):
                    file.write(chunk)
            logger.info(f"File downloaded successfully: {filename}")
        else:
            logger.error(f"Failed to download {filename}. Status code: {response.status_code}")
        

if __name__ == "__main__":
    
    pass
