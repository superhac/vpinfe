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
    def __init__(self, media_index: dict | None, *, playfieldvariant: str, playfieldresolution: str, playfieldvideoresolution: str) -> None:
        self.media_index = media_index or {}
        self.playfieldvariant = playfieldvariant
        self.playfieldresolution = playfieldresolution
        self.playfieldvideoresolution = playfieldvideoresolution

    def file_exists(self, path) -> bool:
        return bool(path and os.path.exists(path))

    def download_media_file(self, game_id, url, filename) -> None:
        logger.info("Downloading %s from %s", filename, url)
        try:
            download_file(url, Path(filename))
            logger.info("Successfully downloaded %s from VPinMedia", filename)
        except requests.RequestException as exc:
            logger.warning("Failed to download %s for table %s: %s", filename, game_id, exc)

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

    def download_media(self, game_id, metadata, key, filename, default_filename):
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

        self.download_media_file(game_id, metadata[key], default_filename)
        if self.file_exists(default_filename):
            return default_filename, remote_md5
        return None

    def download_media_for_game(self, game, game_id, meta_config=None) -> None:
        if game_id not in self.media_index:
            logger.info("No media exists for %s (ID %s).", game.fullPathGame, game_id)
            return

        game_media = self.media_index[game_id]
        medias_dir = os.path.join(game.fullPathGame, "medias")
        os.makedirs(medias_dir, exist_ok=True)

        def record(result):
            """Only files we actually placed. download_media returns None for anything
            it declined to touch, so a user's artwork is never claimed as ours."""
            if result and meta_config:
                path, md5hash = result
                meta_config.add_asset(path, "vpinmediadb", md5hash)

        # The ledger is keyed by path now, so the kind no longer has to be passed along
        # to be recorded - it was the same value as `key` at every call site anyway.
        def process(metadata, key, filename, default_filename):
            record(self.download_media(game_id, metadata, key, filename, default_filename))

        process(game_media.get("1k"), "bg", game.BGImagePath, str(default_media_path(game.fullPathGame, "bg", self.playfieldvariant)))
        process(game_media.get("1k"), "dmd", game.DMDImagePath, str(default_media_path(game.fullPathGame, "dmd", self.playfieldvariant)))
        process(game_media, "wheel", game.WheelImagePath, str(default_media_path(game.fullPathGame, "wheel", self.playfieldvariant)))
        process(game_media, "cab", game.CabImagePath, str(default_media_path(game.fullPathGame, "cab", self.playfieldvariant)))
        process(game_media, "realdmd", game.realDMDImagePath, str(default_media_path(game.fullPathGame, "realdmd", self.playfieldvariant)))
        process(game_media, "realdmd_color", game.realDMDColorImagePath, str(default_media_path(game.fullPathGame, "realdmd_color", self.playfieldvariant)))
        process(game_media, "flyer", game.FlyerImagePath, str(default_media_path(game.fullPathGame, "flyer", self.playfieldvariant)))
        process(game_media.get(self.playfieldresolution), self.playfieldvariant, game.PlayfieldImagePath, str(default_media_path(game.fullPathGame, self.playfieldvariant, self.playfieldvariant)))
        # Videos, and only the ones the index actually carries. There has never been
        # a bg_video at any resolution, so the backglass video is yours to supply.
        # Nor is there an fss_video: under table type fss the playfield video is
        # simply not offered, and asking would quietly fetch nothing.
        process(game_media.get(self.playfieldvideoresolution), "dmd_video", game.DMDVideoPath, str(default_media_path(game.fullPathGame, "dmd_video", self.playfieldvariant)))
        if self.playfieldvariant == "table":
            process(game_media.get(self.playfieldvideoresolution), "table_video", game.PlayfieldVideoPath, str(default_media_path(game.fullPathGame, "table_video", self.playfieldvariant)))
        process(game_media, "audio", game.AudioPath, str(default_media_path(game.fullPathGame, "audio", self.playfieldvariant)))
