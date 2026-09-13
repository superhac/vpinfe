import configparser
import hashlib
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from common.online.vpsdb_cache import VPSDatabaseCache
from common.online.vpsdb_media import (
    REMOTE_KEYS,
    VPSMediaDownloader,
    offered,
    published_url,
)
from tests.support.library import fake_game


def _md5(data: bytes) -> str:
    return hashlib.md5(data).hexdigest()


OURS = b"\x89PNG the wheel vpinmediadb publishes"
THEIRS = b"\x89PNG a wheel someone drew themselves"


class OwnershipTests(unittest.TestCase):
    """Whether a media file may be overwritten is decided by comparing its hash to the
    one vpinmediadb publishes, never by whether we happen to have a ledger entry.

    Absence proves nothing. vpinmediadb artwork loses its entry whenever a table folder
    is copied, an .info is regenerated, or the media came from another tool - and
    reading "no entry" as "the user's" would freeze that art with nobody able to tell.
    """

    def _downloader(self, remote_md5: str):
        return VPSMediaDownloader(
            {"vps-1": {"wheel": "https://example.invalid/wheel.png",
                       "wheel_md5": remote_md5}},
            playfieldvariant="table", playfieldresolution="1k", playfieldvideoresolution="1k",
        )

    def _run(self, on_disk: bytes, remote_md5: str):
        """Returns (result, bytes still on disk, whether a download was attempted)."""
        with TemporaryDirectory() as tmp:
            wheel = Path(tmp) / "wheel.png"
            wheel.write_bytes(on_disk)
            dl = self._downloader(remote_md5)
            with mock.patch.object(dl, "download_media_file") as fetch:
                result = dl.download_media(
                    "vps-1", dl.media_index["vps-1"], "wheel",
                    str(wheel), str(wheel))
            return result, wheel.read_bytes(), fetch.called

    def test_a_users_own_artwork_is_left_alone_and_never_claimed(self) -> None:
        """The bug this fixes: an unrecorded file was treated as ours, stamped with the
        remote hash without being downloaded, then overwritten on the next sync."""
        result, on_disk, fetched = self._run(THEIRS, _md5(OURS))

        self.assertIsNone(result, "returning nothing is what stops record() claiming it")
        self.assertEqual(on_disk, THEIRS, "the user's file must survive untouched")
        self.assertFalse(fetched)

    def test_our_own_artwork_stays_managed_without_a_ledger_entry(self) -> None:
        """The regression the naive fix would have caused: treating absence as the
        user's would freeze vpinmediadb art whose entry was lost, forever."""
        result, _, fetched = self._run(OURS, _md5(OURS))

        self.assertIsNotNone(result, "hashes match, so this is demonstrably our file")
        self.assertEqual(result[1], _md5(OURS))
        self.assertFalse(fetched, "already current - nothing to fetch")

    def test_without_a_remote_hash_we_cannot_prove_ownership(self) -> None:
        """Silence protects. An index entry with no md5 is not evidence."""
        result, on_disk, fetched = self._run(THEIRS, "")

        self.assertIsNone(result)
        self.assertEqual(on_disk, THEIRS)
        self.assertFalse(fetched)

    def test_a_missing_file_is_still_downloaded(self) -> None:
        """Ownership only gates files that already exist; a gap is still filled."""
        with TemporaryDirectory() as tmp:
            wheel = Path(tmp) / "wheel.png"
            dl = self._downloader(_md5(OURS))
            with mock.patch.object(dl, "download_media_file") as fetch:
                dl.download_media("vps-1", dl.media_index["vps-1"], "wheel",
                                  str(wheel), str(wheel))
            self.assertTrue(fetch.called)


class RemoteVocabularyTests(unittest.TestCase):
    """The keys we index vpinmediadb's manifest with are its words, not ours.

    A rename of our own media kinds once swept three of these in with them, and
    nothing failed: `download_media` returns None for a key an entry does not carry,
    so the whole symptom was art that never arrived. This is the guard - an entry
    carrying the manifest's real vocabulary, and every kind in it expected to land.
    """

    # One entry in the shape vpinmdb.json actually publishes: resolution buckets
    # holding bg/dmd/table/fss and the videos, the rest at the top level.
    ENTRY = {
        "1k": {"bg": "https://example.invalid/bg.png",
               "dmd": "https://example.invalid/dmd.png",
               "table": "https://example.invalid/table.png",
               "dmd_video": "https://example.invalid/dmd.mp4",
               "table_video": "https://example.invalid/table.mp4"},
        "4k": {"table": "https://example.invalid/table4k.png"},
        "wheel": "https://example.invalid/wheel.png",
        "cab": "https://example.invalid/cab.png",
        "flyer": "https://example.invalid/flyer.png",
        "audio": "https://example.invalid/audio.mp3",
        "realdmd": "https://example.invalid/realdmd.png",
        "realdmd_color": "https://example.invalid/realdmd-color.png",
    }

    def _fetched(self) -> set[str]:
        with TemporaryDirectory() as tmp:
            game = fake_game(tmp, BGImagePath=None, DMDImagePath=None,
                             WheelImagePath=None, CabImagePath=None,
                             realDMDImagePath=None, realDMDColorImagePath=None,
                             FlyerImagePath=None, PlayfieldImagePath=None,
                             PlayfieldVideoPath=None, DMDVideoPath=None,
                             AudioPath=None)
            dl = VPSMediaDownloader({"vps-1": self.ENTRY}, playfieldvariant="table",
                                    playfieldresolution="1k",
                                    playfieldvideoresolution="1k")
            with mock.patch.object(dl, "download_media_file") as fetch:
                dl.download_media_for_game(game, "vps-1")
            return {Path(call.args[2]).name for call in fetch.call_args_list}

    def test_every_kind_the_manifest_offers_is_fetched(self) -> None:
        self.assertEqual(
            self._fetched(),
            {"bg.png", "dmd.png", "wheel.png", "cab.png", "flyer.png", "audio.mp3",
             "realdmd.png", "realdmd-color.png", "table.png", "dmd.mp4", "table.mp4"},
        )

    def test_the_manifests_words_are_pinned_against_a_rename_of_ours(self) -> None:
        """The whole mapping, so changing one of our kind names fails here and says
        why rather than quietly asking vpinmediadb for a key it has never had."""
        self.assertEqual(REMOTE_KEYS, {
            "backglass": "bg", "scoreview": "dmd", "scoreview_video": "dmd_video",
            "playfield": "table", "playfield_fss": "fss",
            "playfield_video": "table_video", "wheel": "wheel", "cab": "cab",
            "flyer": "flyer", "audio": "audio", "real_dmd": "realdmd",
            "real_dmd_color": "realdmd_color",
        })

    def test_a_kind_the_catalog_does_not_carry_is_absent_rather_than_empty(self) -> None:
        """vpinmediadb has no topper at all. Reporting it as an option with nothing
        behind it would put a dead choice in front of someone."""
        self.assertNotIn("topper", offered({"vps-1": self.ENTRY}, "vps-1"))
        self.assertIsNone(published_url({"vps-1": self.ENTRY}, "vps-1", "topper"))

    def test_every_size_an_entry_carries_is_offered_largest_first(self) -> None:
        """The configured resolution is right for an unattended refresh and wrong for
        someone choosing a picture, so the catalog reports both."""
        playfield = offered({"vps-1": self.ENTRY}, "vps-1")["playfield"]
        self.assertEqual([item["size"] for item in playfield], ["4k", "1k"])
        self.assertEqual(published_url({"vps-1": self.ENTRY}, "vps-1", "playfield")[0],
                         "https://example.invalid/table4k.png")


class RecordingTests(unittest.TestCase):
    """What reaches the assets ledger, going through the real recording path."""

    def _game(self, root: Path):
        """Enough of a Game for download_media_for_game. Every media path points at
        the canonical name; only the wheel exists on disk in these tests."""
        paths = {"BGImagePath": "bg.png", "DMDImagePath": "dmd.png",
                 "WheelImagePath": "wheel.png", "CabImagePath": "cab.png",
                 "realDMDImagePath": "realdmd.png",
                 "realDMDColorImagePath": "realdmd-color.png",
                 "FlyerImagePath": "flyer.png", "PlayfieldImagePath": "table.png",
                 "DMDVideoPath": "dmd.mp4", "PlayfieldVideoPath": "table.mp4",
                 "AudioPath": "audio.mp3"}
        game = fake_game(root, root.name)
        for attr, name in paths.items():
            setattr(game, attr, str(root / "medias" / name))
        return game

    def _downloader(self, remote_md5: str):
        return VPSMediaDownloader(
            {"vps-1": {"wheel": "https://example.invalid/wheel.png",
                       "wheel_md5": remote_md5}},
            playfieldvariant="table", playfieldresolution="1k", playfieldvideoresolution="1k")

    def test_a_file_we_never_wrote_is_not_recorded_as_ours(self) -> None:
        """download_media returns None for anything it declined to touch, and record()
        writes nothing for None - so the ledger cannot claim a user's artwork."""
        with TemporaryDirectory() as tmp:
            root = Path(tmp) / "Cactus Canyon (Bally 1998)"
            (root / "medias").mkdir(parents=True)
            (root / "medias" / "wheel.png").write_bytes(THEIRS)
            dl = self._downloader(_md5(OURS))
            meta = mock.Mock()
            with mock.patch.object(dl, "download_media_file"):
                dl.download_media_for_game(self._game(root), "vps-1", meta)

            meta.add_asset.assert_not_called()

    def test_a_file_we_placed_is_recorded_by_path_with_its_hash(self) -> None:
        """The entry is keyed by where the file went, not by which kind it is - a kind
        cannot say which build's artwork it means."""
        with TemporaryDirectory() as tmp:
            root = Path(tmp) / "Cactus Canyon (Bally 1998)"
            (root / "medias").mkdir(parents=True)
            (root / "medias" / "wheel.png").write_bytes(OURS)
            dl = self._downloader(_md5(OURS))
            meta = mock.Mock()
            with mock.patch.object(dl, "download_media_file"):
                dl.download_media_for_game(self._game(root), "vps-1", meta)

            meta.add_asset.assert_called_once_with(
                str(root / "medias" / "wheel.png"), "vpinmediadb", _md5(OURS))


class _FakeIni:
    def __init__(self) -> None:
        self.config = configparser.ConfigParser()
        self.saved = False

    def save(self) -> None:
        self.saved = True


class VpsCacheTests(unittest.TestCase):
    def test_vps_cache_loads_local_list_without_network_version(self) -> None:
        with TemporaryDirectory() as tmp:
            config_dir = Path(tmp)
            (config_dir / "vpsdb.json").write_text(
                json.dumps([{"id": "vps-1", "name": "Example"}]),
                encoding="utf-8",
            )
            cache = VPSDatabaseCache(
                config_dir,
                _FakeIni(),
                db_url="https://example.invalid/db.json",
                last_update_url="https://example.invalid/last.json",
            )

            with mock.patch.object(cache, "fetch_last_update", return_value=None):
                self.assertEqual(cache.ensure_current(), [{"id": "vps-1", "name": "Example"}])

if __name__ == "__main__":
    unittest.main()
