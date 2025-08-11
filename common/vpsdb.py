import requests
import json
from difflib import SequenceMatcher
import os
import re
import sys
import colorama

class VPSdb:
  rootTableDir = None
  data = None
  _vpinfeIniConfig = None

  vpsUrlLastUpdate = "https://raw.githubusercontent.com/VirtualPinballSpreadsheet/vps-db/refs/heads/main/lastUpdated.json"
  vpsUrldb = "https://github.com/VirtualPinballSpreadsheet/vps-db/raw/refs/heads/main/db/vpsdb.json"
  vpinmdbUrl = "https://github.com/superhac/vpinmediadb/raw/refs/heads/main/vpinmdb.json"

  def __init__(self, rootTableDir, vpinfeIniConfig):
    #global logger
    #logger = logging.getLogger()
    colorama.init()

    print("Initializing VPSdb")
    self._vpinfeIniConfig = vpinfeIniConfig
    version = self.downloadLastUpdate()
    if version != None:
      print(f"Current VPSdb version @ VPSdb: {version}")
      if self._vpinfeIniConfig.config['VPSdb']['last'] < version:
        self.downloadDB()
      else:
        print("VPSdb currently at lastest revision.")
      
      self._vpinfeIniConfig.config['VPSdb']['last'] = version
      self._vpinfeIniConfig.save()
      
      self.rootTableDir = rootTableDir
      if self.fileExists('vpsdb.json'):
        try:
            with open('vpsdb.json', 'r') as file:
              self.data = json.load(file)
              print(f"Total VPSdb entries: {len(self.data)}")
        except json.JSONDecodeError:
          print(f"Invalid JSON format in vpsdb.json.")
      else:
        print(f"JSON file vpsdb.json not found.")
    self.tabletype = self._vpinfeIniConfig.config['Media']["tabletype"].lower()
    self.tableresolution = self._vpinfeIniConfig.config['Media']["tableresolution"].lower()
    print(f"Using {self.tableresolution}/{self.tabletype} tables")
    self.vpinmediadbjson = self.downloadMediaJson()


  def __len__(self):
    return len(self.data)

  def __contains__(self, item):
    return item in self.data

  def tables(self):
    return self.data

  def lookupName(self, name, manufacturer, year):
    if any(param is None for param in (name, manufacturer, year)):
      return None
    for table in self.data:
        name_similarity_ratio = SequenceMatcher(None, name.lower(),  table["name"].lower()).ratio()
        #print(f'"{name}" "{table["name"]}"')
        if name_similarity_ratio < .8:
          continue
        #print("name matched with threshold:", table["name"], name_similarity_ratio)
        similarity_ratio = SequenceMatcher(None, manufacturer.lower(),  table["manufacturer"].lower()).ratio()
        #print(f"Manufacturer matched with threshold: {table["manufacturer"]} with a ratio of {similarity_ratio}")
        if similarity_ratio < .8:
          continue
        similarity_ratio = SequenceMatcher(None, str(year),  str(table["year"])).ratio()
        if similarity_ratio >= .8:
          #print(f"{name} ({manufacturer} {year}) matched with threshold: {table['name']}")
          return table        
    print(f"{colorama.Fore.RED} No match found for: {name}{colorama.Style.RESET_ALL}")
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

  def downloadMediaJson(self):
    response = requests.get(self.vpinmdbUrl)
    if response.status_code == 200:
      content = response.text
      return json.loads(content)
    else:
      print(f"Failed to retrieve content vpmdb.json from VPinMediaDBStatus code: {response.status_code}")
      return None

  def downloadDB(self):
    response = requests.get(VPSdb.vpsUrldb)

    file_Path = 'vpsdb.json'
    if response.status_code == 200:
      with open(file_Path, 'wb') as file:
        file.write(response.content)
      print(f"Successfully downloaded {file_Path} from VPSdb")
    else:
      print(f"Failed to download {file_Path} from VPSdb. Status code: {response.status_code}")
      
  def downloadLastUpdate(self):
    response = requests.get(VPSdb.vpsUrlLastUpdate)
    if response.status_code == 200:
      content = response.text  # Use response.content for binary data
      return content
    else:
      print(f"Failed to retrieve content lastUpdate.json from VPSdb. Status code: {response.status_code}")
      return None

  def downloadMediaFile(self, tableId, url, filename):
    print(f"Downloading {filename} from {url}")
    try:
      response = requests.get(url)
    except:
        print(f"Failed to download {filename} from VPinMedia with id {tableId}. Excepton raised.")
        return
    if response.status_code == 200:
      with open(filename, 'wb') as file:
        file.write(response.content)
      print(f"Successfully downloaded {filename} from VPinMedia")
    else:
      print(f"Failed to download {filename} from VPinMedia with id {tableId}. Status code: {response.status_code}")

  def fileExists(self, path):
    if path is None:
      return False
    return os.path.exists(path)

  def downloadMedia(self, tableId, metadata, key, filename, defaultFilename):
    if metadata is None or key not in metadata or self.fileExists(filename):
      return
    self.downloadMediaFile(tableId, metadata[key], defaultFilename)

  def downloadMediaForTable(self, table, id):
    if not id in self.vpinmediadbjson:
      print(f"{colorama.Fore.RED}No media exists yet for {table.fullPathTable} with ID {id}.{colorama.Style.RESET_ALL}")
      return
    tablemediajson = self.vpinmediadbjson[id]
    self.downloadMedia(id, tablemediajson[self.tableresolution], 'bg', table.BGImagePath, table.fullPathTable + "/bg.png")
    self.downloadMedia(id, tablemediajson[self.tableresolution], 'dmd', table.DMDImagePath, table.fullPathTable + "/dmd.png")
    self.downloadMedia(id, tablemediajson, 'wheel', table.WheelImagePath, table.fullPathTable + "/wheel.png")
    self.downloadMedia(id, tablemediajson[self.tableresolution], self.tabletype, table.TableImagePath, table.fullPathTable + "/" + self.tabletype + ".png")

  def updateTable(self, name, manufacturer, year):
      self.progress_table_label.config(text=f"{name}\n({manufacturer} {year})")

if __name__ == "__main__":
  #logger = init_logger("VPSDB")
  #searchForType()
  #print(data[655], compact=True)
  #lookupName("King Kong", "data east", "1990")
  
  #print(tableDirs)
  #sys.exit()
  
  
  """ tableDirs = loadTables("/home/superhac/tables")
  for tableDir in tableDirs:
    parsed = parse_directory(tableDir)
    print("Checking: "+tableDir)
    lookupName(parsed["table_name"], parsed["manufacturer"], parsed["year"])
    print("Done.") """

