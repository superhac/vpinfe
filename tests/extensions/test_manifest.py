"""What a manifest has to say, and what it is told when it does not say it.

Every refusal carries a catalog line, because the reader of one is somebody who
installed an extension and is looking at a list that says it is not running.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from common.extensions import contract
from common.i18n import t

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


def _said(refused: contract.ManifestError) -> str:
    return t(refused.key, **refused.values)


class ParseTests(unittest.TestCase):
    def test_a_full_manifest_round_trips(self) -> None:
        manifest = contract.parse(GOOD)

        self.assertEqual(manifest.name, "sample")
        self.assertEqual(manifest.provides, ("read",))
        self.assertEqual(manifest.as_dict()["capabilities"], ["config:own"])

    def test_a_display_name_left_out_stays_empty(self) -> None:
        """So the extension's own catalog can answer it, in the language now set."""
        self.assertEqual(contract.parse(_without("display_name")).display_name, "")

    def test_a_name_that_could_not_be_a_url_segment_is_refused(self) -> None:
        for bad in ("Sample", "two words", "9lives", "", "a/b", "a-b"):
            with self.subTest(name=bad), \
                    self.assertRaises(contract.ManifestError) as caught:
                contract.parse(_without("name", name=bad))

            self.assertEqual(caught.exception.key, "extension.reason.manifest_bad_name")

    def test_an_abi_this_build_does_not_offer_is_refused(self) -> None:
        with self.assertRaises(contract.ManifestError) as caught:
            contract.parse(_without("requires_platform", requires_platform=99))

        self.assertEqual(_said(caught.exception),
                         t("extension.reason.manifest_platform_not_offered", abi="99",
                           offered=str(contract.PLATFORM_ABI)))

    def test_a_capability_nobody_has_heard_of_is_refused(self) -> None:
        """The list is the consent surface, so an unknown entry is not a thing a user
        could have agreed to."""
        with self.assertRaises(contract.ManifestError) as caught:
            contract.parse(_without("capabilities", capabilities=["hardware:laser"]))

        self.assertEqual(_said(caught.exception),
                         t("extension.reason.manifest_unknown_capabilities",
                           capabilities="hardware:laser"))

    def test_each_refusal_fills_every_slot_of_its_line(self) -> None:
        for bad in (["not", "an", "object"], _without("name"),
                    _without("requires_platform", requires_platform="one"),
                    _without("requires_platform", requires_platform=99),
                    _without("provides", provides="read"),
                    _without("provides", provides=["read:everything"]),
                    _without("capabilities", capabilities=["hardware:laser"]),
                    _without("platforms", platforms=["amiga"]),
                    _without("requires_features", requires_features=["catalog"])):
            with self.subTest(manifest=bad), \
                    self.assertRaises(contract.ManifestError) as caught:
                contract.parse(bad)

            self.assertNotIn("{", _said(caught.exception))
            self.assertNotEqual(_said(caught.exception), caught.exception.key)

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

        self.assertEqual(_said(caught.exception),
                         t("extension.reason.manifest_missing", file=contract.MANIFEST_NAME))

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
