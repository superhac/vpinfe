"""Finding and importing a module that ships outside the package."""

from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from common.third_party import find_named_path, import_module_from_path


class ThirdPartyLoaderTests(unittest.TestCase):
    def test_third_party_helpers_find_and_import_module(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            nested = root / "nested"
            nested.mkdir()
            module_path = nested / "service_wrapper.py"
            module_path.write_text(
                "class DemoController:\n"
                "    value = 42\n",
                encoding="utf-8",
            )

            self.assertEqual(find_named_path(root, ("service_wrapper.py",)), module_path)
            module = import_module_from_path(module_path, module_prefix="_test")

            self.assertEqual(module.DemoController.value, 42)


if __name__ == "__main__":
    unittest.main()
