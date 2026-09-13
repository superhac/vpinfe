"""What a manifest has to say, and what it is told when it does not say it.

Every refusal carries a sentence, because the reader of one is somebody who installed
an extension and is looking at a list that says it is not running.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from common.extensions import contract

GOOD = {
    "name": "sample",
    "display_name": "Sample",
    "version": "1.0.0",
    "description": "Does nothing.",
    "requires_platform": contract.PLATFORM_ABI,
    "scopes": ["games:read"],
    "provides": ["read"],
    "capabilities": ["config:own"],
    "requires_features": ["library"],
    "platforms": ["linux"],
    "events": ["noticed"],
}


def _without(key: str, **changes) -> dict:
    raw = {name: value for name, value in GOOD.items() if name != key}
    raw.update(changes)
    return raw


class ParseTests(unittest.TestCase):
    def test_a_full_manifest_round_trips(self) -> None:
        manifest = contract.parse(GOOD)

        self.assertEqual(manifest.name, "sample")
        self.assertEqual(manifest.provides, ("read",))
        self.assertEqual(manifest.as_dict()["capabilities"], ["config:own"])

    def test_the_display_name_falls_back_to_the_name(self) -> None:
        self.assertEqual(contract.parse(_without("display_name")).display_name, "sample")

    def test_a_name_that_could_not_be_a_url_segment_is_refused(self) -> None:
        for bad in ("Sample", "two words", "9lives", "", "a/b"):
            with self.subTest(name=bad), self.assertRaises(contract.ManifestError):
                contract.parse(_without("name", name=bad))

    def test_an_abi_this_build_does_not_offer_is_refused(self) -> None:
        with self.assertRaises(contract.ManifestError) as caught:
            contract.parse(_without("requires_platform", requires_platform=99))

        self.assertIn("99", str(caught.exception))

    def test_a_capability_nobody_has_heard_of_is_refused(self) -> None:
        """The list is the consent surface, so an unknown entry is not a thing a user
        could have agreed to."""
        with self.assertRaises(contract.ManifestError) as caught:
            contract.parse(_without("capabilities", capabilities=["hardware:laser"]))

        self.assertIn("hardware:laser", str(caught.exception))

    def test_a_feature_that_does_not_exist_is_refused(self) -> None:
        with self.assertRaises(contract.ManifestError):
            contract.parse(_without("requires_features", requires_features=["catalog"]))

    def test_a_platform_that_does_not_exist_is_refused(self) -> None:
        with self.assertRaises(contract.ManifestError):
            contract.parse(_without("platforms", platforms=["amiga"]))

    def test_an_action_that_could_not_be_a_scope_is_refused(self) -> None:
        with self.assertRaises(contract.ManifestError):
            contract.parse(_without("provides", provides=["read:everything"]))

    def test_a_list_field_given_a_string_is_refused(self) -> None:
        with self.assertRaises(contract.ManifestError):
            contract.parse(_without("provides", provides="read"))


class ReadTests(unittest.TestCase):
    def test_a_missing_manifest_names_the_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(contract.ManifestError) as caught:
                contract.read_manifest(Path(tmp))

        self.assertIn(contract.MANIFEST_NAME, str(caught.exception))

    def test_a_manifest_that_is_not_json_says_so(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / contract.MANIFEST_NAME).write_text("{", encoding="utf-8")

            with self.assertRaises(contract.ManifestError):
                contract.read_manifest(Path(tmp))

    def test_a_manifest_on_disk_parses(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / contract.MANIFEST_NAME).write_text(json.dumps(GOOD),
                                                            encoding="utf-8")

            self.assertEqual(contract.read_manifest(Path(tmp)).name, "sample")


if __name__ == "__main__":
    unittest.main()
