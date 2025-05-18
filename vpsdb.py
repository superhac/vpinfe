import requests
import json
from difflib import SequenceMatcher
import os
import re
import sys
from logger import get_logger

RED_CONSOLE_TEXT = '\033[31m'
RESET_CONSOLE_TEXT = '\033[0m'

class VPSdb:
  logger = None
  rootTableDir = None
  data = None
  _iniConfig = None

  vpsUrlLastUpdate = "https://raw.githubusercontent.com/VirtualPinballSpreadsheet/vps-db/refs/heads/main/lastUpdated.json"
  vpsUrldb = "https://github.com/VirtualPinballSpreadsheet/vps-db/raw/refs/heads/main/db/vpsdb.json"
  vpsUrlMediaBackground = "https://raw.githubusercontent.com/superhac/vpinmediadb/master/{tableId}/1k/bg.png"
  vpsUrlMediaDMD = "https://raw.githubusercontent.com/superhac/vpinmediadb/master/{tableId}/1k/dmd.png"
  vpsUrlMediaWheel = "https://raw.githubusercontent.com/superhac/vpinmediadb/master/{tableId}/wheel.png"
  vpsUrlMediaTable = "https://raw.githubusercontent.com/superhac/vpinmediadb/master/{tableId}/{tableResolution}/{tableType}.png"


  def __init__(self, rootTableDir, vpinfeIniConfig):
    global logger
    logger = get_logger()

    logger.info("Initializing VPSdb")
    self._iniConfig = vpinfeIniConfig.config
    version = self.downloadLastUpdate()
    if version != None:
      logger.info(f"Current VPSdb version @ VPSdb: {version}")
      try:
        if vpinfeIniConfig.config['VPSdb']['last'] < version:
          self.downloadDB()
        else:
          logger.info("VPSdb currently at lastest revision.")
      except KeyError:
        self.downloadDB()
      
      vpinfeIniConfig.config['VPSdb']['last'] = version
      vpinfeIniConfig.save()
      
      self.rootTableDir = rootTableDir
      if self.fileExists('vpsdb.json'):
        try:
            with open('vpsdb.json', 'r') as file:
              self.data = json.load(file)
              logger.info(f"Total VPSdb entries: {len(self.data)}")
        except json.JSONDecodeError:
          logger.error(f"Invalid JSON format in vpsdb.json.")
      else:
        logger.error(f"JSON file vpsdb.json not found.")
      self.setTablesPath()
    
  def setTablesPath(self):
    self.tabletype = self._iniConfig['Media']["tabletype"]
    self.tableresolution = self._iniConfig['Media']["tableresolution"]
    if self.tableresolution is '':
      self.pathresolution = "4k"
    else:
      self.pathresolution = "4k" if "4k" in self.tableresolution else "1k"
    self.pathstyle = "" if self.tabletype is '' else self.tabletype
    if self.tabletype is '' or self.tabletype != "fss":
      self.nameTableFile = "table"
    else:
      self.nameTableFile = "fss"
      self.pathresolution = f"fss/{self.pathresolution}"
    logger.debug(f"{self.pathresolution}/{self.nameTableFile}")

  def lookupName(self, name, manufacturer, year):
    for table in self.data:
      try:
        name_similarity_ratio = SequenceMatcher(None, name.lower(),  table["name"].lower()).ratio()
        #logger.debug(f'"{name}" "{table["name"]}"')
        if name_similarity_ratio >= .8:
            #logger.debug("name matched with threshold:", table["name"], name_similarity_ratio)
            similarity_ratio = SequenceMatcher(None, manufacturer.lower(),  table["manufacturer"].lower()).ratio()
            #logger.debug(f"Manufacturer matched with threshold: {table["manufacturer"]} with a ratio of {similarity_ratio}")
            if similarity_ratio >= .8:
              similarity_ratio = SequenceMatcher(None, str(year),  str(table["year"])).ratio()
              if similarity_ratio >= .8:
                logger.info(f"Name, manufacturer, and year matched with threshold: {table["name"]}")
                return table        
      except KeyError:
        logger.error("lookupName: no key?")
        pass
    logger.error(f"{RED_CONSOLE_TEXT} No match for: {name}{RESET_CONSOLE_TEXT}")
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
      logger.info(f"Successfully downloaded {file_Path} from VPSdb")
    else:
      logger.error(f"Failed to download {file_Path} from VPSdb. Status code: {response.status_code}")
      
  def downloadLastUpdate(self):
    response = requests.get(VPSdb.vpsUrlLastUpdate)
    if response.status_code == 200:
      content = response.text  # Use response.content for binary data
      return content
    else:
      logger.error(f"Failed to retrieve content lastUpdate.json from VPSdb. Status code: {response.status_code}")
      return None

  def downloadMediaFile(self, tableId, url, filename):
    logger.debug(f"Downloading {filename} from {url}")
    response = requests.get(url)
    if response.status_code == 200:
      with open(filename, 'wb') as file:
        file.write(response.content)
      logger.info(f"  Successfully downloaded {filename} from VPinMedia")
    else:
      logger.error(f"Failed to download {filename} from VPinMedia with id {tableId}. Status code: {response.status_code}")

  def fileExists(self, path):
    if path is None:
      return False
    return os.path.exists(path)

  def createUrl(self, base, tableId):
    return base.replace("{tableId}", tableId).replace("{tableResolution}", self.pathresolution).replace("{tableType}", self.nameTableFile)

  def downloadMedia(self, tableId, baseurl, filename, defaultFilename):
    if self.fileExists(filename):
      return
    url = self.createUrl(baseurl, tableId)
    self.downloadMediaFile(tableId, url, defaultFilename)

  def downloadMediaForTable(self, table, id):
    self.downloadMedia(id, VPSdb.vpsUrlMediaBackground, table.BGImagePath, table.fullPathTable + "/bg.png")
    self.downloadMedia(id, VPSdb.vpsUrlMediaDMD, table.DMDImagePath, table.fullPathTable + "/dmd.png")
    self.downloadMedia(id, VPSdb.vpsUrlMediaWheel, table.WheelImagePath, table.fullPathTable + "/wheel.png")
    self.downloadMedia(id, VPSdb.vpsUrlMediaTable, table.TableImagePath, table.fullPathTable + "/" + self.nameTableFile + ".png")

if __name__ == "__main__":
  logger = init_logger("VPSDB")
  #searchForType()
  #logger.debug(data[655], compact=True)
  #lookupName("King Kong", "data east", "1990")
  tableDirs = loadTables("/home/superhac/tables")
  #logger.debug(tableDirs)
  #sys.exit()
  for tableDir in tableDirs:
    parsed = parse_directory(tableDir)
    logger.debug("Checking: "+tableDir)
    lookupName(parsed["table_name"], parsed["manufacturer"], parsed["year"])
    logger.debug("Done.")

