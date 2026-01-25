import requests
from common.metaconfig import MetaConfig
import os

class StandaloneScripts:

    hashsUrl = "https://raw.githubusercontent.com/jsm174/vpx-standalone-scripts/refs/heads/master/hashes.json"
    
    def __init__(self, tables, progress_cb=None):
        self.hashes = None
        self.tables = tables
        self.progress_cb = progress_cb
        print("VPX-Standalone-Scripts Patching System initialized.")
        self.downloadHashes()
        self.checkForPatches()
        
    def downloadHashes(self):
        response = requests.get(StandaloneScripts.hashsUrl)
        if response.status_code == 200:
            self.hashes = response.json()
            print(f"Retrieved hash file from VPX-Standalone-Scripts with {len(self.hashes)} patched tables.")
        else:
            print('Failed to download hash file from VPX-Standalone-Scripts')
            
    def checkForPatches(self):
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
                print(f"Checking {table.tableDirName}")
                for patch in self.hashes:
                    if patch["sha256"] == vpxFileVBSHash:
                        print(f"Found a match for {table.fullPathVPXfile}")
                        if os.path.exists(os.path.splitext(table.fullPathVPXfile)[0] + ".vbs"):
                            print(f"A .vbs sidecar file already exists for that table. Assuming it is a patch.")
                            try:
                                table_dir = os.path.dirname(table.fullPathVPXfile)
                                meta = MetaConfig(os.path.join(table_dir, table.tableDirName + '.info'))
                                meta.data['VPXFile']['patch_applied'] = 'true'
                                meta.writeConfig()
                            except Exception:
                                pass
                        else:
                            self.downloadPatch(os.path.splitext(table.fullPathVPXfile)[0] + ".vbs", patch["patched"]["url"])
                            # mark meta.ini with patch_applied = true
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
        response = requests.get(url, stream=True)
        if response.status_code == 200:
            with open(filename, "wb") as file:
                for chunk in response.iter_content(chunk_size=1024):
                    file.write(chunk)
            print(f"File downloaded successfully: {filename}")
            # also set patch_applied in .info if possible (derive from filename)
            try:
                table_dir = os.path.dirname(filename)
                info_filename = os.path.basename(table_dir) + '.info'
                meta = MetaConfig(os.path.join(table_dir, info_filename))
                meta.data['VPXFile']['patch_applied'] = 'true'
                meta.writeConfig()
            except Exception:
                pass
        else:
            print(f"Failed to download {filename}. Status code: {response.status_code}")

