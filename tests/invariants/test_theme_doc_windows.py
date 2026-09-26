"""docs/theme.md names the windows a theme opens as the frontend reads them."""

from __future__ import annotations

import json
import re
import tempfile
import unittest
from pathlib import Path

from frontend import theme_contract, theme_windows

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
THEME_DOC = REPO_ROOT / "docs" / "theme.md"

JSON_BLOCK = re.compile(r"```json\n(.*?)```", re.DOTALL)
NAMES_AT_CONTRACT = re.compile(r"((?:`\w+`(?:, | and )?)+) at contract (\d+)")
FILES_ROW = re.compile(r"^\| (\d+) \| (.+) \|$", re.MULTILINE)
PAGE = re.compile(r"index_(\w+)\.html")


def _doc() -> str:
    return THEME_DOC.read_text(encoding="utf-8")


def _section(heading: str) -> str:
    """From `heading` to the next heading of any level."""
    body = _doc().split(f"\n{heading}\n", 1)[1]
    return re.split(r"\n#{2,4} ", body, maxsplit=1)[0]


def _manifests() -> list[dict]:
    """Every JSON example that declares windows, a bare `"windows": [...]` line included."""
    found = []
    for text in JSON_BLOCK.findall(_doc()):
        for candidate in (text, "{" + text + "}"):
            try:
                parsed = json.loads(candidate)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict) and theme_windows.MANIFEST_KEY in parsed:
                found.append(parsed)
            break
    return found


def _theme(folder: Path, manifest: dict | None, pages: tuple[str, ...] = ()) -> Path:
    folder.mkdir(parents=True)
    if manifest is not None:
        (folder / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    for name in pages:
        (folder / f"index_{name}.html").write_text("<html></html>", encoding="utf-8")
    return folder


class ManifestExamplesTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory()))

    def test_every_example_opens_the_windows_it_lists_without_a_warning(self) -> None:
        manifests = _manifests()
        self.assertGreaterEqual(len(manifests), 2)
        for at, manifest in enumerate(manifests):
            with self.subTest(windows=manifest[theme_windows.MANIFEST_KEY]):
                self.assertIn(theme_contract.MIN_VERSION_KEY, manifest)
                theme_dir = _theme(self.root / str(at), manifest)
                contract = theme_contract.declared_contract(theme_dir)
                with self.assertNoLogs(theme_windows.logger, level="WARNING"):
                    opened = theme_windows.declared_windows(theme_dir, contract)
                self.assertEqual(opened, tuple(manifest[theme_windows.MANIFEST_KEY]))


class DefaultsTests(unittest.TestCase):
    def test_the_defaults_sentence_names_what_each_contract_opens(self) -> None:
        paragraph = " ".join(_section("### Declaring windows").split())
        said = {int(contract): tuple(re.findall(r"`(\w+)`", names))
                for names, contract in NAMES_AT_CONTRACT.findall(paragraph)}

        self.assertEqual(said, theme_windows.DEFAULT_WINDOWS)

    def test_the_files_table_names_the_pages_each_contract_opens(self) -> None:
        rows = {int(contract): tuple(PAGE.findall(files))
                for contract, files in FILES_ROW.findall(_section("## HTML Files"))}
        self.assertEqual(rows, theme_windows.DEFAULT_WINDOWS)

        root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        for contract, pages in rows.items():
            with self.subTest(contract=contract):
                theme_dir = _theme(root / str(contract), None, pages)
                self.assertEqual(theme_windows.declared_windows(theme_dir, contract),
                                 theme_windows.DEFAULT_WINDOWS[contract])

    def test_the_doc_s_own_windows_and_tree_are_the_current_contract_s(self) -> None:
        current = theme_windows.DEFAULT_WINDOWS[theme_contract.CURRENT_CONTRACT]
        listed = tuple(re.findall(r"^- `(\w+)`", _section("### Windows"), re.MULTILINE))
        tree = _section("## Theme Structure").split("```", 2)[1]

        self.assertEqual(listed, current)
        self.assertEqual(tuple(PAGE.findall(tree)), current)


if __name__ == "__main__":
    unittest.main()
