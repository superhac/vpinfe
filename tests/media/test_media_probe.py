"""What a media file's own header says it is."""

from __future__ import annotations

import io
import struct
import tempfile
import unittest
from pathlib import Path

from common.media_probe import probe


def _box(kind: bytes, body: bytes) -> bytes:
    return struct.pack(">I4s", 8 + len(body), kind) + body


def _mvhd(scale: int, length: int, version: int = 0) -> bytes:
    if version == 1:
        body = bytes([1, 0, 0, 0]) + bytes(16) + struct.pack(">IQ", scale, length)
    else:
        body = bytes(4) + bytes(8) + struct.pack(">II", scale, length)
    return _box(b"mvhd", body + bytes(80))


def _tkhd(width: int, height: int) -> bytes:
    body = bytes(4) + bytes(20) + bytes(52) + struct.pack(">II", width << 16, height << 16)
    return _box(b"tkhd", body)


def _mp4(*, moov_last: bool = False, version: int = 0) -> bytes:
    moov = _box(b"moov", _mvhd(1000, 30_500, version)
                + _box(b"trak", _tkhd(0, 0))
                + _box(b"trak", _tkhd(1920, 1080)))
    head = _box(b"ftyp", b"isom" + bytes(4))
    media = _box(b"mdat", bytes(4096))
    return head + (media + moov if moov_last else moov + media)


# MPEG-1 Layer III, 128 kbps, 44.1 kHz, stereo: 417 bytes a frame, 1,152 samples.
_FRAME = b"\xff\xfb\x90\x00"
_FRAME_BYTES = 417


def _mp3(frames: int, *, xing: bool, id3: bool = False) -> bytes:
    first = bytearray(_FRAME + bytes(_FRAME_BYTES - 4))
    if xing:
        first[4 + 32:4 + 32 + 12] = b"Xing" + struct.pack(">II", 1, frames)
    audio = bytes(first) + (_FRAME + bytes(_FRAME_BYTES - 4)) * (frames - 1)
    tag = b"ID3\x04\x00\x00" + bytes([0, 0, 0, 20]) + bytes(20) if id3 else b""
    return tag + audio


def _ogg_page(granule: int, packet: bytes) -> bytes:
    return (b"OggS" + bytes(2) + struct.pack("<q", granule) + bytes(12)
            + bytes([1, len(packet)]) + packet)


def _vorbis(rate: int, samples: int) -> bytes:
    ident = b"\x01vorbis" + struct.pack("<IBI", 0, 2, rate) + bytes(15)
    return _ogg_page(0, ident) + _ogg_page(samples // 2, bytes(40)) \
        + _ogg_page(samples, bytes(40))


def _opus(skip: int, samples: int) -> bytes:
    ident = b"OpusHead" + bytes([1, 2]) + struct.pack("<HI", skip, 44_100) + bytes(3)
    return _ogg_page(0, ident) + _ogg_page(samples + skip, bytes(40))


class TheHeaderSaysWhatItIs(unittest.TestCase):
    def setUp(self) -> None:
        held = tempfile.TemporaryDirectory()
        self.addCleanup(held.cleanup)
        self.root = Path(held.name)

    def _probe(self, name: str, data: bytes) -> dict:
        path = self.root / name
        path.write_bytes(data)
        return probe(path)

    def test_a_video_has_its_size_and_running_time(self) -> None:
        facts = self._probe("table.mp4", _mp4())

        self.assertEqual(("MP4", 1920, 1080, 30.5),
                         (facts["format"], facts["width"], facts["height"],
                          facts["duration_s"]))

    def test_the_movie_header_is_found_after_the_media(self) -> None:
        self.assertEqual(30.5, self._probe("bg.mp4", _mp4(moov_last=True))["duration_s"])

    def test_a_wide_movie_header_is_read(self) -> None:
        self.assertEqual(30.5, self._probe("dmd.mp4", _mp4(version=1))["duration_s"])

    def test_a_variable_rate_sound_is_timed_by_its_frame_count(self) -> None:
        facts = self._probe("audio.mp3", _mp3(100, xing=True))

        self.assertEqual("MP3", facts["format"])
        self.assertAlmostEqual(100 * 1152 / 44_100, facts["duration_s"], places=3)

    def test_a_constant_rate_sound_is_timed_by_its_size(self) -> None:
        facts = self._probe("audio.mp3", _mp3(100, xing=False, id3=True))

        self.assertAlmostEqual(100 * _FRAME_BYTES * 8 / 128_000, facts["duration_s"],
                               places=2)

    def test_a_vorbis_sound_is_timed_by_its_last_page(self) -> None:
        facts = self._probe("audio.ogg", _vorbis(44_100, 88_200))

        self.assertEqual(("OGG", 2.0), (facts["format"], facts["duration_s"]))

    def test_an_opus_sound_leaves_out_what_it_skips(self) -> None:
        self.assertEqual(1.0, self._probe("audio.ogg", _opus(312, 48_000))["duration_s"])

    def test_an_image_says_what_it_really_is_not_what_it_is_named(self) -> None:
        from PIL import Image

        buffer = io.BytesIO()
        Image.new("RGB", (64, 48)).save(buffer, "JPEG")
        facts = self._probe("wheel.png", buffer.getvalue())

        self.assertEqual(("JPEG", 64, 48), (facts["format"], facts["width"],
                                            facts["height"]))

    def test_a_file_that_is_not_what_it_claims_falls_back_to_its_name(self) -> None:
        facts = self._probe("track01.mp3", b"not really a sound!!")

        self.assertEqual(("MP3", None), (facts["format"], facts["duration_s"]))

    def test_a_slot_detail_carries_them_beside_its_size(self) -> None:
        from common.games import media_ops

        path = self.root / "table.mp4"
        path.write_bytes(_mp4())
        facts = media_ops._file_facts(path)

        self.assertEqual(("MP4", 30.5, path.stat().st_size),
                         (facts["format"], facts["duration_s"], facts["size_bytes"]))

    def test_a_cut_off_video_costs_the_numbers_not_the_answer(self) -> None:
        facts = self._probe("table.mp4", _mp4()[:40])

        self.assertEqual(("MP4", None), (facts["format"], facts["duration_s"]))


if __name__ == "__main__":
    unittest.main()
