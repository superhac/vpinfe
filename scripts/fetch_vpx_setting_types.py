#!/usr/bin/env python3
"""Regenerate `apps/vpx/setting_types.py` from Visual Pinball's own declarations.

Visual Pinball writes a comment above every setting in its ini giving the label, the
description, the default and any enumerated answers - so all of that is read from the
user's own file at runtime and nothing needs to be kept here. What the comment cannot
say is the *type*: `Enable Log` and `ImageMngPosX` both default to a bare 0 or 1, and
only the source separates them. Without it every switch renders as a number field.

So this takes what the ini cannot give and nothing else: a map of `Section.Key` to a
type name, and what each plugin registers its settings with. A plugin's settings are
written without the comment, so the ini has no label, default, range or answers for them
either - and none of them at all until VPX has run that plugin once.

    ./scripts/fetch_vpx_setting_types.py [--from PATH [--from PATH]...]

Run it when Visual Pinball ships settings we do not know the type of. A key the map does
not carry falls back to what the ini implies, so a stale map degrades rather than breaks.
"""

from __future__ import annotations

import argparse
import pathlib
import re
import sys
import urllib.request
from collections.abc import Iterable

SOURCE = ("https://raw.githubusercontent.com/vpinball/vpinball/master/"
          "src/core/Settings_properties.inl")
OUT = pathlib.Path(__file__).resolve().parent.parent / "apps" / "vpx" / "setting_types.py"

# The macro's name says the type.
KINDS = {
    "Bool": "bool", "BoolDyn": "bool", "BoolBase": "bool",
    "Int": "int", "IntUnbounded": "int", "IntDyn": "int", "IntBase": "int",
    "Float": "number", "FloatUnbounded": "number", "FloatDyn": "number",
    "FloatStepped": "number", "FloatSteppedDyn": "number", "FloatBase": "number",
    "String": "string", "StringDyn": "string", "StringBase": "string",
    "Enum": "choice", "EnumDyn": "choice", "EnumWithMin": "choice", "Enum1": "choice",
    "EnumBase": "choice",
}
# It gathers other properties under one name.
NOT_A_SETTING = frozenset({"Array"})

DECL = re.compile(r"Prop(\w+)\(\s*(\w+)\s*,\s*(\w+)\s*,")
# Past the key of a `...Base` form: the label and the comment, each one or more string
# literals, then whether it is contextual.
_LITERALS = r'(?:"(?:[^"\\]|\\.)*"s?\s*)+'
BASE_CONTEXTUAL = re.compile(rf"\s*{_LITERALS},\s*{_LITERALS},\s*(true|false)\b")

# A plugin declares its own, and they are never in the core file: it registers them with
# the host when it loads. `MSGPI_INT_VAL_SETTING(var, "BackglassDMDX", "Backglass DMD X
# position", "DMD overlay X position", true, 0, 0xFFFF, 0)`: the variable, the key, its
# label, its description and whether it is editable, then what its type takes. A label
# that is not a literal still leaves the rest.
PLUGIN_CALL = re.compile(r"\bMSGPI_([A-Z]+)_(?:VAL_)?SETTING\s*\(")
PLUGIN_KINDS = {"BOOL": "bool", "INT": "int", "FLOAT": "number",
                "STRING": "string", "ENUM": "choice"}
# Past those five, by macro. `MSGPI_ENUM_...` numbers its answers from `minimum`.
PLUGIN_ARGS = {"FLOAT": ("minimum", "maximum", "step", "default"),
               "INT": ("minimum", "maximum", "default"),
               "ENUM": ("minimum", "count", "values", "default"),
               "BOOL": ("default",),
               "STRING": ("default", "size")}
_STRING = re.compile(r'"((?:[^"\\]|\\.)*)"s?')
_CHAR = re.compile(r"'(?:[^'\\]|\\.)'")
_NUMBER = re.compile(r"[-+]?(?:0[xX][0-9A-Fa-f]+|(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?[fF]?)")
_SIZE = re.compile(r"std::size\(\s*(\w+)\s*\)")
_DEFINE = re.compile(r"^[ \t]*#[ \t]*define[ \t]+(\w+)[ \t]+([^\n]+?)[ \t]*$", re.M)
_ENUM = re.compile(r"\benum\b[^{;]*\{")
_ARRAY = re.compile(r"\b(\w+)\s*\[\s*\w*\s*\]\s*=\s*\{")
_ESCAPES = {"n": "\n", "t": "\t", '"': '"', "\\": "\\", "'": "'"}
# `id = "B2SLegacy"` in the manifest is the section suffix: `[Plugin.B2SLegacy]`.
PLUGIN_ID = re.compile(r'^\s*id\s*=\s*"([^"]+)"', re.M)

# The source names a section with a C++ identifier; the file it writes uses a separator.
# `PluginPinMAME` is `[Plugin.PinMAME]` on disk and `DefaultPropsBall` is
# `[DefaultProps\Ball]`. Two rules rather than a list of forty, so a plugin added later
# lands without this script changing.
SEPARATORS = (("DefaultProps", "\\"), ("Plugin", "."))


def section_on_disk(declared: str) -> str:
    for prefix, joiner in SEPARATORS:
        if declared.startswith(prefix) and len(declared) > len(prefix):
            return f"{prefix}{joiner}{declared[len(prefix):]}"
    return declared


def parsed(text: str) -> tuple[dict[str, str], set[str]]:
    """Every setting's type, and which of them are contextual.

    Contextual is the `...Dyn` half of each macro pair, or a `...Base` form that says so,
    and it decides whether a table override survives being saved:
    `LayeredINIPropertyStore::Save` drops a table value that equals the application's
    *unless* the property is contextual, in which case it is kept. Without this, a
    setting that can be held at the inherited value and one that cannot are
    indistinguishable here.

    Raises ValueError on a macro `KINDS` does not name.
    """
    flat = re.sub(r"\s+", " ", text)
    found: dict[str, str] = {}
    contextual: set[str] = set()
    unknown: set[str] = set()
    for declared in DECL.finditer(flat):
        macro, section, key = declared.groups()
        if macro in NOT_A_SETTING:
            continue
        kind = KINDS.get(macro)
        if kind is None:
            unknown.add(f"Prop{macro}")
            continue
        qualified = f"{section_on_disk(section)}.{key}"
        found[qualified] = kind
        if _contextual(macro, qualified, flat, declared.end()):
            contextual.add(qualified)
    if unknown:
        raise ValueError(f"No type for {', '.join(sorted(unknown))}; add it to KINDS.")
    return found, contextual


def _contextual(macro: str, qualified: str, text: str, after_key: int) -> bool:
    if not macro.endswith("Base"):
        return macro.endswith("Dyn")
    said = BASE_CONTEXTUAL.match(text, after_key)
    if said is None:
        raise ValueError(f"Cannot read whether {qualified} is contextual.")
    return said.group(1) == "true"


# By key, what a plugin registers a setting with: `default` as the file would store it,
# and `minimum`, `maximum` and `choices` where it has them.
Registered = dict[str, dict[str, object]]
Build = tuple[dict[str, str], set[str], dict[str, str], Registered]


def combined(builds: Iterable[Build]) -> Build:
    """Several builds as one map, oldest first. A setting more than one declares takes
    the last one's type, whether it is contextual, its label and what it registers."""
    types: dict[str, str] = {}
    contextual: set[str] = set()
    labels: dict[str, str] = {}
    registered: Registered = {}
    for found, held, said, given in builds:
        types.update(found)
        contextual = (contextual - found.keys()) | held
        labels = {key: label for key, label in labels.items() if key not in found} | said
        registered = {key: one for key, one in registered.items() if key not in found} | given
    return types, contextual, labels, registered


def _registered_row(key: str, one: dict[str, object]) -> str:
    named = [repr(one["default"])]
    named += [f"{name}={one[name]!r}" for name in ("minimum", "maximum")
              if one.get(name) is not None]
    answers = one.get("choices") or ()
    if not isinstance(answers, tuple) or not answers:
        return f"    {key!r}: Registered({', '.join(named)}),\n"
    listed = "".join(f"        {answer!r},\n" for answer in answers)
    return f"    {key!r}: Registered({', '.join(named)}, choices=(\n{listed}    )),\n"


def rendered(types: dict[str, str], contextual: set[str] | None = None,
             labels: dict[str, str] | None = None,
             registered: Registered | None = None) -> str:
    # Escaped: a `DefaultProps\\Ball` section carries a backslash, and written raw it
    # is an invalid escape in the file this generates.
    rows = "".join(f'    {key!r}: "{kind}",\n' for key, kind in sorted(types.items()))
    marks = "".join(f"    {key!r},\n" for key in sorted(contextual or ()))
    names = "".join(f"    {key!r}: {label!r},\n"
                    for key, label in sorted((labels or {}).items()))
    given = "".join(_registered_row(key, one)
                    for key, one in sorted((registered or {}).items()))
    return (
        '"""What type each Visual Pinball setting is, and what a plugin registers its own\n'
        "with.\n"
        "\n"
        "Generated by `scripts/fetch_vpx_setting_types.py` from Visual Pinball's own\n"
        "property declarations. The label, the description, the default and any\n"
        "enumerated answers of the rest are written into the ini by Visual Pinball\n"
        "itself and are read from the user's own file at runtime.\n"
        "\n"
        "It is here because the ini cannot say what a type is. `Enable Log` and\n"
        "`ImageMngPosX` both default to a bare 0 or 1, and without this every switch in\n"
        "the program renders as a number field.\n"
        "\n"
        "A key this does not carry falls back to what the ini implies, so a version of\n"
        "Visual Pinball newer than this file degrades rather than breaks.\n"
        '"""\n'
        "\n"
        "from __future__ import annotations\n"
        "\n"
        "from typing import NamedTuple\n"
        "\n"
        "\n"
        "class Registered(NamedTuple):\n"
        '    """What a plugin registers one of its settings with. `default` is as the file\n'
        '    stores it: a switch is 1 or 0, and an enumerated setting is its number."""\n'
        "\n"
        "    default: str\n"
        "    minimum: float | None = None\n"
        "    maximum: float | None = None\n"
        "    choices: tuple[tuple[str, str], ...] = ()\n"
        "\n"
        "\n"
        f"# {len(types)} declarations.\n"
        "TYPES: dict[str, str] = {\n"
        f"{rows}"
        "}\n"
        "\n"
        "# The ones a table can hold at the application's own value.\n"
        "#\n"
        "# Saving a table's settings drops any value equal to the application's, so a\n"
        "# table cannot be pinned to what it already inherits - except for these, which\n"
        "# are kept. Declared by the `...Dyn` half of each macro pair.\n"
        f"# {len(contextual or ())} of them.\n"
        "CONTEXTUAL: frozenset[str] = frozenset({\n"
        f"{marks}"
        "})\n"
        "\n"
        "# A plugin setting's label, where it is not the key. The ini writes every plugin\n"
        "# setting but `Enable` bare, so it has none to give.\n"
        f"# {len(labels or {})} of them.\n"
        "LABELS: dict[str, str] = {\n"
        f"{names}"
        "}\n"
        "\n"
        "# What each plugin setting is registered with. The ini has none of it: VPX writes\n"
        "# a plugin's settings bare, and only once it has run that plugin.\n"
        f"# {len(registered or {})} of them.\n"
        "REGISTERED: dict[str, Registered] = {\n"
        f"{given}"
        "}\n"
    )


def from_plugins(root: pathlib.Path) -> tuple[dict[str, str], dict[str, str], Registered]:
    """Every setting the shipped plugins register, by the section they land in; the
    label of each one whose label is not its key; and what each is registered with.

    A plugin names itself in its manifest and its settings in its sources, so the two
    are read together. Without this the switches somebody actually reaches for - turn
    the backglass DMD overlay off, turn a plugin on - are typeless and draw as text.

    Raises ValueError on a declaration whose default or answers it cannot work out.
    """
    found: dict[str, str] = {}
    labels: dict[str, str] = {}
    registered: Registered = {}
    for manifest in sorted(root.rglob("plugin.cfg")):
        named = PLUGIN_ID.search(manifest.read_text(encoding="utf-8", errors="replace"))
        if named is None:
            continue
        section = f"Plugin.{named.group(1)}"
        # Every plugin has one and no plugin declares it: the host creates it so that a
        # plugin can be switched off, and it is the switch somebody actually reaches for.
        found[f"{section}.Enable"] = "bool"
        sources = [source.read_text(encoding="utf-8", errors="replace")
                   for source in sorted(manifest.parent.rglob("*"))
                   if source.suffix in (".cpp", ".h")]
        names = _Names(sources)
        for text in sources:
            for macro, args in _declarations(text):
                kind = PLUGIN_KINDS.get(macro)
                key = _literal(args[1]) if len(args) > 1 else None
                if kind is None or key is None:
                    continue
                qualified = f"{section}.{key}"
                found[qualified] = kind
                label = _literal(args[2])
                if label and label != key:
                    labels[qualified] = label
                registered[qualified] = names.registered(qualified, macro, args[5:])
    return found, labels, registered


def _declarations(text: str) -> Iterable[tuple[str, list[str]]]:
    """Each plugin setting declared in a source, as its macro and its arguments. The
    macros' own definitions are not declarations."""
    for call in PLUGIN_CALL.finditer(text):
        line = text[text.rfind("\n", 0, call.start()) + 1:call.start()]
        if "#" not in line:
            yield call.group(1), _items(text, call.end())


def _items(text: str, start: int) -> list[str]:
    """The comma-separated items from `start` to the bracket that closes the one before
    it, each stripped, with the commas inside strings, brackets and comments left alone.
    """
    found: list[str] = []
    depth, begin, at = 0, start, start
    while at < len(text):
        two = text[at:at + 2]
        if two == "//":
            at = text.find("\n", at)
            at = len(text) if at < 0 else at
            continue
        if two == "/*":
            at = text.find("*/", at)
            at = len(text) if at < 0 else at + 2
            continue
        char = text[at]
        if char in "\"'":
            quoted = (_STRING if char == '"' else _CHAR).match(text, at)
            at = quoted.end() if quoted else at + 1
            continue
        if char in "([{":
            depth += 1
        elif char in ")]}":
            if depth == 0:
                found.append(_uncommented(text[begin:at]))
                return [one for one in found if one]
            depth -= 1
        elif char == "," and depth == 0:
            found.append(_uncommented(text[begin:at]))
            begin = at + 1
        at += 1
    raise ValueError(f"Unclosed bracket from: {text[start:start + 60]!r}")


def _items_or_none(text: str, start: int) -> list[str] | None:
    try:
        return _items(text, start)
    except ValueError:
        return None


def _uncommented(item: str) -> str:
    return re.sub(r"//[^\n]*|/\*.*?\*/", "", item, flags=re.S).strip()


def _literal(item: str) -> str | None:
    """The text of one string literal, or of several written side by side; None where
    the item is not one."""
    parts = list(_STRING.finditer(item))
    if not parts or _STRING.sub("", item).strip():
        return None
    return "".join(re.sub(r"\\(.)", lambda m: _ESCAPES.get(m.group(1), m.group(1)),
                          part.group(1)) for part in parts)


class _Names:
    """What a plugin's sources name: its `#define`s, its enum members and its arrays,
    for reading a declaration that uses them."""

    def __init__(self, sources: Iterable[str]) -> None:
        self.values: dict[str, str] = {}
        self.arrays: dict[str, list[str]] = {}
        texts = list(sources)
        for text in texts:
            self.values.update(_DEFINE.findall(text))
        # Read after every `#define`, which an enum's members may be set from. What
        # cannot be read is left out rather than stopping the run: only a declaration
        # that uses it needs it, and that one stops the run itself.
        for text in texts:
            for body in _ENUM.finditer(text):
                following: int | None = 0
                for member in _items_or_none(text, body.end()) or ():
                    name, _, said = member.partition("=")
                    if said.strip():
                        following = self._number_or_none(said)
                    if following is not None:
                        self.values[name.strip()] = str(following)
                        following += 1
            for array in _ARRAY.finditer(text):
                if (items := _items_or_none(text, array.end())) is not None:
                    self.arrays[array.group(1)] = items

    def value(self, item: str, seen: frozenset[str] = frozenset()) -> str | float | bool:
        item = item.strip()
        while item.startswith("(") and item.endswith(")"):
            item = item[1:-1].strip()
        said = _literal(item)
        if said is not None:
            return said
        if item in ("true", "false"):
            return item == "true"
        if _NUMBER.fullmatch(item):
            if re.fullmatch(r"[-+]?0[xX][0-9A-Fa-f]+", item):
                return float(int(item, 16))
            return float(item.rstrip("fF"))
        sized = _SIZE.fullmatch(item)
        if sized and sized.group(1) in self.arrays:
            return float(len(self.arrays[sized.group(1)]))
        if item in self.values and item not in seen:
            return self.value(self.values[item], seen | {item})
        raise ValueError(f"Cannot read {item!r}")

    def number(self, item: str) -> int:
        said = self.value(item)
        if isinstance(said, str):
            raise ValueError(f"{item!r} is not a number")
        return int(said)

    def _number_or_none(self, item: str) -> int | None:
        try:
            return self.number(item)
        except ValueError:
            return None

    def registered(self, qualified: str, macro: str,
                   args: list[str]) -> dict[str, object]:
        wanted = PLUGIN_ARGS[macro]
        if len(args) < len(wanted):
            raise ValueError(f"{qualified} declares too little to read.")
        said = dict(zip(wanted, args, strict=False))
        try:
            return self._given(macro, said)
        except ValueError as exc:
            raise ValueError(f"{qualified}: {exc}") from exc

    def _given(self, macro: str, said: dict[str, str]) -> dict[str, object]:
        if macro == "BOOL":
            return {"default": "1" if self.value(said["default"]) else "0"}
        if macro == "STRING":
            return {"default": str(self.value(said["default"]))}
        if macro == "FLOAT":
            return {"default": repr(float(self.value(said["default"]))),
                    "minimum": float(self.value(said["minimum"])),
                    "maximum": float(self.value(said["maximum"]))}
        low = self.number(said["minimum"])
        if macro == "INT":
            return {"default": str(self.number(said["default"])), "minimum": low,
                    "maximum": self.number(said["maximum"])}
        answers = self.arrays.get(said["values"].strip())
        if answers is None:
            raise ValueError(f"no array {said['values']!r}")
        count = self.number(said["count"])
        return {"default": str(self.number(said["default"])),
                "choices": tuple((str(low + n), str(self.value(answer)))
                                 for n, answer in enumerate(answers[:count]))}


def from_checkout(root: pathlib.Path) -> Build:
    types, contextual = parsed((root / "src" / "core" / "Settings_properties.inl")
                               .read_text(encoding="utf-8"))
    # The plugins come second, so a plugin that redeclares a core setting is the one
    # that answers for its own section.
    plugin_types, labels, registered = from_plugins(root / "plugins")
    # The host registers the switch of a plugin the core does not declare when the
    # player starts, off.
    registered.update({key: {"default": "0"} for key in plugin_types
                       if key.endswith(".Enable") and key not in types})
    types.update(plugin_types)
    return types, contextual, labels, registered


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--from", dest="sources", action="append", default=[],
                    metavar="PATH",
                    help="a checkout of vpinball, instead of fetching the sources; once "
                         "per build, oldest first")
    args = ap.parse_args()

    try:
        labels: dict[str, str] = {}
        registered: Registered = {}
        if args.sources:
            types, contextual, labels, registered = combined(
                from_checkout(pathlib.Path(source)) for source in args.sources)
        else:
            with urllib.request.urlopen(SOURCE, timeout=30) as answer:
                types, contextual = parsed(answer.read().decode("utf-8"))
            print("Only the core settings were read. Point --from at a checkout to "
                  "take the plugins' as well.", file=sys.stderr)
    except ValueError as exc:
        print(exc, file=sys.stderr)
        return 1
    if not types:
        print("No declarations found; the source's shape has changed.", file=sys.stderr)
        return 1
    OUT.write_text(rendered(types, contextual, labels, registered), encoding="utf-8")
    counts: dict[str, int] = {}
    for kind in types.values():
        counts[kind] = counts.get(kind, 0) + 1
    print(f"wrote {OUT.relative_to(OUT.parent.parent.parent)}: {len(types)} settings")
    for kind, n in sorted(counts.items()):
        print(f"    {kind:8} {n}")
    print(f"    {'contextual':8} {len(contextual)}")
    print(f"    {'labels':8} {len(labels)}")
    print(f"    {'registered':8} {len(registered)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
