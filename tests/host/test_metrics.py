from __future__ import annotations

import contextlib
import json
import subprocess
import unittest
from collections.abc import Iterator
from unittest import mock

from common.host import about, metrics


@contextlib.contextmanager
def _nvtop(cards: list) -> Iterator[None]:
    done = subprocess.CompletedProcess(["nvtop", "-s"], 0, stdout=json.dumps(cards),
                                       stderr="")
    with mock.patch.object(metrics.platform, "system", return_value="Linux"), \
            mock.patch.object(metrics.shutil, "which", return_value="/usr/bin/nvtop"), \
            mock.patch.object(metrics.subprocess, "run", return_value=done):
        yield


def _names(cards: list) -> list[str]:
    with _nvtop(cards):
        return [card["name"] for card in metrics.gpu()["gpus"]]


class UnnamedCardTests(unittest.TestCase):
    def test_two_unnamed_cards_read_apart(self) -> None:
        self.assertEqual(_names([{"gpu_util": "10%"}, {"device_name": None}]),
                         ["Card 1", "Card 2"])

    def test_a_named_card_keeps_its_name_beside_an_unnamed_one(self) -> None:
        self.assertEqual(_names([{"device_name": "Radeon Pro 5500M"}, {"device_name": ""}]),
                         ["Radeon Pro 5500M", "Card 2"])

    def test_a_lone_unnamed_card_is_unknown(self) -> None:
        self.assertEqual(_names([{"temp": "40C"}]), ["Unknown"])

    def test_about_names_each_card(self) -> None:
        with _nvtop([{}, {}]):
            self.assertEqual(about._graphics(), "Card 1, Card 2")


if __name__ == "__main__":
    unittest.main()
