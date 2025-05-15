import requests
import json
import pprint
from difflib import SequenceMatcher
import os
import re
import sys

RED_CONSOLE_TEXT = '\033[31m'
RESET_CONSOLE_TEXT = '\033[0m'

class VPSdb:
  
  vpsUrlLastUpdate = "https://raw.githubusercontent.com/VirtualPinballSpreadsheet/vps-db/refs/heads/main/lastUpdated.json"
  vpsUrldb = "https://github.com/VirtualPinballSpreadsheet/vps-db/raw/refs/heads/main/db/vpsdb.json"
  vpsUrlMediaBackground = "https://raw.githubusercontent.com/superhac/vpinmediadb/master/{tableId}/1k/bg.png"
  vpsUrlMediaDMD = "https://raw.githubusercontent.com/superhac/vpinmediadb/master/{tableId}/1k/dmd.png"
  vpsUrlMediaWheel = "https://raw.githubusercontent.com/superhac/vpinmediadb/master/{tableId}/wheel.png"
  vpsUrlMediaTable = "https://raw.githubusercontent.com/superhac/vpinmediadb/master/{tableId}/4k/table.png"

  def __init__(self, rootTableDir, vpinfeIniConfig):
    print("Initing VPSdb")
    version = self.downloadLastUpdate()
    if version != None:
      print("  Current VPSdb version @ VPSdb: ", version)
      try:
        if vpinfeIniConfig.config['VPSdb']['last'] < version:
          self.downloadDB()
        else:
          print("  VPSdb currently at lastest revision.")
      except KeyError:
        self.downloadDB()
      
      vpinfeIniConfig.config['VPSdb']['last'] = version
      vpinfeIniConfig.save()
      
      self.rootTableDir = rootTableDir
      try:
        with open('vpsdb.json', 'r') as file:
          self.data = json.load(file)
          print(f"  Total VPSdb entries: {len(self.data)}")

      except FileNotFoundError:
        print("  Error: JSON file not found.")
      except json.JSONDecodeError:
        print("  Error: Invalid JSON format.")
    
  def lookupName(self, name, manufacturer, year):
    for table in self.data:
      try:
        name_similarity_ratio = SequenceMatcher(None, name.lower(),  table["name"].lower()).ratio()
        #print(f'"{name}" "{table["name"]}"')
        if name_similarity_ratio >= .8:
            #print("name matched with threshold:", table["name"], name_similarity_ratio)
            similarity_ratio = SequenceMatcher(None, manufacturer.lower(),  table["manufacturer"].lower()).ratio()
            #print("manufacturer matched with threshold:", table["manufacturer"], similarity_ratio)
            if similarity_ratio >= .8:
              similarity_ratio = SequenceMatcher(None, str(year),  str(table["year"])).ratio()
              if similarity_ratio >= .8:
                print("  Name, manufacturer, and year matched with threshold:", table["name"])
                return table        
      except KeyError:
        print("lookupName: no key?")
        pass
    print(f"{RED_CONSOLE_TEXT}  No match for: {name}{RESET_CONSOLE_TEXT} ")  
    return None

  def parseTableNameFromDir(self, directory_name):
    pattern = r"^(.+?) \(([^()]+) (\d{4})\)$"
    match = re.match(pattern, directory_name)
    
    if match:
        table_name = match.group(1)
        manufacturer = match.group(2)
        year = int(match.group(3))
        return {
            "name": table_name,
            "manufacturer": manufacturer,
            "year": year
        }
    else:
        return None

  def downloadDB(self):
    response = requests.get(VPSdb.vpsUrldb)

    file_Path = 'vpsdb.json'
    if response.status_code == 200:
      with open(file_Path, 'wb') as file:
        file.write(response.content)
      print(f"  Successfully downloaded {file_Path} from VPSdb")
    else:
      print(f"  Failed to download {file_Path} from VPSdb. Status code: {response.status_code}")
      
  def downloadLastUpdate(self):
    response = requests.get(VPSdb.vpsUrlLastUpdate)
    if response.status_code == 200:
      content = response.text  # Use response.content for binary data
      return content
    else:
      print(f"Failed to retrieve content lastUpdate.json from VPSdb. Status code: {response.status_code}")
      return None

  def downloadMediaFile(self, url, filename):
    print(f"  Downloading {filename} from {url}")
    response = requests.get(url)
    if response.status_code == 200:
      with open(filename, 'wb') as file:
        file.write(response.content)
      print(f"  Successfully downloaded {filename} from VPinMedia")
    else:
      print(f"  Failed to download {filename} from VPinMedia. Status code: {response.status_code}")

  def fileExists(self, path):
    if path is None:
      return False
    return os.path.exists(path)

  def createUrl(self, base, tableId):
    return base.replace("{tableId}", tableId)

  def downloadMedia(self, tableId, baseurl, filename, defaultFilename):
    if self.fileExists(filename):
      return
    url = self.createUrl(baseurl, tableId)
    self.downloadMediaFile(url, defaultFilename)

  def downloadMediaForTable(self, table, id):
    self.downloadMedia(id, VPSdb.vpsUrlMediaBackground, table.BGImagePath, table.fullPathTable + "/bg.png")
    self.downloadMedia(id, VPSdb.vpsUrlMediaDMD, table.DMDImagePath, table.fullPathTable + "/dmd.png")
    self.downloadMedia(id, VPSdb.vpsUrlMediaWheel, table.WheelImagePath, table.fullPathTable + "/wheel.png")
    self.downloadMedia(id, VPSdb.vpsUrlMediaTable, table.TableImagePath, table.fullPathTable + "/table.png")

if __name__ == "__main__":
  #searchForType()
  #pprint.pprint(data[655], compact=True)
  #lookupName("King Kong", "data east", "1990")
  tableDirs = loadTables("/home/superhac/tables")
  #print(tableDirs)
  #sys.exit()
  for tableDir in tableDirs:
    parsed = parse_directory(tableDir)
    print("Checking: "+tableDir)
    lookupName(parsed["table_name"], parsed["manufacturer"], parsed["year"])
    print()

