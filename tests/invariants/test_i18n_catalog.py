"""The catalog and the code agree, and the registries hold no words of their own.

Each of these is a way the catalog silently rots: a key nothing serves renders as the
key, a registry that kept its literal is a string no translator is ever offered, and a
recorded hash that has drifted means `--stale` stops reporting.
"""

import ast
import dataclasses
import importlib.util
import json
import re
import string
import unittest
from pathlib import Path

from common import apps, i18n, tokens
from common.apps.contract import Availability, ConfigGroup, Field
from common.config_schema import ConfigOption
from common.games.asset_registry import ASSET_SPECS, AssetSpec
from common.games.collection_filters import AXES, FilterAxis
from common.games.launchers import OWN_FIELDS
from common.input_registry import InputAction, actions
from common.media_specs import MEDIA_SPECS, MediaSpec
from common.tokens import Token
from tests.support.catalogs import served

ROOT = Path(__file__).resolve().parents[2]
CATALOGS = ROOT / "common" / "i18n" / "catalogs"
SOURCE = json.loads((CATALOGS / "en.json").read_text(encoding="utf-8"))

# The registries whose words now live in the catalog. A declaration here holding a
# string literal is one the translator never sees.
CONVERTED = {
    ConfigOption: {"label", "description", "group"},
    MediaSpec: {"label"},
    AssetSpec: {"label"},
    InputAction: {"label", "group"},
    FilterAxis: {"label", "summary"},
    Field: {"label", "description"},
    ConfigGroup: {"label"},
    Token: {"says"},
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

    def test_setting_groups(self) -> None:
        from common import config_schema
        self._check(sorted({(f"config.group.{o.group}", o.group_label)
                            for o in config_schema.options() if o.group}))

    def test_settings_that_are_shown(self) -> None:
        from common import config_schema
        shown = [o for o in config_schema.options() if not o.internal]
        missing = [f"{o.section}.{o.key}" for o in shown if not o.label]
        self.assertEqual(missing, [], "a setting with no name of its own")

    def test_launcher_fields(self) -> None:
        described = [(f"{app.id}.{f.key}", apps.field_words(app.id, f))
                     for app in apps.all_apps() for f in (*app.fields, *OWN_FIELDS)]
        self.assertEqual([name for name, said in described
                          if not said["label_key"] or not said["description"]], [],
                         "a launcher field with no words of its own")

    def test_tokens(self) -> None:
        self._check([(one.name, tokens.stands_for(one)) for one in tokens.TOKENS])

    def test_app_names(self) -> None:
        self.assertEqual([app.id for app in apps.all_apps()
                          if apps.app_name(app.id) == app.id], [])

    def test_app_setting_groups(self) -> None:
        from apps.vpx import areas
        keys = [*areas.AREAS, areas.POINT_OF_VIEW, areas.REST]
        self.assertEqual([key for key in keys
                          if not apps.group_words("vpx", ConfigGroup(key))["label_key"]],
                         [])


def _literal_words(tree: ast.AST) -> list[tuple[int, str]]:
    """Each converted declaration given a word in place, by name or by position."""
    held = {cls.__name__: (names, [f.name for f in dataclasses.fields(cls)])
            for cls, names in CONVERTED.items()}
    found = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
        if name not in held:
            continue
        names, order = held[name]
        given = [*zip(order, node.args, strict=False),
                 *((kw.arg, kw.value) for kw in node.keywords)]
        found += [(value.lineno, f"{name}({arg}={value.value!r})")
                  for arg, value in given
                  if arg in names and isinstance(value, ast.Constant) and value.value]
    return found


class TestRegistriesHoldNoWords(unittest.TestCase):
    def test_no_converted_declaration_carries_a_literal(self) -> None:
        offenders = [f"{path.relative_to(ROOT)}:{line} {said}"
                     for root in ("common", "apps")
                     for path in sorted((ROOT / root).rglob("*.py"))
                     if "__pycache__" not in path.parts
                     for line, said in _literal_words(
                         ast.parse(path.read_text(encoding="utf-8")))]
        self.assertEqual(offenders, [], "the catalog owns these words now")

    def test_a_word_is_found_however_it_is_given(self) -> None:
        source = ('Field("bin_path", "Program")\n'
                  'apps.Field("args", description="Arguments")\n'
                  'ConfigGroup("rom", "ROM")\n'
                  'Field("bin_path", path="exe")\n')
        self.assertEqual([said for _, said in _literal_words(ast.parse(source))],
                         ["Field(label='Program')", "Field(description='Arguments')",
                          "ConfigGroup(label='ROM')"])


# Modules whose words a surface shows, and which ways out each is read for.
EVERY_WAY = frozenset({"return", "reason", "raise"})
SPEAKS_TO_A_SURFACE = {
    "common/path_checks.py": EVERY_WAY,
    "common/feature_checks.py": EVERY_WAY,
    "common/host/metrics.py": EVERY_WAY,
    "common/host/pinmame_catalog.py": EVERY_WAY,
    "common/host/action_ops.py": EVERY_WAY,
    "common/extensions/games.py": EVERY_WAY,
    "common/uploads/upload_ops.py": EVERY_WAY,
    "httpapi/capabilities.py": EVERY_WAY,
    "httpapi/core_capabilities.py": EVERY_WAY,
    "common/device_client.py": frozenset({"reason", "raise"}),
    "common/uploads/asset_import_service.py": frozenset({"reason", "raise", "refusal"}),
    "common/uploads/upload_session_service.py": frozenset({"raise", "refusal"}),
    "common/games/locations.py": frozenset({"reason"}),
    "console/metrics.py": frozenset({"reason"}),
    "common/games/config_backups.py": frozenset({"raise", "refusal"}),
    "common/games/asset_resolver.py": frozenset({"reason"}),
    "common/games/table_lens.py": frozenset({"reason"}),
}

# Said to whoever wrote the calling code, which has a bug to fix rather than a person
# something to do.
SAID_TO_A_DEVELOPER = {"AttributeError", "ContractError", "NotThisDeviceError",
                       "NotVPinFEError", "RuntimeError", "TypeError"}
# A value refused, which a module's caller may show as it was said. One that does lists
# `refusal`.
REFUSED = "ValueError"


def _pieces(node: ast.expr, held: dict[str, ast.expr]) -> list[ast.expr]:
    """A value split through tuples, conditionals and joins, and a module constant read
    through its name where it holds words rather than a code."""
    if isinstance(node, ast.Tuple):
        return [piece for one in node.elts for piece in _pieces(one, held)]
    if isinstance(node, ast.IfExp):
        return _pieces(node.body, held) + _pieces(node.orelse, held)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        return _pieces(node.left, held) + _pieces(node.right, held)
    constant = held.get(node.id) if isinstance(node, ast.Name) else None
    if isinstance(constant, ast.Constant) and _words(constant.value):
        return [ast.copy_location(ast.Constant(constant.value), node)]
    return [node]


def _names_reason(target: ast.expr) -> bool:
    if isinstance(target, ast.Subscript):
        return isinstance(target.slice, ast.Constant) and target.slice.value == "reason"
    return getattr(target, "id", None) == "reason"


def _reason_at(tree: ast.Module) -> dict[str, int]:
    """Where a module's own dataclasses take `reason` when it is given by position."""
    at = {}
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and any(
                _named(one.func if isinstance(one, ast.Call) else one) == "dataclass"
                for one in node.decorator_list):
            fields = [one.target.id for one in node.body
                      if isinstance(one, ast.AnnAssign) and isinstance(one.target, ast.Name)]
            if "reason" in fields:
                at[node.name] = fields.index("reason")
    return at


def _handed_back(source: str) -> list[tuple[str, ast.expr]]:
    """Each value a module returns, gives as a `reason` or raises with, and which."""
    tree = ast.parse(source)
    held = _constants(tree)
    reason_at = _reason_at(tree)
    found: list[tuple[str, ast.expr]] = []

    def add(kind: str, value: ast.expr) -> None:
        found.extend((kind, one) for one in _pieces(value, held))

    for node in ast.walk(tree):
        if isinstance(node, ast.Return) and node.value is not None:
            add("return", node.value)
        elif isinstance(node, ast.keyword) and node.arg == "reason":
            add("reason", node.value)
        elif isinstance(node, ast.Call) and _named(node.func) in reason_at:
            spot = reason_at[str(_named(node.func))]
            if len(node.args) > spot:
                add("reason", node.args[spot])
        elif isinstance(node, ast.Dict):
            for key, value in zip(node.keys, node.values, strict=True):
                if isinstance(key, ast.Constant) and key.value == "reason":
                    add("reason", value)
        elif isinstance(node, ast.Raise) and isinstance(node.exc, ast.Call) \
                and node.exc.args and _named(node.exc.func) not in SAID_TO_A_DEVELOPER:
            add("refusal" if _named(node.exc.func) == REFUSED else "raise",
                node.exc.args[0])
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                pairs = (list(zip(target.elts, node.value.elts, strict=True))
                         if isinstance(target, ast.Tuple)
                         and isinstance(node.value, ast.Tuple)
                         else [(target, node.value)])
                for at, value in pairs:
                    if _names_reason(at):
                        add("reason", value)
    return found


def _not_looked_up(kind: str, one: ast.expr) -> bool:
    if isinstance(one, ast.JoinedStr):
        return True
    if isinstance(one, ast.Constant) and isinstance(one.value, str):
        said = one.value.strip()
        return bool(said) and said not in SOURCE
    return kind == "reason" and isinstance(one, ast.Call) and _named(one.func) == "str"


def _source_of(name: str) -> str:
    return (ROOT / name).read_text(encoding="utf-8")


class TestWhatAModuleHandsBackIsLookedUp(unittest.TestCase):

    def test_no_word_handed_back_is_written_in_place(self) -> None:
        offenders = [f"{name}:{one.lineno} {kind} {ast.unparse(one)[:60]}"
                     for name, ways in SPEAKS_TO_A_SURFACE.items()
                     for kind, one in _handed_back(_source_of(name))
                     if kind in ways and _not_looked_up(kind, one)]
        self.assertEqual(offenders, [], "the catalog owns these words now")

    def test_it_found_each_way_out(self) -> None:
        """An empty sweep passes and measures nothing, which reads the same as clean."""
        kinds = [kind for name, ways in SPEAKS_TO_A_SURFACE.items()
                 for kind, _ in _handed_back(_source_of(name)) if kind in ways]
        self.assertGreater(kinds.count("return"), 5)
        self.assertGreater(kinds.count("reason"), 5)
        self.assertGreater(kinds.count("raise"), 5)
        self.assertGreater(kinds.count("refusal"), 0)

    def test_each_road_is_read(self) -> None:
        source = ('NOT_WIRED = "Nothing performs that."\n'
                  'KEY = "error.actions.nothing_performs_that"\n'
                  "def listing():\n"
                  '    return {"reason": NOT_WIRED, "reason_key": KEY, "what": "VPinFE"}\n'
                  "def probe(exc):\n"
                  '    return {"state": "unreachable", "reason": str(exc)}\n'
                  "def game(game_id):\n"
                  '    raise LookupError(f"No game with id {game_id}")\n'
                  "def check():\n"
                  "    raise UnavailableError(NOT_WIRED)\n"
                  "def contract():\n"
                  '    raise ContractError("not inside a folder it declared")\n'
                  "def folder(name):\n"
                  '    raise ValueError(f"Table folder already exists: {name}")\n'
                  "def row(found):\n"
                  '    found["reason"] = "Copied"\n'
                  "    return t(KEY)\n"
                  "@dataclass(frozen=True)\n"
                  "class Blocked:\n"
                  "    asset: str\n"
                  "    reason: str\n"
                  "def blocked(asset):\n"
                  '    return Blocked(asset, "Drop it on a game")\n')

        said = sorted(f"{kind} {ast.unparse(one)}" for kind, one in _handed_back(source)
                      if _not_looked_up(kind, one))

        self.assertEqual(said, ["raise 'Nothing performs that.'",
                                "raise f'No game with id {game_id}'",
                                "reason 'Copied'",
                                "reason 'Drop it on a game'",
                                "reason 'Nothing performs that.'",
                                "reason str(exc)",
                                "refusal f'Table folder already exists: {name}'"])


# Pages where a caught exception reaches the screen only through the function named,
# which is what turns another machine's connection error into a reason a person can use.
SAYS_WHAT_WENT_WRONG = {"console/devices.py": "_why"}


def _exception_made_text(source: str) -> list[ast.expr]:
    """Each caught exception handed to `str()`, to `t()` or into an f-string."""
    found: list[ast.expr] = []
    for handler in ast.walk(ast.parse(source)):
        if not isinstance(handler, ast.ExceptHandler) or not handler.name:
            continue
        for node in (one for line in handler.body for one in ast.walk(line)):
            if isinstance(node, ast.Call) and _named(node.func) in ("str", "t"):
                given = [*node.args, *(kw.value for kw in node.keywords)]
            elif isinstance(node, ast.FormattedValue):
                given = [node.value]
            else:
                continue
            found += [one for one in given
                      if isinstance(one, ast.Name) and one.id == handler.name]
    return found


class TestAnExceptionIsSaidInWords(unittest.TestCase):

    def test_no_exception_reaches_the_screen_as_itself(self) -> None:
        offenders = [f"{name}:{one.lineno} {ast.unparse(one)}"
                     for name in SAYS_WHAT_WENT_WRONG
                     for one in _exception_made_text(_source_of(name))]
        self.assertEqual(offenders, [], "say it through the function that words it")

    def test_the_function_that_words_it_is_there(self) -> None:
        for name, through in SAYS_WHAT_WENT_WRONG.items():
            with self.subTest(name):
                self.assertIn(f"def {through}(", _source_of(name))

    def test_each_way_is_read(self) -> None:
        source = ("def ask(client):\n"
                  "    try:\n"
                  "        client.ask()\n"
                  "    except TooOldError as exc:\n"
                  "        return str(exc)\n"
                  "    except Exception as exc:\n"
                  "        logger.info('Could not ask %s', exc)\n"
                  "        ui.notify(t('said.could_not_do_that', exc=(exc)))\n"
                  "        ui.notify(f'Could not: {exc}')\n"
                  "        return t('said.could_not_do_that', exc=_why(exc))\n")

        said = [f"{one.lineno} {ast.unparse(one)}" for one in _exception_made_text(source)]

        self.assertEqual(said, ["5 exc", "8 exc", "9 exc"])


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
QUALIFIED = {("panel", "search"): 0, ("confirm", "ask"): 0}
DISPLAY_KWARGS = {"label", "text", "title", "placeholder", "tooltip", "help", "message",
                  "description", "caption", "hint", "said", "header", "headerName",
                  # A column group is a header over other headers. `detail` and
                  # `confirm` are the confirm dialog's own - its question is a positional
                  # argument, so QUALIFIED carries that half. `summary` and `reason` are
                  # deliberately absent: they name OpenAPI metadata and a WebSocket close
                  # reason far more often than anything on a screen.
                  "group", "detail", "confirm"}
# Constructors whose `description` and `title` are the API's own documentation - the
# OpenAPI page and the capability list an integrator reads, not anything on a screen.
# Same line drawn for logs and docs/: it says the same thing on every install.
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
        slots = sum(isinstance(v, ast.FormattedValue) for v in node.values)
        if slots > 1 and words.strip():
            return [f"{where} {shown}f{words!r})"]
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


# Quasar props drawn as text.
TEXT_PROPS =("error-message", "hint", "label", "placeholder", "prefix", "suffix",
              "no-option-label", "no-data-label", "no-results-label", "loading-label",
              "title", "aria-label")
_TEXT_PROP = re.compile(r"(?<![\w-])(" + "|".join(TEXT_PROPS) + r")=([\"'])(.*?)\2")
OPTION_CALLS =frozenset({"select", "toggle", "radio"})
_CATALOG_KEY = re.compile(r"[a-z][a-z0-9_]*(?:\.[a-z0-9_]+)+")


def _words(value: object) -> bool:
    return _is_text(value) and not _CATALOG_KEY.fullmatch(str(value).strip())


def _constants(tree: ast.Module) -> dict[str, ast.expr]:
    held: dict[str, ast.expr] = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 \
           and isinstance(node.targets[0], ast.Name):
            held[node.targets[0].id] = node.value
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) \
                and node.value is not None:
            held[node.target.id] = node.value
    return held


def _reachable_constants(tree: ast.Module) -> dict[str, ast.expr]:
    """This module's constants, and the ones it imports by name from the tree."""
    held = _constants(tree)
    for node in tree.body:
        if not (isinstance(node, ast.ImportFrom) and node.module and not node.level):
            continue
        source = ROOT / (node.module.replace(".", "/") + ".py")
        if source.is_file():
            theirs = _constants(ast.parse(source.read_text(encoding="utf-8")))
            for alias in node.names:
                if alias.name in theirs:
                    held.setdefault(alias.asname or alias.name, theirs[alias.name])
    return held


def _prop_words(tree: ast.AST) -> list[str]:
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and getattr(node.func, "attr", None) == "props":
            for arg in node.args:
                typed = arg.value if isinstance(arg, ast.Constant) \
                    else _glued_words(arg) if isinstance(arg, ast.JoinedStr) else None
                if isinstance(typed, str):
                    found += [f"{node.lineno} {prop}={said!r}"
                              for prop, _quote, said in _TEXT_PROP.findall(typed)
                              if _words(said)]
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Subscript) \
                   and getattr(target.value, "attr", None) == "props" \
                   and isinstance(target.slice, ast.Constant) \
                   and target.slice.value in TEXT_PROPS \
                   and isinstance(node.value, ast.Constant) and _words(node.value.value):
                    found.append(f"{node.lineno} props[{target.slice.value!r}]"
                                 f" = {node.value.value!r}")
    return found


class _Options(ast.NodeVisitor):
    def __init__(self, held: dict[str, ast.expr]) -> None:
        self.held = held
        self.scopes: list[dict[str, list[ast.expr]]] = [{}]
        self.found: list[str] = []

    def visit_FunctionDef(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        assigned: dict[str, list[ast.expr]] = {}
        for inner in ast.walk(node):
            if isinstance(inner, ast.Assign):
                for target in inner.targets:
                    if isinstance(target, ast.Name):
                        assigned.setdefault(target.id, []).append(inner.value)
        self.scopes.append(assigned)
        self.generic_visit(node)
        self.scopes.pop()

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self.visit_FunctionDef(node)

    def visit_Call(self, node: ast.Call) -> None:
        func = node.func
        name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", None)
        if name in OPTION_CALLS:
            for arg in [*node.args[:1], *(kw.value for kw in node.keywords
                                          if kw.arg == "options")]:
                said = self._words_in(arg, ())
                if said:
                    self.found.append(f"{node.lineno} {name}({said[:3]})")
        self.generic_visit(node)

    def _words_in(self, node: ast.expr, seen: tuple[str, ...]) -> list[str]:
        if isinstance(node, ast.Constant):
            return [node.value] if _words(node.value) else []
        if isinstance(node, ast.Dict):
            return [said for key, value in zip(node.keys, node.values, strict=True)
                    for said in (self._words_in(value, seen) if key is None
                                 else self._element(value, seen))]
        if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
            return [said for element in node.elts for said in self._element(element, seen)]
        if isinstance(node, ast.Starred):
            return self._words_in(node.value, seen)
        if isinstance(node, ast.IfExp):
            return self._words_in(node.body, seen) + self._words_in(node.orelse, seen)
        if isinstance(node, ast.BinOp):
            return self._words_in(node.left, seen) + self._words_in(node.right, seen)
        if isinstance(node, ast.Call) and getattr(node.func, "id", None) in (
                "dict", "list", "tuple") and node.args:
            return self._words_in(node.args[0], seen)
        if isinstance(node, ast.Name) and node.id not in seen:
            bound = next((scope[node.id] for scope in reversed(self.scopes)
                          if node.id in scope),
                         [self.held[node.id]] if node.id in self.held else [])
            return [said for value in bound
                    for said in self._words_in(value, (*seen, node.id))]
        return []

    def _element(self, node: ast.expr, seen: tuple[str, ...]) -> list[str]:
        """An option itself: words, or a name bound to them - never a nested collection,
        which is data a person does not read as one option."""
        if isinstance(node, (ast.Constant, ast.Name, ast.Starred)):
            return self._words_in(node, seen)
        return []


class TestWordsHandedToQuasar(unittest.TestCase):
    def test_no_prop_carries_words(self) -> None:
        offenders = []
        for path in sorted((ROOT / "console").rglob("*.py")):
            if "__pycache__" in path.parts:
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"))
            offenders += [f"{path.relative_to(ROOT)}:{said}" for said in _prop_words(tree)]
        self.assertEqual(offenders, [], "call t() and put the words in the catalog")

    def test_no_picker_is_handed_words(self) -> None:
        offenders = []
        for path in sorted((ROOT / "console").rglob("*.py")):
            if "__pycache__" in path.parts:
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"))
            seen = _Options(_reachable_constants(tree))
            seen.visit(tree)
            offenders += [f"{path.relative_to(ROOT)}:{said}" for said in seen.found]
        self.assertEqual(offenders, [], "call t() and put the words in the catalog")

    def test_each_road_is_read(self) -> None:
        tree = ast.parse(
            'name.props["error-message"] = "Give it a name"\n'
            "box.props('dense outlined error-message=\"Give it a name\"')\n"
            'ui.select({"": t("a"), "no": "No"})\n'
            'LABELS = {"asc": "Ascending", "desc": "order.direction.desc"}\n'
            "def control():\n"
            '    choices = {"m": t("b"), **LABELS} if arranged else dict(LABELS)\n'
            "    def draw():\n"
            "        ui.select(choices)\n"
            'ui.toggle(options=["Keys", "order.by.title", key])\n'
            'ui.select({"a": {"label": "Nested"}})\n')
        seen = _Options(_reachable_constants(tree))
        seen.visit(tree)

        self.assertEqual(len(_prop_words(tree)), 2)
        self.assertEqual(seen.found, ["3 select(['No'])",
                                      "8 select(['Ascending', 'Ascending'])",
                                      "9 toggle(['Keys'])"])


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


PASSED_ON_AS_A_REFUSAL = {"CommandRefusedError"}


def _named(node: ast.expr) -> str | None:
    return getattr(node, "id", None) or getattr(node, "attr", None)


def _refusal_sweep() -> tuple[set[str], list[tuple[Path, str | None, ast.expr]]]:
    """The LaunchUnavailableError family, and each call in `common/` with its first argument."""
    parents: dict[str, set[str | None]] = {}
    calls = []
    for path in sorted((ROOT / "common").rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.ClassDef):
                parents[node.name] = {_named(base) for base in node.bases}
            elif isinstance(node, ast.Call) and node.args:
                calls.append((path, _named(node.func), node.args[0]))
    family = {"LaunchUnavailableError"}
    while grown := {name for name, bases in parents.items() if bases & family} - family:
        family |= grown
    return family, calls


class TestLaunchRefusalMessages(unittest.TestCase):
    def test_no_refusal_is_raised_with_a_literal_message(self) -> None:
        family, calls = _refusal_sweep()
        offenders = [fault for path, name, message in calls
                     if name in family | PASSED_ON_AS_A_REFUSAL
                     for fault in _fault(path, name, "", message)]
        self.assertEqual(offenders, [], "call t() and put the words in the catalog")

    def test_it_found_the_refusals(self) -> None:
        """An empty sweep passes and measures nothing, which reads the same as clean."""
        family, calls = _refusal_sweep()
        self.assertGreater(len(family), 3)
        self.assertGreater(sum(1 for _, name, _ in calls if name in family), 5)
        self.assertTrue(any(name in PASSED_ON_AS_A_REFUSAL for _, name, _ in calls))


class TestTheCatalogHoldsWords(unittest.TestCase):
    def test_no_entry_is_a_class_list(self) -> None:
        """A translation of one restyles the page instead of rewording it."""
        found = [key for key, value in SOURCE.items()
                 for said in (value.values() if isinstance(value, dict) else [value])
                 if re.search(r"\bconsole-[a-z]", str(said))]
        self.assertEqual([], found)

    def test_no_entry_is_a_fragment_glued_onto_another(self) -> None:
        """A space at either end is the seam of a sentence built from pieces."""
        joiners = {"console.collection_rules.list_join"}
        found = [key for key, value in served().items() if key not in joiners
                 for said in (value.values() if isinstance(value, dict) else [value])
                 if str(said) != str(said).strip()]
        self.assertEqual([], found, "take the other string as a slot")


# An f-string reaching one of these is not a word anybody reads.
NOT_ON_SCREEN = {
    "run_javascript", "add_body_html", "add_head_html", "html", "classes", "props",
    "style", "dumps", "loads", "getLogger", "debug", "info", "warning", "error",
    "exception", "critical",
    # The ones the Console does show are the API's own errors, read by
    # TestApiErrorMessages.
    "ValueError", "TypeError", "RuntimeError", "CancelledError", "KeyError", "OSError",
    "FileNotFoundError", "NotImplementedError",
}
# A literal carrying one of these is markup, a URL or a selector rather than prose.
NOT_PROSE = re.compile(r"[<>?&/=;{}#]")
BYTE_UNITS = {"B", "KB", "MB", "GB", "TB"}


def _is_identifier(said: str) -> bool:
    """`asset_`, `.tables`, `builtin:`: a name being built, not words being joined.

    Whitespace tells them apart, and it is read unstripped: `builtin:` is one token and
    `"Set: "` is a word with a value after it. Prose this short - `by`, `of`, `No` -
    never carries a dot, an underscore or a colon.
    """
    body = said.strip()
    if not body or any(c.isspace() for c in body):
        return False
    if re.search(r"[_.\-]", body):
        return True
    # `builtin:`, `location:` - an id namespace. Prose puts a space after its colon,
    # which is the whole of the difference between that and `"Set: "`.
    return body.endswith(":") and not any(c.isspace() for c in said)


def _glued_words(node: ast.JoinedStr) -> str:
    """The typed half of an f-string: everything outside its slots."""
    return "".join(v.value for v in node.values
                   if isinstance(v, ast.Constant) and isinstance(v.value, str))


class _Fstrings(ast.NodeVisitor):
    """Every f-string, with the calls it sits inside, so context can excuse it."""

    def __init__(self) -> None:
        self.found: list[tuple[int, str]] = []
        self.calls: list[str] = []

    def visit_Call(self, node: ast.Call) -> None:
        name = getattr(node.func, "attr", None) or getattr(node.func, "id", None) or ""
        self.visit(node.func)
        self.calls.append(name)
        for argument in (*node.args, *node.keywords):
            self.visit(argument)
        self.calls.pop()

    def visit_JoinedStr(self, node: ast.JoinedStr) -> None:
        said = _glued_words(node)
        if not set(self.calls) & NOT_ON_SCREEN and not NOT_PROSE.search(said) \
           and not _is_identifier(said) and said.strip() not in BYTE_UNITS \
           and re.search(r"[A-Za-z]{2,}", said):
            self.found.append((node.lineno, said))
        self.generic_visit(node)


class TestNoWordGluedToAValue(unittest.TestCase):
    """An f-string whose typed half is a word rather than a token or a class."""

    def test_a_label_styled_in_the_same_line_is_still_read(self) -> None:
        seen = _Fstrings()
        seen.visit(ast.parse('ui.label(f"{a} of {b}").classes("console-help")'))
        self.assertEqual([" of "], [said for _, said in seen.found])

    def test_no_fstring_in_the_console_carries_a_word(self) -> None:
        offenders = []
        for path in sorted((ROOT / "console").rglob("*.py")):
            if "__pycache__" in path.parts:
                continue
            seen = _Fstrings()
            seen.visit(ast.parse(path.read_text(encoding="utf-8")))
            offenders += [f"{path.relative_to(ROOT)}:{line} f{said.strip()[:38]!r}"
                          for line, said in seen.found]
        self.assertEqual(offenders, [], "call t() with a named slot instead")


class _PluralSuffixes(ast.NodeVisitor):
    """A choice between "" and "s" handed to t() or written into an f-string."""

    SUFFIXES = {"", "s", "es"}

    def __init__(self) -> None:
        self.found: list[int] = []
        self.within: list[str] = []

    def visit_Call(self, node: ast.Call) -> None:
        name = getattr(node.func, "attr", None) or getattr(node.func, "id", None) or ""
        self.visit(node.func)
        self.within.append(name)
        for argument in (*node.args, *node.keywords):
            self.visit(argument)
        self.within.pop()

    def visit_JoinedStr(self, node: ast.JoinedStr) -> None:
        self.within.append("f-string")
        self.generic_visit(node)
        self.within.pop()

    def visit_IfExp(self, node: ast.IfExp) -> None:
        said = {getattr(b, "value", None) for b in (node.body, node.orelse)}
        if len(said) == 2 and said <= self.SUFFIXES \
           and not set(self.within) & NOT_ON_SCREEN \
           and set(self.within) & {"t", "t_source", "f-string"}:
            self.found.append(node.lineno)
        self.generic_visit(node)


class TestPluralsComeFromTheCatalog(unittest.TestCase):
    """A count's word is a `one`/`other` entry, never a suffix chosen beside the call."""

    def test_a_suffix_handed_to_t_is_found(self) -> None:
        seen = _PluralSuffixes()
        seen.visit(ast.parse('ui.label(t("k", value=("" if n == 1 else "s"))).classes("x")'))
        self.assertEqual([1], seen.found)

    def test_one_written_into_an_fstring_is_found(self) -> None:
        seen = _PluralSuffixes()
        seen.visit(ast.parse('f"{n} device{\'s\' if n != 1 else \'\'}"'))
        self.assertEqual([1], seen.found)

    def test_a_log_line_may_keep_one(self) -> None:
        seen = _PluralSuffixes()
        seen.visit(ast.parse('logger.info("%s", "" if n == 1 else "s")'))
        self.assertEqual([], seen.found)

    def test_no_screen_word_is_pluralised_in_code(self) -> None:
        offenders = []
        for folder in ("console", "common", "httpapi"):
            for path in sorted((ROOT / folder).rglob("*.py")):
                if "__pycache__" in path.parts:
                    continue
                seen = _PluralSuffixes()
                seen.visit(ast.parse(path.read_text(encoding="utf-8")))
                offenders += [f"{path.relative_to(ROOT)}:{line}" for line in seen.found]
        self.assertEqual(offenders, [], "give the key one/other forms and pass count=")


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
        # What `_serve_core_words` actually sends: the frontend's own namespace and the
        # shared vocabulary. A key outside both would reach a page that was never given
        # it, however present it is in the catalog.
        served = {k for k in SOURCE if k.startswith(("frontend.", "word."))}
        missing = []
        for path in sorted(STATIC.rglob("*.html")):
            for key in re.findall(r'data-i18n="([^"]+)"', path.read_text(encoding="utf-8")):
                if key not in served:
                    missing.append(f"{path.relative_to(ROOT)}: {key}")
        self.assertEqual(missing, [], "the markup names a key the catalog does not hold")


class TestPanelFactLabels(unittest.TestCase):
    """`panel.facts` takes (label, control) pairs, so the label is never an argument.

    Sixty-six of these were English after the render check called every section clean -
    a panel only draws when something is selected, and the fixture selects nothing.
    """

    def test_no_pair_carries_a_bare_label(self) -> None:
        import re as _re
        offenders = []
        for path in sorted((ROOT / "console").rglob("*.py")):
            if "__pycache__" in path.parts:
                continue
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                if not isinstance(node, ast.Tuple) or len(node.elts) != 2:
                    continue
                label, control = node.elts
                if not (isinstance(label, ast.Constant)
                        and isinstance(label.value, str)):
                    continue
                if not isinstance(control, (ast.Call, ast.Lambda, ast.Name, ast.IfExp,
                                            ast.Attribute, ast.Subscript, ast.BoolOp)):
                    continue
                said = label.value.strip()
                if len(said) < 3 or not said[:1].isupper():
                    continue
                if _re.fullmatch(r"[A-Za-z][A-Za-z '/-]*", said):
                    offenders.append(f"{path.relative_to(ROOT)}:{label.lineno} "
                                     f"({said!r}, ...)")
        self.assertEqual(offenders, [], "a fact's label belongs in the catalog too")


class TestEveryKeyIsServed(unittest.TestCase):
    """`t("a.key.nobody.added")` renders the key. Two shipped because a script that
    rewrote the source aborted before it wrote the catalog, so the code asked for
    entries that were never created."""

    def test_no_call_asks_for_a_key_the_catalog_lacks(self) -> None:
        offenders = []
        # `tests` is in here because a re-key that rewrites the source and forgets the
        # suite leaves an assertion naming a key nothing serves.
        for root in ("console", "frontend", "httpapi", "common", "tests"):
            for path in sorted((ROOT / root).rglob("*.py")):
                if "__pycache__" in path.parts:
                    continue
                for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                    if not isinstance(node, ast.Call) \
                       or getattr(node.func, "id", None) != "t":
                        continue
                    if not node.args or not isinstance(node.args[0], ast.Constant):
                        continue
                    key = node.args[0].value
                    if isinstance(key, str) and key not in SOURCE:
                        offenders.append(f"{path.relative_to(ROOT)}:{node.lineno} {key}")
        self.assertEqual(offenders, [], "the catalog has no entry for these")


def _scan() -> tuple[set[str], set[str]]:
    """Every key the Python asks for, exact and by prefix.

    Imported from `scripts/i18n.py` rather than restated here, so the translator's
    `--unused` report and this gate cannot come to different answers.
    """
    spec = importlib.util.spec_from_file_location("i18n_script",
                                                  ROOT / "scripts" / "i18n.py")
    assert spec is not None and spec.loader is not None, "scripts/i18n.py is gone"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.referenced()


def _markup_keys() -> set[str]:
    """Keys the frontend's own pages name, which no scan of the Python sees."""
    found: set[str] = set()
    for path in sorted(STATIC.rglob("*")):
        if path.suffix not in (".html", ".js") or not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        found.update(re.findall(r'data-i18n="([^"]+)"', text))
        found.update(m[0] for m in re.findall(
            r"""["']([a-z][a-z0-9_]*(?:\.[a-z0-9_]+)+)["']""", text))
    return found


class TestTheCatalogHoldsNothingSpare(unittest.TestCase):
    """The other direction: an entry nothing asks for.

    It renders nowhere, so no screen looks wrong and nothing above this has anything to
    say about it. The translator is handed it to translate along with the rest.
    """

    def test_no_entry_is_asked_for_by_nothing(self) -> None:
        exact, derived = _scan()
        asks = exact | _markup_keys()
        # A key reaching a surface inside a block is asked for as much as one written
        # out: AG Grid takes `grid.*` as a single dictionary, so no search for one of
        # those keys finds anything. `referenced()` reports those namespaces among its
        # prefixes, which is why nothing here needs to know which they are.
        spare = [key for key in sorted(SOURCE)
                 if key not in asks and not key.startswith(tuple(derived))]
        self.assertEqual(spare, [], "nothing asks for these; drop them from every catalog")


class TestParametersMatchTheirTemplate(unittest.TestCase):
    """`t(key, exc=...)` against an entry that says `{reason}` renders the brace.

    Four of these shipped, and every check I had passed over all four: the call is a
    `t()` so nothing flags a literal, and the entry exists so nothing flags a miss. The
    two only disagree when you read them together.
    """

    def test_every_call_fills_exactly_the_slots_its_entry_has(self) -> None:
        offenders = []
        for root in ("console", "frontend", "httpapi", "common"):
            for path in sorted((ROOT / root).rglob("*.py")):
                if "__pycache__" in path.parts:
                    continue
                for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                    if not isinstance(node, ast.Call) \
                       or getattr(node.func, "id", None) != "t":
                        continue
                    if not node.args or not isinstance(node.args[0], ast.Constant):
                        continue
                    entry = SOURCE.get(node.args[0].value)
                    if not isinstance(entry, str):
                        continue
                    wants = {name for _, name, _, _
                             in string.Formatter().parse(entry) if name}
                    fills = {kw.arg for kw in node.keywords if kw.arg}
                    if wants != fills:
                        offenders.append(
                            f"{path.relative_to(ROOT)}:{node.lineno} "
                            f"{node.args[0].value} wants {sorted(wants)}, "
                            f"gets {sorted(fills)}")
        self.assertEqual(offenders, [], "a slot nobody fills renders as its own name")


APPS = ROOT / "apps"


def _file(directory: Path, name: str = "en") -> dict:
    path = directory / f"{name}.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}


def _package_strings(app_id: str) -> set[str]:
    """Every string constant in an app's code: a group's key, a reason it hands back."""
    return {node.value for path in (APPS / app_id).rglob("*.py")
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
            if isinstance(node, ast.Constant) and isinstance(node.value, str)}


_FIELD_WORD = re.compile(r"field\.(.+)\.(label|description|help|blank)")
_CHOICE_WORD = re.compile(r"field\.(.+)\.choice\.[^.]+\.help")
_GROUP_WORD = re.compile(r"group\.([^.]+)\.label")
_HEADING_WORD = re.compile(r"group\.([^.]+)\.(?:heading\.([^.]+)\.(?:label|note)"
                           r"|pair\.([^.]+)\.(?:label|note|joiner))")


def _asked_for(key: str, named: set[str]) -> bool:
    """Whether the key is one the contract's lookups can form from something the app
    names: a reason itself, a field's words or a choice's, a group's label, or a heading's
    words or a pair's."""
    if key in named:
        return True
    found = (_CHOICE_WORD.fullmatch(key) or _FIELD_WORD.fullmatch(key)
             or _GROUP_WORD.fullmatch(key))
    if found is not None:
        return found[1] in named
    under = _HEADING_WORD.fullmatch(key)
    return under is not None and under[1] in named and (under[2] or under[3]) in named


def _reasons(app_id: str) -> list[str]:
    """Every reason an app writes into an `Availability`, by position or by name."""
    found = []
    for path in (APPS / app_id).rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if not isinstance(node, ast.Call) \
               or getattr(node.func, "id", None) != Availability.__name__:
                continue
            given = [*node.args[1:2], *(kw.value for kw in node.keywords
                                        if kw.arg == "reason")]
            found += [one.value for one in given
                      if isinstance(one, ast.Constant) and one.value]
    return found


class TestEachAppKeepsItsOwnWords(unittest.TestCase):
    """An app's words are in its own `i18n/`, and served under `app.<id>.`."""

    def setUp(self) -> None:
        self.built_in = [app for app in apps.all_apps() if (APPS / app.id).is_dir()]

    def test_the_apps_were_found(self) -> None:
        self.assertEqual(sorted(app.id for app in self.built_in), ["generic", "vpx"])

    def test_core_holds_none_of_an_owners_words(self) -> None:
        self.assertEqual([k for k in SOURCE if k.startswith(i18n.OWNED)], [])

    def test_every_reason_an_app_gives_is_in_its_catalog(self) -> None:
        for app in self.built_in:
            held = _file(APPS / app.id / "i18n")
            with self.subTest(app=app.id):
                self.assertEqual([r for r in _reasons(app.id) if r not in held], [])

    def test_the_reasons_were_found(self) -> None:
        self.assertIn("no_plugins", _reasons("vpx"))

    def test_no_entry_is_one_the_app_cannot_ask_for(self) -> None:
        for app in self.built_in:
            named = {f.key for f in app.fields} | _package_strings(app.id)
            spare = [key for key in _file(APPS / app.id / "i18n")
                     if key != "name" and not _asked_for(key, named)]
            with self.subTest(app=app.id):
                self.assertEqual(spare, [], "nothing asks for these")

    def test_no_entry_has_a_slot(self) -> None:
        """Nothing fills one. A field's words are looked up with no parameters."""
        for app in self.built_in:
            slotted = [key for key, entry in _file(APPS / app.id / "i18n").items()
                       if isinstance(entry, str)
                       and any(name for _, name, _, _ in string.Formatter().parse(entry))]
            with self.subTest(app=app.id):
                self.assertEqual(slotted, [])


EXTENSIONS = ROOT / "extensions"


class TestEachOwnersFileIsInStep(unittest.TestCase):
    def setUp(self) -> None:
        self.owners = sorted([*APPS.glob("*/i18n"), *EXTENSIONS.glob("*/i18n")])

    def test_the_owners_were_found(self) -> None:
        found = [str(one.relative_to(ROOT)) for one in self.owners]
        self.assertIn("apps/vpx/i18n", found)
        self.assertIn("extensions/library_importer/i18n", found)

    def test_the_recorded_hashes_match(self) -> None:
        import hashlib
        for owner in self.owners:
            current = {k: hashlib.sha256(json.dumps(
                v, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:12]
                for k, v in _file(owner).items()}
            with self.subTest(owner=str(owner.relative_to(ROOT))):
                self.assertEqual(_file(owner, "en.hashes"), current,
                                 "run scripts/i18n.py --record")

    def test_the_pseudo_locale_is_in_step(self) -> None:
        for owner in self.owners:
            with self.subTest(owner=str(owner.relative_to(ROOT))):
                self.assertEqual(sorted(_file(owner, "qps")), sorted(_file(owner)),
                                 "run scripts/i18n.py --pseudo")

    def test_no_translation_holds_a_key_english_does_not(self) -> None:
        for owner in self.owners:
            english = set(_file(owner))
            for path in sorted(owner.glob("*.json")):
                if path.stem in ("en", "en.hashes", "qps"):
                    continue
                with self.subTest(owner=str(owner.relative_to(ROOT)), locale=path.stem):
                    extra = set(json.loads(path.read_text(encoding="utf-8"))) - english
                    self.assertEqual(sorted(extra), [], "keys nothing serves")


MATCHED_NOT_SHOWN = {"visual pinball x", "system volume information"}
# What the Console never shows, beside a log line and a query handed to SQLite.
NOT_READ_AT_A_SCREEN = NOT_ON_SCREEN | {"log", "execute"}
# The wizard's and the report's own, beside what the Console draws.
EXTENSION_DISPLAY_KEYS = DISPLAY_KWARGS | {"reason", "error", "how"}
# The first segment of a key the host looks up, rather than the extension's code.
HOST_READS = {"action", "community", "token", "app"}
HOST_SEGMENTS = {"label", "description", "title", "column", "header", "help", "view",
                 "name", "says", "field", "group"}


def _extensions() -> list[Path]:
    return sorted(path.parent for path in EXTENSIONS.glob("*/extension.json"))


def _modules(package: Path) -> list[tuple[Path, ast.Module]]:
    return [(path, ast.parse(path.read_text(encoding="utf-8")))
            for path in sorted(package.rglob("*.py")) if "__pycache__" not in path.parts]


def _a_sentence(said: str) -> bool:
    """Two words or more with a lowercase one among them: a phrase, not a name or a key."""
    return len(said.split()) >= 2 and any(
        word.islower() and len(word) > 1 for word in re.findall(r"[^\W\d_]+", said))


def _docstrings(tree: ast.AST) -> set[int]:
    return {id(node.body[0].value) for node in ast.walk(tree)
            if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef,
                                 ast.AsyncFunctionDef))
            and node.body and isinstance(node.body[0], ast.Expr)
            and isinstance(node.body[0].value, ast.Constant)
            and isinstance(node.body[0].value.value, str)}


class _Sentences(ast.NodeVisitor):
    def __init__(self, tree: ast.AST) -> None:
        self.skip = _docstrings(tree)
        self.calls: list[str] = []
        self.found: list[tuple[int, str]] = []
        self.visit(tree)

    def visit_Call(self, node: ast.Call) -> None:
        self.visit(node.func)
        self.calls.append(getattr(node.func, "attr", None)
                          or getattr(node.func, "id", None) or "")
        for argument in (*node.args, *node.keywords):
            self.visit(argument)
        self.calls.pop()

    def _read(self, line: int, said: str) -> None:
        if not set(self.calls) & NOT_READ_AT_A_SCREEN and said not in MATCHED_NOT_SHOWN \
           and _a_sentence(said):
            self.found.append((line, said))

    def visit_JoinedStr(self, node: ast.JoinedStr) -> None:
        self._read(node.lineno, _glued_words(node))
        for value in node.values:
            if isinstance(value, ast.FormattedValue):
                self.visit(value)

    def visit_Constant(self, node: ast.Constant) -> None:
        if isinstance(node.value, str) and id(node) not in self.skip:
            self._read(node.lineno, node.value)


def _written_in_place(tree: ast.AST, product: str) -> list[tuple[int, str]]:
    found = []
    for node in ast.walk(tree):
        spots: list[tuple[str, ast.expr]] = []
        if isinstance(node, ast.Call):
            name = getattr(node.func, "attr", None) or getattr(node.func, "id", None)
            if name not in API_DOCUMENTATION:
                spots = [(kw.arg, kw.value) for kw in node.keywords
                         if kw.arg in EXTENSION_DISPLAY_KEYS]
        elif isinstance(node, ast.Dict):
            spots = [(key.value, value) for key, value in zip(node.keys, node.values,
                                                               strict=True)
                     if isinstance(key, ast.Constant) and key.value in EXTENSION_DISPLAY_KEYS]
        found += [(value.lineno, f"{key}={value.value!r}") for key, value in spots
                  if isinstance(value, ast.Constant) and _is_text(value.value)
                  and value.value != product]
    return found


def _asks(tree: ast.AST) -> list[tuple[int, str | re.Pattern, set[str]]]:
    """Each key a module asks its own file for, and the slots it fills.

    `ctx.t` and a module's `t = words(name)` both. A key built in an f-string asks for
    every entry its shape matches.
    """
    found: list[tuple[int, str | re.Pattern, set[str]]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not node.args \
           or (getattr(node.func, "attr", None) or getattr(node.func, "id", None)) != "t":
            continue
        key, fills = node.args[0], {kw.arg for kw in node.keywords if kw.arg}
        if isinstance(key, ast.Constant) and isinstance(key.value, str):
            found.append((node.lineno, key.value, fills))
        elif isinstance(key, ast.JoinedStr):
            shape = "".join(re.escape(str(part.value)) if isinstance(part, ast.Constant)
                            else "[a-z0-9_]+" for part in key.values)
            found.append((node.lineno, re.compile(shape), fills))
    return found


def _slots(entry: object) -> set[str]:
    """What an entry fills in. A plural is chosen by `count`, whichever form uses it."""
    forms = list(entry.values()) if isinstance(entry, dict) else [entry]
    wants = {name for form in forms for _, name, _, _ in string.Formatter().parse(str(form))
             if name}
    return wants | {"count"} if isinstance(entry, dict) else wants


class TestEachExtensionKeepsItsOwnWords(unittest.TestCase):
    """An extension's words are in its own `i18n/`, and its code asks for them."""

    def setUp(self) -> None:
        self.extensions = _extensions()

    def test_the_extensions_were_found(self) -> None:
        self.assertEqual([one.name for one in _extensions()], ["library_importer", "vpinplay"])

    def test_no_sentence_is_written_in_its_code(self) -> None:
        offenders = [f"{path.relative_to(ROOT)}:{line} {said[:50]!r}"
                     for package in self.extensions
                     for path, tree in _modules(package)
                     for line, said in _Sentences(tree).found]
        self.assertEqual(offenders, [], "ctx.t() or words(), and the words in i18n/en.json")

    def test_nothing_it_shows_is_written_in_place(self) -> None:
        offenders = []
        for package in self.extensions:
            product = json.loads((package / "extension.json").read_text(
                encoding="utf-8")).get("display_name", "")
            offenders += [f"{path.relative_to(ROOT)}:{line} {said}"
                          for path, tree in _modules(package)
                          for line, said in _written_in_place(tree, product)]
        self.assertEqual(offenders, [], "ctx.t() or words(), and the words in i18n/en.json")

    def test_a_sentence_is_found_wherever_it_is_written(self) -> None:
        tree = ast.parse('"""Reads a library."""\n'
                         'NOTE = "Could not read it"\n'
                         'reason = f"{name} is not reachable"\n'
                         'logger.warning("Could not read %s", path)\n'
                         'db.execute("select name from games")\n'
                         'HINTS = ("vpx", "visual pinball x")\n'
                         'SOURCE = "PinballX / PinballY"\n'
                         'field = {"label": "Systems", "key": "systems"}\n'
                         'ctx.ui.settings("/s", label="VPinPlay")\n')
        self.assertEqual([said for _, said in _Sentences(tree).found],
                         ["Could not read it", " is not reachable"])
        self.assertEqual([said for _, said in _written_in_place(tree, "VPinPlay")],
                         ["label='Systems'"])

    def test_every_key_it_asks_for_is_served_with_its_slots(self) -> None:
        offenders = []
        for package in self.extensions:
            held = _file(package / "i18n")
            for path, tree in _modules(package):
                for line, asked, fills in _asks(tree):
                    where = f"{path.relative_to(ROOT)}:{line}"
                    keys = [asked] if isinstance(asked, str) \
                        else [key for key in held if asked.fullmatch(key)]
                    if not keys or any(key not in held for key in keys):
                        shown = getattr(asked, "pattern", asked)
                        offenders.append(f"{where} {shown} is not served")
                    offenders += [f"{where} {key} wants {sorted(_slots(held[key]))}, "
                                  f"gets {sorted(fills)}"
                                  for key in keys if key in held and _slots(held[key]) != fills]
        self.assertEqual(offenders, [])

    def test_the_asks_were_found(self) -> None:
        asked = [asked for _, tree in _modules(EXTENSIONS / "library_importer")
                 for _, asked, _ in _asks(tree)]
        self.assertIn("wizard.summary.confirm", asked)
        self.assertTrue(any(isinstance(one, re.Pattern) and one.fullmatch("kind.roms.label")
                            for one in asked))

    def test_no_entry_is_asked_for_by_nothing(self) -> None:
        for package in self.extensions:
            manifest = json.loads((package / "extension.json").read_text(encoding="utf-8"))
            trees = [tree for _, tree in _modules(package)]
            asked = [one for tree in trees for _, one, _ in _asks(tree)]
            said = {node.value for tree in trees for node in ast.walk(tree)
                    if isinstance(node, ast.Constant) and isinstance(node.value, str)}
            called = {node.func.attr for tree in trees for node in ast.walk(tree)
                      if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)}
            spare = []
            for key in _file(package / "i18n"):
                segments = key.split(".")
                if key in asked or any(isinstance(one, re.Pattern) and one.fullmatch(key)
                                       for one in asked):
                    continue
                if key == "name" and not manifest.get("display_name") \
                   or key == "description" and not manifest.get("description"):
                    continue
                if key in ("settings.label", "state.label") and segments[0] in called:
                    continue
                if segments[0] in HOST_READS and all(
                        one in said for one in segments[1:] if one not in HOST_SEGMENTS):
                    continue
                spare.append(key)
            with self.subTest(extension=package.name):
                self.assertEqual(spare, [], "nothing asks for these")


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
