"""The catalog and the code agree, and the registries hold no words of their own.

Each of these is a way the catalog silently rots: a key nothing serves renders as the
key, a registry that kept its literal is a string no translator is ever offered, and a
recorded hash that has drifted means `--stale` stops reporting.
"""

import ast
import json
import unittest
from pathlib import Path

from common import i18n
from common.games.asset_registry import ASSET_SPECS
from common.games.collection_filters import AXES
from common.input_registry import actions
from common.media_specs import MEDIA_SPECS

ROOT = Path(__file__).resolve().parents[2]
CATALOGS = ROOT / "common" / "i18n" / "catalogs"
SOURCE = json.loads((CATALOGS / "en.json").read_text(encoding="utf-8"))

# The registries whose words now live in the catalog. A declaration here holding a
# string literal is one the translator never sees.
CONVERTED = {
    "ConfigOption": {"label", "description"},
    "MediaSpec": {"label"},
    "AssetSpec": {"label"},
    "InputAction": {"label"},
    "FilterAxis": {"label", "summary"},
}


class TestEveryRegistryResolves(unittest.TestCase):
    """A key with no entry comes back as itself, which is visible and ugly, not fatal."""

    def _check(self, pairs) -> None:
        unresolved = [key for key, said in pairs if said == key or not said]
        self.assertEqual(unresolved, [], "no catalog entry")

    def test_filter_axes(self) -> None:
        self._check([(f"filter.{a.name}.label", a.label) for a in AXES]
                    + [(f"filter.{a.name}.summary", a.summary) for a in AXES])

    def test_media_kinds(self) -> None:
        self._check([(f"media.kind.{s.kind}.label", s.label) for s in MEDIA_SPECS])

    def test_asset_kinds(self) -> None:
        self._check([(f"asset.kind.{s.kind}.label", s.label) for s in ASSET_SPECS])

    def test_input_actions(self) -> None:
        self._check([(f"input.{a.name}.label", a.label) for a in actions()])

    def test_settings_that_are_shown(self) -> None:
        from common import config_schema
        shown = [o for o in config_schema.options() if not o.internal]
        missing = [f"{o.section}.{o.key}" for o in shown if not o.label]
        self.assertEqual(missing, [], "a setting with no name of its own")


class TestRegistriesHoldNoWords(unittest.TestCase):
    def test_no_converted_declaration_carries_a_literal(self) -> None:
        offenders = []
        for path in sorted((ROOT / "common").rglob("*.py")):
            if "__pycache__" in path.parts:
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                name = getattr(node.func, "id", None)
                for kw in node.keywords:
                    if kw.arg in CONVERTED.get(name, ()) \
                       and isinstance(kw.value, ast.Constant):
                        offenders.append(
                            f"{path.relative_to(ROOT)}:{kw.value.lineno} "
                            f"{name}({kw.arg}={kw.value.value!r})")
        self.assertEqual(offenders, [], "the catalog owns these words now")


# The display positions a string reaches a person through. Kept beside the check rather
# than imported from the Console, so a surface cannot quietly widen what counts as not
# being text.
DISPLAY_CALLS = {
    "label", "button", "markdown", "tooltip", "notify", "link", "badge", "chip", "tab",
    "expansion", "item_label", "radio", "toggle", "menu_item", "input", "select",
    "switch", "checkbox", "number", "textarea", "upload", "dialog", "tree", "step",
}
DISPLAY_ARG = {"column": 1, "two_line": 0, "intro": 0, "note": 0, "state": 0,
               "header": 0, "fact": 0}
DISPLAY_KWARGS = {"label", "text", "title", "placeholder", "tooltip", "help", "message",
                  "description", "caption", "hint", "said", "header", "headerName"}


def _is_text(value) -> bool:
    """Whether a literal is something a person reads, rather than an icon or a class."""
    import re
    if not isinstance(value, str):
        return False
    said = value.strip()
    if len(said) < 2 or not any(c.isalpha() for c in said):
        return False
    if said.startswith(("http://", "https://", "/", "./", "#")):
        return False
    if " " not in said and said.islower() and ("-" in said or "_" in said):
        return False
    return not re.fullmatch(r"[a-z][a-z0-9_]*", said)


class TestNoBareDisplayLiterals(unittest.TestCase):
    """A string written where it is shown is one no translator is ever offered.

    Scoped to the Console. `frontend/` static chrome is not here yet, and widening this
    to it is what that pass is measured against.
    """

    def test_the_console_shows_nothing_it_did_not_look_up(self) -> None:
        offenders = []
        for path in sorted((ROOT / "console").rglob("*.py")):
            if "__pycache__" in path.parts:
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                func = node.func
                name = func.attr if isinstance(func, ast.Attribute) \
                    else getattr(func, "id", None)
                at = 0 if name in DISPLAY_CALLS else DISPLAY_ARG.get(name)
                if at is not None and len(node.args) > at:
                    arg = node.args[at]
                    if isinstance(arg, ast.Constant) and _is_text(arg.value):
                        offenders.append(
                            f"{path.relative_to(ROOT)}:{arg.lineno} {name}({arg.value!r})")
                for kw in node.keywords:
                    if kw.arg in DISPLAY_KWARGS and isinstance(kw.value, ast.Constant) \
                       and _is_text(kw.value.value):
                        offenders.append(f"{path.relative_to(ROOT)}:{kw.value.lineno} "
                                         f"{name}({kw.arg}={kw.value.value!r})")
        self.assertEqual(offenders, [], "call t() and put the words in the catalog")

    def test_a_choice_written_as_a_dict_counts_too(self) -> None:
        """`{"value": True, "label": "Yes"}` is a grid filter's words, and the keyword
        check above walks straight past it - which is how thirteen of these survived the
        first pass."""
        offenders = []
        for path in sorted((ROOT / "console").rglob("*.py")):
            if "__pycache__" in path.parts:
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Dict):
                    continue
                for key, value in zip(node.keys, node.values):
                    if isinstance(key, ast.Constant) and key.value in DISPLAY_KWARGS \
                       and isinstance(value, ast.Constant) and _is_text(value.value):
                        offenders.append(f"{path.relative_to(ROOT)}:{value.lineno} "
                                         f'{{"{key.value}": {value.value!r}}}')
        self.assertEqual(offenders, [], "call t() and put the words in the catalog")


class TestCatalogs(unittest.TestCase):
    def test_the_recorded_hashes_match_the_source(self) -> None:
        """Out of step and `--stale` stops reporting. `scripts/i18n.py --record` fixes it."""
        import hashlib
        recorded = json.loads((CATALOGS / "en.hashes.json").read_text(encoding="utf-8"))
        current = {k: hashlib.sha256(
            json.dumps(v, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:12]
            for k, v in SOURCE.items()}
        self.assertEqual(recorded, current, "run scripts/i18n.py --record")

    def test_no_translation_holds_a_key_english_does_not(self) -> None:
        for path in sorted(CATALOGS.glob("*.json")):
            if path.stem in ("en", "en.hashes"):
                continue
            with self.subTest(locale=path.stem):
                extra = sorted(set(json.loads(path.read_text(encoding="utf-8"))) - set(SOURCE))
                self.assertEqual(extra, [], "keys nothing serves")

    def test_a_missing_key_is_not_fatal(self) -> None:
        self.assertEqual(i18n.t("nothing.serves.this"), "nothing.serves.this")

    def test_the_fallback_chain_ends_at_english(self) -> None:
        self.assertEqual(i18n.chain("de-AT"), ("de-AT", "de", "en"))


if __name__ == "__main__":
    unittest.main()
