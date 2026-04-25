from __future__ import annotations

import logging
import os
from pathlib import Path

import requests

from common.http_client import download_file


logger = logging.getLogger("vpinfe.common.vpsdb_media")


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

    def download_media(self, table_id, metadata, key, filename, default_filename, meta_config=None, media_type=None):
        if not metadata or key not in metadata:
            return None

        remote_md5 = metadata.get(f"{key}_md5", "")
        actual_path = filename if self.file_exists(filename) else (default_filename if self.file_exists(default_filename) else None)

        if actual_path:
            if meta_config and media_type and remote_md5:
                existing = meta_config.getMedia(media_type)
                if existing and existing.get("Source") == "vpinmediadb":
                    stored_md5 = existing.get("MD5Hash", "")
                    if stored_md5 and stored_md5 != remote_md5:
                        logger.info(
                            "MD5 changed for %s (%s -> %s), re-downloading",
                            media_type,
                            stored_md5,
                            remote_md5,
                        )
                        self.download_media_file(table_id, metadata[key], actual_path)
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

        def is_user_media(media_type):
            if not meta_config:
                return False
            existing = meta_config.getMedia(media_type)
            return existing is not None and existing.get("Source") != "vpinmediadb"

        def record(media_type, result):
            if result and meta_config:
                path, md5hash = result
                meta_config.addMedia(media_type, "vpinmediadb", path, md5hash)

        def process(media_type, metadata, key, filename, default_filename):
            if is_user_media(media_type):
                logger.debug("Skipping %s: user-provided media", media_type)
                return
            result = self.download_media(table_id, metadata, key, filename, default_filename, meta_config, media_type)
            record(media_type, result)

        process("bg", table_media.get("1k"), "bg", table.BGImagePath, f"{table.fullPathTable}/medias/bg.png")
        process("dmd", table_media.get("1k"), "dmd", table.DMDImagePath, f"{table.fullPathTable}/medias/dmd.png")
        process("wheel", table_media, "wheel", table.WheelImagePath, f"{table.fullPathTable}/medias/wheel.png")
        process("cab", table_media, "cab", table.CabImagePath, f"{table.fullPathTable}/medias/cab.png")
        process("realdmd", table_media, "realdmd", table.realDMDImagePath, f"{table.fullPathTable}/medias/realdmd.png")
        process("realdmd_color", table_media, "realdmd_color", table.realDMDColorImagePath, f"{table.fullPathTable}/medias/realdmd-color.png")
        process("flyer", table_media, "flyer", table.FlyerImagePath, f"{table.fullPathTable}/medias/flyer.png")
        process(self.tabletype, table_media.get(self.tableresolution), self.tabletype, table.TableImagePath, f"{table.fullPathTable}/medias/{self.tabletype}.png")
        process("bg_video", table_media.get(self.tablevideoresolution), "bg_video", table.BGVideoPath, f"{table.fullPathTable}/medias/bg.mp4")
        process("dmd_video", table_media.get(self.tablevideoresolution), "dmd_video", table.DMDVideoPath, f"{table.fullPathTable}/medias/dmd.mp4")
        process(f"{self.tabletype}_video", table_media.get(self.tablevideoresolution), f"{self.tabletype}_video", table.TableVideoPath, f"{table.fullPathTable}/medias/{self.tabletype}.mp4")
        process("audio", table_media, "audio", table.AudioPath, f"{table.fullPathTable}/medias/audio.mp3")
