import hashlib
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from common.online.vpsdb_media import VPSMediaDownloader


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
            tabletype="table", tableresolution="1k", tablevideoresolution="1k",
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
                    str(wheel), str(wheel), meta_config=None, media_type="wheel")
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
                                  str(wheel), str(wheel), meta_config=None,
                                  media_type="wheel")
            self.assertTrue(fetch.called)


class RecordingTests(unittest.TestCase):
    def test_only_files_we_placed_are_recorded_as_ours(self) -> None:
        """download_media returns None for anything it declined to touch, and record()
        writes nothing for None - so the ledger cannot claim a file we never wrote."""
        with TemporaryDirectory() as tmp:
            wheel = Path(tmp) / "wheel.png"
            wheel.write_bytes(THEIRS)
            dl = VPSMediaDownloader(
                {"vps-1": {"wheel": "https://example.invalid/wheel.png",
                           "wheel_md5": _md5(OURS)}},
                tabletype="table", tableresolution="1k", tablevideoresolution="1k")
            meta = mock.Mock()
            with mock.patch.object(dl, "download_media_file"):
                result = dl.download_media("vps-1", dl.media_index["vps-1"], "wheel",
                                           str(wheel), str(wheel), meta_config=meta,
                                           media_type="wheel")
            self.assertIsNone(result)
            meta.addMedia.assert_not_called()


if __name__ == "__main__":
    unittest.main()
