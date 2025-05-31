import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageTk
import requests
import json
from difflib import SequenceMatcher
import os
import re
import sys
import logging

RED_CONSOLE_TEXT = '\033[31m'
RESET_CONSOLE_TEXT = '\033[0m'

class VPSdb:
  logger = None
  rootTableDir = None
  data = None
  _vpinfeIniConfig = None

  vpsUrlLastUpdate = "https://raw.githubusercontent.com/VirtualPinballSpreadsheet/vps-db/refs/heads/main/lastUpdated.json"
  vpsUrldb = "https://github.com/VirtualPinballSpreadsheet/vps-db/raw/refs/heads/main/db/vpsdb.json"
  vpinmdbUrl = "https://github.com/superhac/vpinmediadb/raw/refs/heads/main/vpinmdb.json"

  def __init__(self, rootTableDir, vpinfeIniConfig):
    global logger
    logger = logging.getLogger()

    logger.info("Initializing VPSdb")
    self._vpinfeIniConfig = vpinfeIniConfig
    version = self.downloadLastUpdate()
    if version != None:
      logger.info(f"Current VPSdb version @ VPSdb: {version}")
      if self._vpinfeIniConfig.get_string('VPSdb','last','') < version:
        self.downloadDB()
      else:
        logger.info("VPSdb currently at lastest revision.")
      
      self._vpinfeIniConfig.config['VPSdb']['last'] = version
      self._vpinfeIniConfig.save()
      
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
    self.tabletype = self._vpinfeIniConfig.get_string('Media',"tabletype","table").lower()
    self.tableresolution = self._vpinfeIniConfig.get_string('Media',"tableresolution","4k").lower()
    logger.debug(f"Using {self.tableresolution}/{self.tabletype} tables")
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
        #logger.debug(f'"{name}" "{table["name"]}"')
        if name_similarity_ratio < .8:
          continue
        #logger.debug("name matched with threshold:", table["name"], name_similarity_ratio)
        similarity_ratio = SequenceMatcher(None, manufacturer.lower(),  table["manufacturer"].lower()).ratio()
        #logger.debug(f"Manufacturer matched with threshold: {table["manufacturer"]} with a ratio of {similarity_ratio}")
        if similarity_ratio < .8:
          continue
        similarity_ratio = SequenceMatcher(None, str(year),  str(table["year"])).ratio()
        if similarity_ratio >= .8:
          logger.info(f"{name} ({manufacturer} {year}) matched with threshold: {table['name']}")
          return table        
    logger.error(f"{RED_CONSOLE_TEXT} No match found for: {name}{RESET_CONSOLE_TEXT}")
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
      logger.error(f"Failed to retrieve content vpmdb.json from VPinMediaDBStatus code: {response.status_code}")
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
    try:
      response = requests.get(url)
    except:
        logger.error(f"Failed to download {filename} from VPinMedia with id {tableId}. Excepton raised.")
        return
    if response.status_code == 200:
      with open(filename, 'wb') as file:
        file.write(response.content)
      logger.info(f"Successfully downloaded {filename} from VPinMedia")
    else:
      logger.error(f"Failed to download {filename} from VPinMedia with id {tableId}. Status code: {response.status_code}")

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
      logger.error(f"{RED_CONSOLE_TEXT}No media exists yet for {table.fullPathTable} with ID {id}.{RESET_CONSOLE_TEXT}")
      return
    tablemediajson = self.vpinmediadbjson[id]
    self.downloadMedia(id, tablemediajson[self.tableresolution], 'bg', table.BGImagePath, table.fullPathTable + "/bg.png")
    self.downloadMedia(id, tablemediajson[self.tableresolution], 'dmd', table.DMDImagePath, table.fullPathTable + "/dmd.png")
    self.downloadMedia(id, tablemediajson, 'wheel', table.WheelImagePath, table.fullPathTable + "/wheel.png")
    self.downloadMedia(id, tablemediajson[self.tableresolution], self.tabletype, table.TableImagePath, table.fullPathTable + "/" + self.tabletype + ".png")

  def updateTable(self, name, manufacturer, year):
      self.progress_table_label.config(text=f"{name}\n({manufacturer} {year})")

  def updateProgress(self, current, total):
      self.progress_bar["value"] = current
      self.progress_label.config(text=f"Processing {current}/{total} tables")
      return self.progress_was_canceled

  def cancelProgress(self):
    logger.info("Canceled buildmeta and media download operation.")
    self.progress_was_canceled = True

  def setupProgressDialog(self, total):
    root = tk.Tk()
    root.title("Media Download Progress")
    root.geometry("")

    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        icon_path = sys._MEIPASS+"/assets/download-icon.png"
    else:
        icon_path = "assets/download-icon.png"

    if os.path.exists(icon_path):
        pil_image = Image.open(icon_path)
        icon_image = ImageTk.PhotoImage(pil_image)
        root.iconphoto(True, icon_image)

    self.progress_frame = tk.Frame(root, padx=20, pady=20)
    self.progress_frame.pack(fill="both", expand=True)
    # Progress Bar
    self.progress_bar = ttk.Progressbar(self.progress_frame, orient="horizontal", length=300, mode="determinate")
    self.progress_bar.pack(fill="x", expand=True, pady=(0, 10))
    self.progress_bar["maximum"] = total

    # Status Label
    self.progress_label = tk.Label(self.progress_frame, text="Starting download...")
    self.progress_label.pack(fill="x", expand=True)

    # Table Label
    self.progress_table_label = tk.Label(
        self.progress_frame,
        text="",
        justify="center",
        anchor="center",
        height=2,            # Reserve space for 2 lines
        width=50,            # Fixed character width to prevent resizing
        wraplength=380  
    )
    self.progress_table_label.pack(fill="x", expand=True, pady=(0, 5))

    self.progress_cancel = tk.Button(self.progress_frame, text="Cancel", command=self.cancelProgress)
    self.progress_cancel.pack(pady=(10, 0))

    root.update_idletasks()
    root.resizable(False, False)

    self.progress_was_canceled = False

    return root

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

