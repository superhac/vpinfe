from __future__ import annotations

import hashlib
import logging
import os
from pathlib import Path

import requests

from common.http_client import download_file
from common.media_paths import default_media_path


logger = logging.getLogger("vpinfe.common.online.vpsdb_media")


class VPSMediaDownloader:
    def __init__(self, media_index: dict | None, *, tabletype: str, tableresolution: str, tablevideoresolution: str) -> None:
        self.media_index = media_index or {}
        self.tabletype = tabletype
        self.tableresolution = tableresolution
        self.tablevideoresolution = tablevideoresolution

    def file_exists(self, path) -> bool:
        return bool(path and os.path.exists(path))

    def download_media_file(self, table_id, url, filename) -> None:
        logger.info("Downloading %s from %s", filename, url)
        try:
            download_file(url, Path(filename))
            logger.info("Successfully downloaded %s from VPinMedia", filename)
        except requests.RequestException as exc:
            logger.warning("Failed to download %s for table %s: %s", filename, table_id, exc)

    def local_md5(self, path) -> str:
        """The file's own hash, or "" when it cannot be read."""
        try:
            with open(path, "rb") as handle:
                digest = hashlib.md5()
                for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                    digest.update(chunk)
                return digest.hexdigest()
        except OSError:
            logger.debug("Could not hash %s", path, exc_info=True)
            return ""

    def is_ours(self, path, remote_md5) -> bool:
        """Whether a file on disk is the one vpinmediadb publishes.

        Decided by comparing hashes, not by whether we have a ledger entry for it.
        Absence proves nothing - a copied table folder, a regenerated .info or media
        fetched with another tool all leave vpinmediadb art with no record - and
        treating "no entry" as "the user's" would freeze that art forever with no
        way for anyone to notice.

        No remote hash means we cannot prove ownership, so the answer is no.
        """
        return bool(remote_md5) and self.local_md5(path) == remote_md5

    def download_media(self, table_id, metadata, key, filename, default_filename, meta_config=None, media_type=None):
        if not metadata or key not in metadata:
            return None

        remote_md5 = metadata.get(f"{key}_md5", "")
        actual_path = filename if self.file_exists(filename) else (default_filename if self.file_exists(default_filename) else None)

        if actual_path:
            if not self.is_ours(actual_path, remote_md5):
                # Either the user's own artwork, or a newer copy of ours they replaced.
                # Both mean hands off, and neither should be recorded as ours.
                logger.debug("Leaving %s alone: not the file vpinmediadb publishes", actual_path)
                return None
            # Ours and already current - the hashes match, so there is nothing to fetch.
            return actual_path, remote_md5

        self.download_media_file(table_id, metadata[key], default_filename)
        if self.file_exists(default_filename):
            return default_filename, remote_md5
        return None

    def download_media_for_table(self, table, table_id, meta_config=None) -> None:
        if table_id not in self.media_index:
            logger.info("No media exists for %s (ID %s).", table.fullPathTable, table_id)
            return

        table_media = self.media_index[table_id]
        medias_dir = os.path.join(table.fullPathTable, "medias")
        os.makedirs(medias_dir, exist_ok=True)

        def record(media_type, result):
            """Only files we actually placed. download_media returns None for anything
            it declined to touch, so a user's artwork is never claimed as ours."""
            if result and meta_config:
                path, md5hash = result
                meta_config.addMedia(media_type, "vpinmediadb", path, md5hash)

        def process(media_type, metadata, key, filename, default_filename):
            record(media_type, self.download_media(table_id, metadata, key, filename,
                                                   default_filename, meta_config, media_type))

        process("bg", table_media.get("1k"), "bg", table.BGImagePath, str(default_media_path(table.fullPathTable, "bg", self.tabletype)))
        process("dmd", table_media.get("1k"), "dmd", table.DMDImagePath, str(default_media_path(table.fullPathTable, "dmd", self.tabletype)))
        process("wheel", table_media, "wheel", table.WheelImagePath, str(default_media_path(table.fullPathTable, "wheel", self.tabletype)))
        process("cab", table_media, "cab", table.CabImagePath, str(default_media_path(table.fullPathTable, "cab", self.tabletype)))
        process("realdmd", table_media, "realdmd", table.realDMDImagePath, str(default_media_path(table.fullPathTable, "realdmd", self.tabletype)))
        process("realdmd_color", table_media, "realdmd_color", table.realDMDColorImagePath, str(default_media_path(table.fullPathTable, "realdmd_color", self.tabletype)))
        process("flyer", table_media, "flyer", table.FlyerImagePath, str(default_media_path(table.fullPathTable, "flyer", self.tabletype)))
        process(self.tabletype, table_media.get(self.tableresolution), self.tabletype, table.TableImagePath, str(default_media_path(table.fullPathTable, self.tabletype, self.tabletype)))
        # Videos, and only the ones the index actually carries. There has never been
        # a bg_video at any resolution, so the backglass video is yours to supply.
        # Nor is there an fss_video: under table type fss the playfield video is
        # simply not offered, and asking would quietly fetch nothing.
        process("dmd_video", table_media.get(self.tablevideoresolution), "dmd_video", table.DMDVideoPath, str(default_media_path(table.fullPathTable, "dmd_video", self.tabletype)))
        if self.tabletype == "table":
            process("table_video", table_media.get(self.tablevideoresolution), "table_video", table.TableVideoPath, str(default_media_path(table.fullPathTable, "table_video", self.tabletype)))
        process("audio", table_media, "audio", table.AudioPath, str(default_media_path(table.fullPathTable, "audio", self.tabletype)))
