import requests
import metaconfig

#remove
import olefile
import hashlib
import sys
import os


class StandaloneScripts:
    hashsUrl = "https://raw.githubusercontent.com/jsm174/vpx-standalone-scripts/refs/heads/master/hashes.json"
    
    def __init__(self, tables):
        self.hashes = None
        self.tables = tables
        print("VPX-Standalone-Scripts Patching System")
        self.downloadHashes()
        self.checkForPatches()
        #print(self.hashes)
        
    def downloadHashes(self):
        response = requests.get(StandaloneScripts.hashsUrl)
        if response.status_code == 200:
            self.hashes = response.json()
            print(f"  Retrieved hash file from VPX-Standalone-Scripts with {len(self.hashes)} patched tables.")
        else:
            print('  Failed to download hash file from VPX-Standalone-Scripts')
            
        #debug
        #print(self.hashes[0]["file"], self.hashes[0]["sha256"], self.hashes[0]["patched"]["file"])
      
    def checkForPatches(self):
         for table in self.tables:
             basepath = table.fullPathTable
             try:
                meta = metaconfig.MetaConfig(basepath+"/"+"meta.ini")
                vpxFileVBSHash = meta.config['VPXFile']['vbsHash']
                print(f"  Checking {table.tableDirName}")
                for patch in self.hashes:
                    if patch["sha256"] == vpxFileVBSHash:
                        print(f"    Found a match for {table.fullPathVPXfile}")
                        if os.path.exists(os.path.splitext(table.fullPathVPXfile)[0] + ".vbs"):
                            print(f"    A .vbs sidecar file already exists for that table. Skipped.")
                        else:
                            self.downloadPatch(os.path.splitext(table.fullPathVPXfile)[0] + ".vbs", patch["patched"]["url"])
                            
                    #print(patch["file"], patch["sha256"], patch["patched"]["file"])
             except KeyError:
                 pass
    
    def checkIfVBSFileExists(self, file):
        if file.is_file():
            return True
        else:
            return False
            
    def downloadPatch(self, filename, url):
        #print(f"    Patched file installed: {filename}")
        response = requests.get(url, stream=True)
        if response.status_code == 200:
            with open(filename, "wb") as file:
                for chunk in response.iter_content(chunk_size=1024):
                    file.write(chunk)
            print(f"    File downloaded successfully: {filename}")
        else:
            print(f"    Failed to download file. Status code: {response.status_code}")
        

if __name__ == "__main__":
    
    pass