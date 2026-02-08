import requests
import json
from difflib import SequenceMatcher
import os
import re


class VPSdb:
    """
    VPSdb class handles downloading, caching, and querying the Virtual Pinball Spreadsheet (VPS) database
    along with associated media assets via VPinMediaDB.
    """

    rootTableDir = None
    data = None
    _vpinfeIniConfig = None

    vpsUrlLastUpdate = "https://raw.githubusercontent.com/VirtualPinballSpreadsheet/vps-db/refs/heads/main/lastUpdated.json"
    vpsUrldb = "https://github.com/VirtualPinballSpreadsheet/vps-db/raw/refs/heads/main/db/vpsdb.json"
    vpinmdbUrl = "https://github.com/superhac/vpinmediadb/raw/refs/heads/main/vpinmdb.json"

    def __init__(self, rootTableDir, vpinfeIniConfig):
        print("Initializing VPSdb")

        self._vpinfeIniConfig = vpinfeIniConfig
        version = self.downloadLastUpdate()

        if version:
            print(f"Current VPSdb version @ VPSdb: {version}")
            try:
                # Download DB if newer than local version
                if self._vpinfeIniConfig.config['VPSdb']['last'] < version:
                    self.downloadDB()
                else:
                    print("VPSdb currently at latest revision.")
            except KeyError:  # No entry for VPSdb version in config
                self.downloadDB()
                self._vpinfeIniConfig.config.setdefault('VPSdb', {})['last'] = version

            # Always update the version in config
            self._vpinfeIniConfig.config['VPSdb']['last'] = version
            self._vpinfeIniConfig.save()

            self.rootTableDir = rootTableDir

            # Load database from local file
            if self.fileExists('vpsdb.json'):
                try:
                    with open('vpsdb.json', 'r', encoding="utf-8") as file:
                        self.data = json.load(file)
                        print(f"Total VPSdb entries: {len(self.data)}")
                except json.JSONDecodeError:
                    print("Invalid JSON format in vpsdb.json.")
            else:
                print("JSON file vpsdb.json not found.")

        # Setup preferences
        self.tabletype = self._vpinfeIniConfig.config['Media']["tabletype"].lower()
        self.tableresolution = self._vpinfeIniConfig.config['Media']["tableresolution"].lower()
        self.tablevideoresolution = self._vpinfeIniConfig.config['Media']["tablevideoresolution"].lower()
        print(f"Using {self.tableresolution}/{self.tabletype} tables (video: {self.tablevideoresolution})")

        # Load additional media DB
        self.vpinmediadbjson = self.downloadMediaJson()

    # ----------------------------------------------------------------------
    # Python container magic methods
    def __len__(self):
        return len(self.data) if self.data else 0

    def __contains__(self, item):
        return item in self.data if self.data else False

    def tables(self):
        return self.data

    # ----------------------------------------------------------------------
    # Table lookups
    def lookupName(self, name, manufacturer, year):
        """Fuzzy search for a table by name, manufacturer, and year."""
        if not all((name, manufacturer, year)):
            return None

        for table in self.data or []:
            # Compare table names
            if SequenceMatcher(None, name.lower(), table["name"].lower()).ratio() < 0.8:
                continue

            # Compare manufacturers
            if SequenceMatcher(None, manufacturer.lower(), table["manufacturer"].lower()).ratio() < 0.8:
                continue

            # Compare year
            if SequenceMatcher(None, str(year), str(table["year"])).ratio() >= 0.8:
                return table

        print(f"No match found for: {name}")
        return None

    def parseTableNameFromDir(self, directory_name):
        """
        Parses a directory name of format: 'Name (Manufacturer Year)'
        Example: 'Attack From Mars (Bally 1995)'
        """
        pattern = r"^(.+?) \(([^()]+) (\d{4})\)$"
        match = re.match(pattern, directory_name)
        if not match:
            return None
        return {
            "name": match.group(1),
            "manufacturer": match.group(2),
            "year": int(match.group(3))
        }

    # ----------------------------------------------------------------------
    # Remote content handling
    def downloadMediaJson(self):
        """Downloads the VPinMediaDB JSON index."""
        try:
            response = requests.get(self.vpinmdbUrl)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            print(f"Failed to retrieve vpinmdb.json: {e}")
            return None

    def downloadDB(self):
        """Downloads the VPS database JSON."""
        try:
            response = requests.get(VPSdb.vpsUrldb)
            response.raise_for_status()
            with open('vpsdb.json', 'wb') as file:
                file.write(response.content)
            print("Successfully downloaded vpsdb.json from VPSdb")
        except requests.RequestException as e:
            print(f"Failed to download vpsdb.json: {e}")

    def downloadLastUpdate(self):
        """Fetches the last update version string from VPSdb."""
        try:
            response = requests.get(VPSdb.vpsUrlLastUpdate)
            response.raise_for_status()
            return response.text.strip()
        except requests.RequestException as e:
            print(f"Failed to retrieve lastUpdate.json: {e}")
            return None

    def downloadMediaFile(self, tableId, url, filename):
        """Downloads a single media file by URL."""
        print(f"Downloading {filename} from {url}")
        try:
            response = requests.get(url)
            response.raise_for_status()
            with open(filename, 'wb') as file:
                file.write(response.content)
            print(f"Successfully downloaded {filename} from VPinMedia")
        except requests.RequestException as e:
            print(f"Failed to download {filename} for table {tableId}: {e}")

    # ----------------------------------------------------------------------
    # Local file helpers
    def fileExists(self, path):
        return bool(path and os.path.exists(path))

    def downloadMedia(self, tableId, metadata, key, filename, defaultFilename, metaConfig=None, mediaType=None):
        """
        Download a media file if not already present, or re-download if the
        remote MD5 hash differs from the locally stored hash.
        :param tableId: VPS table ID
        :param metadata: dict containing media info
        :param key: which asset to download
        :param filename: local path to check
        :param defaultFilename: local path to save to
        :param metaConfig: MetaConfig instance for MD5 comparison
        :param mediaType: media type key used in the Medias section
        :returns: (downloaded_path, md5hash) if downloaded or already exists, else None
        """
        if not metadata or key not in metadata:
            return None

        remoteMd5 = metadata.get(f"{key}_md5", "")

        if self.fileExists(filename):
            # Check if the remote hash changed compared to what we stored
            if metaConfig and mediaType and remoteMd5:
                existing = metaConfig.getMedia(mediaType)
                if existing and existing.get("Source") == "vpinmediadb":
                    storedMd5 = existing.get("MD5Hash", "")
                    if storedMd5 and storedMd5 != remoteMd5:
                        print(f"MD5 changed for {mediaType} ({storedMd5} -> {remoteMd5}), re-downloading")
                        self.downloadMediaFile(tableId, metadata[key], filename)
            return (filename, remoteMd5)

        self.downloadMediaFile(tableId, metadata[key], defaultFilename)
        if self.fileExists(defaultFilename):
            return (defaultFilename, remoteMd5)
        return None

    def downloadMediaForTable(self, table, id, metaConfig=None):
        """Download all associated media for a given table."""
        if id not in self.vpinmediadbjson:
            print(f"No media exists for {table.fullPathTable} (ID {id}).")
            return

        tablemediajson = self.vpinmediadbjson[id]

        # Ensure medias directory exists
        medias_dir = os.path.join(table.fullPathTable, "medias")
        os.makedirs(medias_dir, exist_ok=True)

        def _isUserMedia(mediaType):
            """Check if the existing media entry is user-provided."""
            if not metaConfig:
                return False
            existing = metaConfig.getMedia(mediaType)
            return existing is not None and existing.get("Source") != "vpinmediadb"

        def _record(mediaType, result):
            if result and metaConfig:
                path, md5hash = result
                metaConfig.addMedia(mediaType, "vpinmediadb", path, md5hash)

        def _process(mediaType, metadata, key, filename, defaultFilename):
            """Skip download and record if the media is user-provided."""
            if _isUserMedia(mediaType):
                print(f"Skipping {mediaType}: user-provided media")
                return
            result = self.downloadMedia(id, metadata, key, filename, defaultFilename, metaConfig, mediaType)
            _record(mediaType, result)

        # Background & DMD (within '1k' key)
        _process('bg', tablemediajson.get('1k'), 'bg', table.BGImagePath, f"{table.fullPathTable}/medias/bg.png")
        _process('dmd', tablemediajson.get('1k'), 'dmd', table.DMDImagePath, f"{table.fullPathTable}/medias/dmd.png")

        # Other assets
        _process('wheel', tablemediajson, 'wheel', table.WheelImagePath, f"{table.fullPathTable}/medias/wheel.png")
        _process('cab', tablemediajson, 'cab', table.CabImagePath, f"{table.fullPathTable}/medias/cab.png")
        _process('realdmd', tablemediajson, 'realdmd', table.realDMDImagePath, f"{table.fullPathTable}/medias/realdmd.png")
        _process('realdmd_color', tablemediajson, 'realdmd_color', table.realDMDColorImagePath, f"{table.fullPathTable}/medias/realdmd-color.png")
        _process('flyer', tablemediajson, 'flyer', table.FlyerImagePath, f"{table.fullPathTable}/medias/flyer.png")

        # Table image depends on resolution/type
        _process(self.tabletype, tablemediajson.get(self.tableresolution), self.tabletype, table.TableImagePath, f"{table.fullPathTable}/medias/{self.tabletype}.png")

        # Video assets
        _process('bg_video', tablemediajson.get(self.tablevideoresolution), 'bg_video', table.BGVideoPath, f"{table.fullPathTable}/medias/bg.mp4")
        _process('dmd_video', tablemediajson.get(self.tablevideoresolution), 'dmd_video', table.DMDVideoPath, f"{table.fullPathTable}/medias/dmd.mp4")
        _process(f'{self.tabletype}_video', tablemediajson.get(self.tablevideoresolution), f'{self.tabletype}_video', table.TableVideoPath, f"{table.fullPathTable}/medias/{self.tabletype}.mp4")

    # ----------------------------------------------------------------------
    def updateTable(self, name, manufacturer, year):
        """UI hook: updates progress label (requires UI integration)."""
        self.progress_table_label.config(text=f"{name}\n({manufacturer} {year})")


