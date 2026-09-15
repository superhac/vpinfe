"""The Virtual Pinball Spreadsheet: the community database VPinFE matches games against."""

import logging
import re
from difflib import SequenceMatcher
from typing import Any

from common.config_access import MediaConfig
from common.config_store import ConfigStore
from common.games.game import Game
from common.games.info_file import MetaConfig
from common.online import vpsdb_media
from common.online.vpsdb_cache import VPinMediaDatabase, VPSDatabaseCache
from common.online.vpsdb_media import VPSMediaDownloader
from common.paths import CONFIG_DIR

logger = logging.getLogger("vpinfe.common.online.vpsdb")


class VPSdb:
    """
    VPSdb class handles downloading, caching, and querying the Virtual Pinball Spreadsheet (VPS) database
    along with associated media assets via VPinMediaDB.
    """

    # Declared, not defaulted: __init__ always sets all three, and `= None` gave every
    # one of them a type it never actually holds.
    root_game_dir: str
    data: list[dict]
    _vpinfe_config_store: ConfigStore

    VPS_LAST_UPDATE_URL = "https://raw.githubusercontent.com/VirtualPinballSpreadsheet/vps-db/refs/heads/main/lastUpdated.json"
    VPS_DB_URL = "https://github.com/VirtualPinballSpreadsheet/vps-db/raw/refs/heads/main/db/vpsdb.json"
    VPINMDB_URL = vpsdb_media.MANIFEST_URL

    def __init__(self, root_game_dir: str,
                 vpinfe_config_store: ConfigStore) -> None:
        logger.info("Initializing VPSdb")

        self._vpinfe_config_store = vpinfe_config_store
        self._config_dir = CONFIG_DIR
        self._config_dir.mkdir(parents=True, exist_ok=True)
        self._cache = VPSDatabaseCache(
            self._config_dir,
            self._vpinfe_config_store,
            db_url=VPSdb.VPS_DB_URL,
            last_update_url=VPSdb.VPS_LAST_UPDATE_URL,
        )
        self._vpsdb_path = self._cache.path
        self.root_game_dir = root_game_dir
        self.data = self._cache.ensure_current()
        logger.info("Total VPSdb entries: %s", len(self.data))
        self._write_manufacturer_reference()

        # Setup preferences
        media_config = MediaConfig.from_config(self._vpinfe_config_store)
        self.playfieldvariant = media_config.playfield_variant
        self.playfieldresolution = media_config.playfield_resolution
        self.playfieldvideoresolution = media_config.playfield_video_resolution
        logger.info(
            "Using %s/%s tables (video: %s)",
            self.playfieldresolution,
            self.playfieldvariant,
            self.playfieldvideoresolution,
        )

        self.vpinmediadbjson = self.download_media_json()
        self._media_downloader = VPSMediaDownloader(
            self.vpinmediadbjson,
            playfieldvariant=self.playfieldvariant,
            playfieldresolution=self.playfieldresolution,
            playfieldvideoresolution=self.playfieldvideoresolution,
        )

    def _write_manufacturer_reference(self) -> None:
        """Refresh the human-readable slug/alias/logo reference after a sync.

        Best-effort: a no-op when the shared assets root is not configured, and
        never allowed to break loading the database.
        """
        try:
            from common.shared_assets import write_manufacturer_reference
            names = {str(t.get("manufacturer", "")) for t in self.data or []
                     if isinstance(t, dict)}
            write_manufacturer_reference(names)
        except Exception:
            logger.exception("Could not write the manufacturer reference")

    # ----------------------------------------------------------------------
    # Python container magic methods
    def __len__(self) -> int:
        return len(self.data) if self.data else 0

    def __contains__(self, item: object) -> bool:
        return item in self.data if self.data else False

    def games(self) -> list[dict]:
        return self.data

    # ----------------------------------------------------------------------
    # Game lookups
    def lookup_name(self, name: str, manufacturer: str, year: object) -> dict | None:
        """Fuzzy search for a game by name, manufacturer, and year."""
        if not all((name, manufacturer, year)):
            return None

        for game in self.data or []:
            # Compare game names
            if SequenceMatcher(None, name.lower(), game["name"].lower()).ratio() < 0.8:
                continue

            # Compare manufacturers
            if SequenceMatcher(None, manufacturer.lower(), game["manufacturer"].lower()).ratio() < 0.8:
                continue

            # Compare year
            if SequenceMatcher(None, str(year), str(game["year"])).ratio() >= 0.8:
                return game

        logger.debug("No match found for: %s", name)
        return None

    def parse_game_name_from_dir(self, directory_name: str) -> dict[str, Any] | None:
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
    def download_media_json(self) -> dict | None:
        """Downloads the VPinMediaDB JSON index."""
        return VPinMediaDatabase(self.VPINMDB_URL).load()

    def download_db(self) -> None:
        """Downloads the VPS database JSON."""
        self._cache.download_db()

    def download_last_update(self) -> str | None:
        """Fetches the last update version string from VPSdb."""
        return self._cache.fetch_last_update()

    def download_media_file(self, game_id: str, url: str, filename: str) -> None:
        """Downloads a single media file by URL."""
        self._media_downloader.download_media_file(game_id, url, filename)

    # ----------------------------------------------------------------------
    # Local file helpers
    def file_exists(self, path: str | None) -> bool:
        return self._media_downloader.file_exists(path)

    def download_media_for_game(self, game: Game, id: str,
                               meta_config: MetaConfig | None = None) -> None:
        """Download all associated media for a given game."""
        self._media_downloader.download_media_for_game(game, id, meta_config)

