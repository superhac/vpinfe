"""Downloading a game's media from VPinMediaDB, at the resolution the display wants."""

from __future__ import annotations

import hashlib
import logging
import os
from pathlib import Path

import requests

from common.http_client import download_file
from common.media_specs import default_media_path

logger = logging.getLogger("vpinfe.common.online.vpsdb_media")


# Where the manifest is published. One name for it, so the downloader and anything
# browsing the catalog cannot end up pointed at different copies.
MANIFEST_URL = "https://github.com/superhac/vpinmediadb/raw/refs/heads/main/vpinmdb.json"

# Our media kinds against vpinmediadb's, and whether the entry files it under a
# resolution. This is the manifest's vocabulary, not ours: it calls the backglass "bg"
# and the score view "dmd", and a rename of our own windows to VPX's words once swept
# those in with them. Nothing complained - `download_media` returns None for a key an
# entry does not carry - so the whole symptom was art that never arrived, on the asset
# vpinmediadb publishes for all but two of the games it knows.
MANIFEST_KINDS: dict[str, tuple[str, bool]] = {
    "backglass": ("bg", True),
    "scoreview": ("dmd", True),
    "scoreview_video": ("dmd_video", True),
    "playfield": ("table", True),
    "playfield_fss": ("fss", True),
    "playfield_video": ("table_video", True),
    "wheel": ("wheel", False),
    "cab": ("cab", False),
    "flyer": ("flyer", False),
    "audio": ("audio", False),
    "real_dmd": ("realdmd", False),
    "real_dmd_color": ("realdmd_color", False),
}

REMOTE_KEYS = {kind: key for kind, (key, _) in MANIFEST_KINDS.items()}

# The resolutions an entry files art under, largest first - which is the order to
# offer them in, since the bigger one is the better one when it exists.
MANIFEST_SIZES = ("4k", "1k")


def offered(media_index: dict | None, vps_id: str) -> dict[str, list[dict]]:
    """What vpinmediadb publishes for one VPS id: our kind -> the files, largest first.

    Every size the entry actually carries, not the one the display is configured for.
    The configured size is right for an unattended refresh and wrong for someone
    standing at the screen choosing a picture.
    """
    entry = (media_index or {}).get(vps_id) or {}
    found: dict[str, list[dict]] = {}
    for kind, (key, bucketed) in MANIFEST_KINDS.items():
        options = []
        for size in (MANIFEST_SIZES if bucketed else ("",)):
            source = entry.get(size) if bucketed else entry
            if not isinstance(source, dict):
                continue
            url = source.get(key)
            if url:
                options.append({"size": size, "url": url,
                                "md5": source.get(f"{key}_md5", "")})
        if options:
            found[kind] = options
    return found


def published_url(media_index: dict | None, vps_id: str, kind: str,
                  size: str = "") -> tuple[str, str] | None:
    """The URL and hash vpinmediadb publishes for one kind, or None.

    The catalog is the only source of a URL this app will fetch. A caller names an
    entry, a kind and a size; it never hands over a link of its own.
    """
    options = offered(media_index, vps_id).get(kind) or []
    if not options:
        return None
    pick = next((item for item in options if item["size"] == size), options[0])
    return pick["url"], pick["md5"]


class VPSMediaDownloader:
    """Downloads a game's media from VPinMediaDB."""

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
        Absence proves nothing - a copied game folder, a regenerated .info or media
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

        # `key` indexes the remote manifest, so it is vpinmediadb's word for the thing
        # and not ours. They differ for three of them - see REMOTE_KEYS. The kind is no
        # longer passed for the ledger, which is keyed by path.
        def process(metadata, key, filename, default_filename):
            record(self.download_media(game_id, metadata, key, filename, default_filename))

        process(game_media.get("1k"), REMOTE_KEYS["backglass"], game.BGImagePath,
                str(default_media_path(game.fullPathGame, "backglass", self.playfieldvariant)))
        process(game_media.get("1k"), REMOTE_KEYS["scoreview"], game.DMDImagePath,
                str(default_media_path(game.fullPathGame, "scoreview", self.playfieldvariant)))
        process(game_media, "wheel", game.WheelImagePath, str(default_media_path(game.fullPathGame, "wheel", self.playfieldvariant)))
        process(game_media, "cab", game.CabImagePath, str(default_media_path(game.fullPathGame, "cab", self.playfieldvariant)))
        process(game_media, "realdmd", game.realDMDImagePath, str(default_media_path(game.fullPathGame, "real_dmd", self.playfieldvariant)))
        process(game_media, "realdmd_color", game.realDMDColorImagePath, str(default_media_path(game.fullPathGame, "real_dmd_color", self.playfieldvariant)))
        process(game_media, "flyer", game.FlyerImagePath, str(default_media_path(game.fullPathGame, "flyer", self.playfieldvariant)))
        process(game_media.get(self.playfieldresolution), self.playfieldvariant, game.PlayfieldImagePath, str(default_media_path(game.fullPathGame, "playfield", self.playfieldvariant)))
        # Videos, and only the ones the index actually carries. There has never been
        # a bg_video at any resolution, so the backglass video is yours to supply.
        # Nor is there an fss_video: under table type fss the playfield video is
        # simply not offered, and asking would quietly fetch nothing.
        scoreview_video = default_media_path(game.fullPathGame, "scoreview_video",
                                             self.playfieldvariant)
        process(game_media.get(self.playfieldvideoresolution),
                REMOTE_KEYS["scoreview_video"], game.DMDVideoPath, str(scoreview_video))
        if self.playfieldvariant == "table":
            process(game_media.get(self.playfieldvideoresolution), "table_video", game.PlayfieldVideoPath, str(default_media_path(game.fullPathGame, "playfield_video", self.playfieldvariant)))
        process(game_media, "audio", game.AudioPath, str(default_media_path(game.fullPathGame, "audio", self.playfieldvariant)))
