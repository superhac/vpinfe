"""The catalog and the code agree, and the registries hold no words of their own.

Each of these is a way the catalog silently rots: a key nothing serves renders as the
key, a registry that kept its literal is a string no translator is ever offered, and a
recorded hash that has drifted means `--stale` stops reporting.
"""

import ast
import json
import re
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
# The Console's own components. Every one of these puts its argument in front of a
# person, and each was found by reading `console/panel.py` rather than by the check
# noticing: a helper the list does not name is a hole the check cannot see.
DISPLAY_ARG = {"column": 1, "two_line": 0, "intro": 0, "note": 0, "state": 0,
               "header": 0, "fact": 0, "action": 0, "trouble_mark": 0}
# `search` only as `panel.search`: `re.search` is the same attribute name and its first
# argument is a pattern, not a placeholder.
QUALIFIED = {("panel", "search"): 0}
DISPLAY_KWARGS = {"label", "text", "title", "placeholder", "tooltip", "help", "message",
                  "description", "caption", "hint", "said", "header", "headerName",
                  # A column group is a header over other headers. `summary` and `reason`
                  # are deliberately absent: they name OpenAPI metadata and a WebSocket
                  # close reason far more often than they name anything on a screen.
                  "group"}
# Constructors whose `description` and `title` are the API's own documentation - the
# OpenAPI page and the capability list an integrator reads, not anything on a screen.
# Same line §9 draws for logs and docs/: it says the same thing on every install.
API_DOCUMENTATION = {"Query", "Header", "Path", "Body", "Form", "File", "Depends",
                     "FastAPI", "APIRouter", "Capability", "Field"}


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


def _literals_in(node) -> list[str]:
    """Every string literal a value is built from, through conditionals and joins."""
    if isinstance(node, ast.Constant):
        return [node.value] if isinstance(node.value, str) else []
    if isinstance(node, ast.IfExp):
        return _literals_in(node.body) + _literals_in(node.orelse)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        return _literals_in(node.left) + _literals_in(node.right)
    if isinstance(node, ast.JoinedStr):
        return ["".join(v.value for v in node.values
                        if isinstance(v, ast.Constant) and isinstance(v.value, str))]
    return []


def _fault(path, call, kwarg, node) -> list[str]:
    """Whether this argument hands a person English the catalog never saw.

    An f-string counts. It was the whole of the miss: 174 of these sat in plain sight
    while a check that only looked at `ast.Constant` reported the Console clean - and a
    sentence assembled from pieces is the one a translator most needs to own, because
    the order of the pieces is different in most languages.
    """
    where = f"{path.relative_to(ROOT)}:{node.lineno}"
    shown = f"{call}({kwarg}=" if kwarg else f"{call}("
    # A conditional picks between two sentences and a + joins one to another, and both
    # are still words typed where they are shown. Four of these sat behind a check that
    # only knew Constant and JoinedStr.
    if isinstance(node, ast.IfExp):
        return _fault(path, call, kwarg, node.body) + _fault(path, call, kwarg, node.orelse)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        return _fault(path, call, kwarg, node.left) + _fault(path, call, kwarg, node.right)
    if isinstance(node, ast.Constant) and _is_text(node.value):
        return [f"{where} {shown}{node.value!r})"]
    if isinstance(node, ast.JoinedStr):
        words = "".join(v.value for v in node.values
                        if isinstance(v, ast.Constant) and isinstance(v.value, str))
        if any(c.isalpha() for c in words) and len(words.strip()) > 2:
            return [f"{where} {shown}f{words.strip()[:46]!r}...)"]
    return []


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
                if at is None:
                    at = QUALIFIED.get((getattr(func.value, "id", None), name)) \
                        if isinstance(func, ast.Attribute) else None
                if at is not None and len(node.args) > at:
                    offenders += _fault(path, name, "", node.args[at])
                if name in API_DOCUMENTATION:
                    continue
                for kw in node.keywords:
                    if kw.arg in DISPLAY_KWARGS:
                        offenders += _fault(path, name, kw.arg, kw.value)
        self.assertEqual(offenders, [], "call t() and put the words in the catalog")

    def test_a_constant_is_not_a_hiding_place(self) -> None:
        """`INTRO = "Each one is a way of..."` then `ui.label(INTRO)` reads as clean.

        Seven of these survived two passes: the check looks at the call site and the
        words were one line away. A constant may hold a *key* - `UNREACHABLE_NOTE` does,
        because `door_reason` returns it and a test names it - but not a sentence.
        """
        offenders = []
        for path in sorted((ROOT / "console").rglob("*.py")):
            if "__pycache__" in path.parts:
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"))
            held = {node.targets[0].id: node.value.value for node in tree.body
                    if isinstance(node, ast.Assign) and len(node.targets) == 1
                    and isinstance(node.targets[0], ast.Name)
                    and isinstance(node.value, ast.Constant)
                    and isinstance(node.value.value, str)}
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                func = node.func
                name = func.attr if isinstance(func, ast.Attribute) \
                    else getattr(func, "id", None)
                if name in API_DOCUMENTATION:
                    continue
                at = 0 if name in DISPLAY_CALLS else DISPLAY_ARG.get(name)
                if at is None:
                    at = QUALIFIED.get((getattr(func.value, "id", None), name)) \
                        if isinstance(func, ast.Attribute) else None
                spots = []
                if at is not None and len(node.args) > at:
                    spots.append(node.args[at])
                spots += [kw.value for kw in node.keywords if kw.arg in DISPLAY_KWARGS]
                for spot in spots:
                    if isinstance(spot, ast.Name) and spot.id in held \
                       and _is_text(held[spot.id]):
                        offenders.append(f"{path.relative_to(ROOT)}:{spot.lineno} "
                                         f"{name}({spot.id}) where {spot.id} = "
                                         f"{held[spot.id][:40]!r}")
        self.assertEqual(offenders, [], "the constant should hold a key, not a sentence")

    def test_a_function_does_not_return_a_sentence(self) -> None:
        """`return "Only this table uses it"` and a caller shows it.

        Nineteen of these. The call site looks clean because the words are in the
        function it calls, which is the same way a constant hid seven more.
        """
        offenders = []
        for path in sorted((ROOT / "console").rglob("*.py")):
            if "__pycache__" in path.parts:
                continue
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                if not isinstance(node, ast.Return) or node.value is None:
                    continue
                for said in _literals_in(node.value):
                    # Three words and a capital: a sentence, not a key or a CSS class
                    if len(said.split()) >= 3 and said[:1].isupper() \
                       and not said.startswith(("console.", "frontend.", "error.")):
                        offenders.append(f"{path.relative_to(ROOT)}:{node.lineno} "
                                         f"return {said[:44]!r}")
        self.assertEqual(offenders, [], "return a key and let the caller resolve it")

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
                for key, value in zip(node.keys, node.values, strict=True):
                    if isinstance(key, ast.Constant) and key.value in DISPLAY_KWARGS \
                       and isinstance(value, ast.Constant) and _is_text(value.value):
                        offenders.append(f"{path.relative_to(ROOT)}:{value.lineno} "
                                         f'{{"{key.value}": {value.value!r}}}')
        self.assertEqual(offenders, [], "call t() and put the words in the catalog")


# Markup the frontend serves itself. A text node here is a cabinet's words, and nothing
# checked them until this existed - the Console could not drift back to English and these
# five pages could.
STATIC = ROOT / "frontend" / "static"
ELEMENT = re.compile(r"<([a-zA-Z][\w-]*)\b([^<>]*?)>([^<>]*[A-Za-z][^<>]*?)</\1>")
SCRIPT_OR_STYLE = re.compile(r"<(script|style)\b.*?</\1>", re.S | re.I)
WRITES_TEXT = re.compile(r"""(textContent|innerHTML|innerText)\s*=\s*(['"])(.*?)\2""")
# `title` never shows under kiosk, `option` carries values a script rewrites, and both
# would be noise rather than findings.
UNCHECKED_TAGS = {"title", "script", "style", "option"}


def _reads_as_prose(text: str) -> bool:
    said = text.strip()
    if len(said) < 2 or not any(c.isalpha() for c in said):
        return False
    if said.startswith(("http", "/", "#", "{")):
        return False
    return not re.fullmatch(r"[a-z][a-z0-9_-]*", said)


# Constructors whose message the Console shows to the user verbatim: console/api.py
# raises ApiError carrying the server's `error.message`, and a page notifies it.
API_ERRORS = {"NotFoundError", "InvalidRequestError", "ConflictError",
              "FeatureUnavailableError", "ApiError"}


class TestApiErrorMessages(unittest.TestCase):
    """The wire's `code` is the contract; its `message` is a sentence somebody reads.

    `httpapi/errors.py` says clients branch on the code, and they should - but nothing
    does, so the message is what reaches the screen. That makes it UI, and it belongs in
    the catalog like the rest of the UI.
    """

    def test_no_error_is_raised_with_a_literal_message(self) -> None:
        offenders = []
        for path in sorted((ROOT / "httpapi").rglob("*.py")):
            if "__pycache__" in path.parts:
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                if getattr(node.func, "id", None) not in API_ERRORS:
                    continue
                spots = [kw.value for kw in node.keywords if kw.arg == "message"]
                name = getattr(node.func, "id", "")
                if name == "ApiError" and len(node.args) > 1:
                    spots.append(node.args[1])
                elif name != "ApiError" and node.args:
                    spots.append(node.args[0])
                for spot in spots:
                    offenders += _fault(path, name, "", spot)
        self.assertEqual(offenders, [], "call t() and put the words in the catalog")


class TestFrontendChrome(unittest.TestCase):
    """The frontend serves its own markup, so the Python check cannot see any of it."""

    def test_every_text_node_carries_a_key(self) -> None:
        offenders = []
        for path in sorted(STATIC.rglob("*.html")):
            body = SCRIPT_OR_STYLE.sub("", path.read_text(encoding="utf-8"))
            for tag, attrs, text in ELEMENT.findall(body):
                if tag.lower() in UNCHECKED_TAGS or "data-i18n" in attrs:
                    continue
                if _reads_as_prose(text):
                    offenders.append(f"{path.relative_to(ROOT)}: <{tag}>{text.strip()[:40]}")
        self.assertEqual(offenders, [], 'add data-i18n="<key>" and put the words in the catalog')

    def test_nothing_writes_a_literal_into_the_page(self) -> None:
        """A runtime string needs t(key, english), not a quoted sentence."""
        offenders = []
        for path in sorted(STATIC.rglob("*")):
            if path.suffix not in (".html", ".js") or not path.is_file():
                continue
            for prop, _quote, said in WRITES_TEXT.findall(path.read_text(encoding="utf-8")):
                if _reads_as_prose(said):
                    offenders.append(f"{path.relative_to(ROOT)}: {prop} = {said[:40]!r}")
        self.assertEqual(offenders, [], "call t(key, english) instead")

    def test_every_key_the_markup_names_is_served(self) -> None:
        """A key with no entry renders as whatever English is between the tags, which
        looks right until the day somebody translates the catalog and that one does not
        move."""
        served = {f"frontend.{k}" for k in SOURCE if k.startswith("frontend.")} | \
                 {k for k in SOURCE if k.startswith("frontend.")}
        missing = []
        for path in sorted(STATIC.rglob("*.html")):
            for key in re.findall(r'data-i18n="([^"]+)"', path.read_text(encoding="utf-8")):
                if key not in served:
                    missing.append(f"{path.relative_to(ROOT)}: {key}")
        self.assertEqual(missing, [], "the markup names a key the catalog does not hold")


class TestCatalogs(unittest.TestCase):
    def test_the_recorded_hashes_match_the_source(self) -> None:
        """Out of step and `--stale` stops reporting. `scripts/i18n.py --record` fixes it."""
        import hashlib
        recorded = json.loads((CATALOGS / "en.hashes.json").read_text(encoding="utf-8"))
        current = {k: hashlib.sha256(
            json.dumps(v, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:12]
            for k, v in SOURCE.items()}
        self.assertEqual(recorded, current, "run scripts/i18n.py --record")

    def test_the_pseudo_locale_is_in_step_with_english(self) -> None:
        """A stale `qps` makes the render check pass on words it can no longer see."""
        pseudo = CATALOGS / "qps.json"
        if not pseudo.is_file():
            self.skipTest("no pseudo-locale generated")
        held = json.loads(pseudo.read_text(encoding="utf-8"))
        self.assertEqual(sorted(held), sorted(SOURCE),
                         "run scripts/i18n.py --pseudo")

    def test_no_translation_holds_a_key_english_does_not(self) -> None:
        for path in sorted(CATALOGS.glob("*.json")):
            if path.stem in ("en", "en.hashes", "qps"):
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
