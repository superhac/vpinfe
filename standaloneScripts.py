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
    
    def list_ole_files(ole_path):
        try:
            # Open the OLE file
            ole = olefile.OleFileIO(ole_path)

            # List all streams and storages inside
            files = ole.listdir()

            # Print each file path
            for file in files:
                print('/'.join(file))

            # Close the file
            ole.close()
        except Exception as e:
            print(f"Error: {e}")
    
    def readInStream():
         # Open the OLE file
        ole = olefile.OleFileIO("/home/superhac/tables/The Last Starfighter (Taito 1983)/Last Starfighter, The (Taito, 1983) hybrid v1.04.vpx")
        #ole = olefile.OleFileIO("/home/superhac/tables/Volcano (Gottlieb 1981)/Volcano (Gottlieb 1981)_Bigus(MOD)4.0.vpx")
        
         # Specify the stream name inside the OLE file
        stream_name = "GameStg/GameData"  # Change this to the actual stream name
        output_filename = "test.vbs"
        if ole.exists(stream_name):
            with ole.openstream(stream_name) as stream:
                data = stream.read()            
        else:
            print("Stream not found.")
            return None
    
        return data
    
    def find_next_offset(data: bytes, word: bytes = b"CODE") -> int:
        index = data.find(word)
        if index != -1:
            return index + len(word)
        return -1  # Return -1 if the word is not found
       
    def write(data):
        with open('test.vbs', 'w', encoding='cp437') as file:
            file.write(data)
    
    def get_slice(data: bytes, offset: int, end: int) -> bytes:
        if offset < 0 or end > len(data) or offset >= end:
            return b""  # Invalid range, return empty byte string

        return data[offset:end]
    
    def ensure_msdos_line_endings(text):
        if "\r\n" in text and "\n" not in text.replace("\r\n", ""):
            return text  # Already in MSDOS format, return as is
        return text.replace("\r\n", "\n").replace("\n", "\r\n")  # Normalize to MSDOS
    
    data = readInStream()
    offset = find_next_offset(data)
    length = int.from_bytes(data[offset:offset + 4], byteorder="little", signed=True)
    print(length)
    print(offset)  # Output: position after "code"
    
    data =  get_slice(data, offset+4, offset+4+length)
    
    
    textData = data.decode('utf-8')
    textData = ensure_msdos_line_endings(textData)
    
    hashed = hashlib.sha256(textData.encode('utf-8')).hexdigest()
    print(hashed)
    write(textData)
    sys.exit()
    
    
    
    # Compute SHA-256 hash
    sha256_hash = hashlib.sha256(textData.encode('cp437')).hexdigest()
    print(f"SHA-256: {sha256_hash}")
    
    write(textData)
    
    
    sys.exit()
    