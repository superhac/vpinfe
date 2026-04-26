import logging
from difflib import SequenceMatcher
import re

from common.paths import CONFIG_DIR
from common.config_access import MediaConfig
from common.vpsdb_cache import VPinMediaDatabase, VPSDatabaseCache
from common.vpsdb_media import VPSMediaDownloader


logger = logging.getLogger("vpinfe.common.vpsdb")


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
        logger.info("Initializing VPSdb")

        self._vpinfeIniConfig = vpinfeIniConfig
        self._config_dir = CONFIG_DIR
        self._config_dir.mkdir(parents=True, exist_ok=True)
        self._cache = VPSDatabaseCache(
            self._config_dir,
            self._vpinfeIniConfig,
            db_url=VPSdb.vpsUrldb,
            last_update_url=VPSdb.vpsUrlLastUpdate,
        )
        self._vpsdb_path = self._cache.path
        self.rootTableDir = rootTableDir
        self.data = self._cache.ensure_current()
        logger.info("Total VPSdb entries: %s", len(self.data))

        # Setup preferences
        media_config = MediaConfig.from_config(self._vpinfeIniConfig)
        self.tabletype = media_config.table_type
        self.tableresolution = media_config.table_resolution
        self.tablevideoresolution = media_config.table_video_resolution
        logger.info(
            "Using %s/%s tables (video: %s)",
            self.tableresolution,
            self.tabletype,
            self.tablevideoresolution,
        )

        self.vpinmediadbjson = self.downloadMediaJson()
        self._media_downloader = VPSMediaDownloader(
            self.vpinmediadbjson,
            tabletype=self.tabletype,
            tableresolution=self.tableresolution,
            tablevideoresolution=self.tablevideoresolution,
        )

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

        logger.debug("No match found for: %s", name)
        return None

    def parseTableNameFromDir(self, directory_name):
        """
        Parses a directory name of format: 'Name (Manufacturer Year)'
        and ignores any suffix text after that block.
        Example: 'Attack From Mars (Bally 1995) (v2)'
        """
        pattern = r"^(.+?) \(([^()]+) (\d{4})\)(?:\s.*)?$"
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
        return VPinMediaDatabase(self.vpinmdbUrl).load()

    def downloadDB(self):
        """Downloads the VPS database JSON."""
        self._cache.download_db()

    def downloadLastUpdate(self):
        """Fetches the last update version string from VPSdb."""
        return self._cache.fetch_last_update()

    def downloadMediaFile(self, tableId, url, filename):
        """Downloads a single media file by URL."""
        self._media_downloader.download_media_file(tableId, url, filename)

    # ----------------------------------------------------------------------
    # Local file helpers
    def fileExists(self, path):
        return self._media_downloader.file_exists(path)

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
        return self._media_downloader.download_media(
            tableId,
            metadata,
            key,
            filename,
            defaultFilename,
            metaConfig,
            mediaType,
        )

    def downloadMediaForTable(self, table, id, metaConfig=None):
        """Download all associated media for a given table."""
        self._media_downloader.download_media_for_table(table, id, metaConfig)

    # ----------------------------------------------------------------------
    def updateTable(self, name, manufacturer, year):
        """UI hook: updates progress label (requires UI integration)."""
        self.progress_table_label.config(text=f"{name}\n({manufacturer} {year})")
