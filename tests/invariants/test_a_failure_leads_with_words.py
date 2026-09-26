"""A failure's message says what could not be done; the exception goes under it."""

from __future__ import annotations

import ast
import re
import unittest
from pathlib import Path
from typing import Any

from tests.support.catalogs import served

ROOT = Path(__file__).resolve().parents[2]
CODE = ("apps", "common", "console", "extensions", "frontend", "httpapi", "cli.py", "main.py")

LOOKUPS = {"t", "t_source"}
# Calls that draw their first argument as the message itself.
MESSAGES = {"notify", "notification", "label", "intro", "note", "lede", "markdown"}
# Where the detail goes, which has to have been through why() or a device's own wording.
DETAIL = {"caption", "hint"}
# What an exception holds as its own text, rather than as data it carries.
TEXT = {"args", "msg", "message", "strerror", "reason"}

SLOT = re.compile(r"\{exc(?:[.!:\[][^}]*)?\}")


def _named(node: ast.expr) -> str:
    return getattr(node, "id", None) or getattr(node, "attr", None) or ""


def _as_text(value: ast.expr, name: str) -> list[ast.Name]:
    """Each use of `name` in `value` that hands on the exception or its words."""
    data = {id(node.value) for node in ast.walk(value)
            if isinstance(node, ast.Attribute) and node.attr not in TEXT}
    return [one for one in ast.walk(value)
            if isinstance(one, ast.Name) and one.id == name and id(one) not in data]


def _given(call: ast.Call) -> list[ast.expr]:
    kind = _named(call.func)
    if kind in LOOKUPS:
        return [*call.args[1:], *(kw.value for kw in call.keywords)]
    if kind in MESSAGES:
        return [*call.args[:1],
                *(kw.value for kw in call.keywords if kw.arg in ("message", "text"))]
    return []


def _detail(call: ast.Call) -> list[ast.expr]:
    return [*(call.args[:1] if _named(call.func) == "tooltip" else []),
            *(kw.value for kw in call.keywords if kw.arg in DETAIL)]


def _unworded(value: ast.expr, name: str) -> list[ast.Name]:
    worded = {id(one) for node in ast.walk(value)
              if isinstance(node, ast.Call) and "why" in _named(node.func)
              for one in ast.walk(node)}
    return [one for one in _as_text(value, name) if id(one) not in worded]


def offenders(source: str) -> list[tuple[int, str]]:
    """Each place an exception reaches a message: an `exc=` handed to `t()`, or a caught
    exception's words handed to a lookup or drawn as the message."""
    tree = ast.parse(source)
    found: list[tuple[int, str]] = []
    seen: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and _named(node.func) in LOOKUPS:
            for kw in (kw for kw in node.keywords if kw.arg == "exc"):
                found.append((kw.value.lineno, f"exc={ast.unparse(kw.value)}"))
                seen |= {id(one) for one in ast.walk(kw.value)}
    for node in ast.walk(tree):
        if not isinstance(node, ast.ExceptHandler) or not node.name:
            continue
        # Innermost first, so a `t()` inside `ui.notify()` is named rather than the notify.
        calls = [one for line in node.body for one in ast.walk(line)
                 if isinstance(one, ast.Call)]
        for call in reversed(calls):
            said = [(value, _as_text(value, node.name)) for value in _given(call)]
            said += [(value, _unworded(value, node.name)) for value in _detail(call)]
            for value, names in said:
                for one in names:
                    if id(one) not in seen:
                        seen.add(id(one))
                        found.append((one.lineno, ast.unparse(value)))
    return sorted(found)


def _sources() -> list[Path]:
    paths: list[Path] = []
    for name in CODE:
        path = ROOT / name
        paths += [path] if path.is_file() else sorted(path.rglob("*.py"))
    return [path for path in paths if "__pycache__" not in path.parts]


def _slots(value: Any) -> bool:
    forms = value.values() if isinstance(value, dict) else [value]
    return any(SLOT.search(str(form)) for form in forms)


class TheExceptionGoesUnderTheWords(unittest.TestCase):

    def test_no_message_carries_an_exception(self) -> None:
        found = [f"{path.relative_to(ROOT).as_posix()}:{line} {said}"
                 for path in _sources()
                 for line, said in offenders(path.read_text(encoding="utf-8"))]
        self.assertEqual(found, [], "the lead-in is the message; why() goes in the caption")

    def test_no_entry_has_a_slot_for_one(self) -> None:
        self.assertEqual(sorted(key for key, value in served().items() if _slots(value)), [])

    def test_each_way_is_read(self) -> None:
        source = ("def save(client):\n"
                  "    try:\n"
                  "        client.save()\n"
                  "    except KeyError as exc:\n"
                  "        ui.notify(t('said.could_not_save_it', exc=(exc)))\n"
                  "    except ValueError as exc:\n"
                  "        ui.notify(str(exc))\n"
                  "    except OSError as exc:\n"
                  "        ui.notify(t('x.not_json', msg=exc.msg))\n"
                  "        ui.notify(t('x.refused', keys=', '.join(exc.keys)))\n"
                  "        panel.intro(t('x.could_not', reason=_why(exc)))\n"
                  "        ui.notify(t('x.could_not'), caption=why(exc))\n"
                  "        panel.intro(t('x.could_not'), hint=why(exc))\n"
                  "        ui.label(t('x.could_not')).tooltip(_why(exc))\n"
                  "        ui.notify(t('x.could_not'), caption=str(exc))\n"
                  "        ui.label(t('x.could_not')).tooltip(exc.args[0])\n"
                  "    except Exception as error:\n"
                  "        row['error'] = ctx.t('x.game_file', error=f'{error}')\n"
                  "    return lambda exc: t('x.could_not', exc=exc)\n")

        said = [f"{line} {text}" for line, text in offenders(source)]

        self.assertEqual(said, ["5 exc=exc", "7 str(exc)", "9 exc.msg",
                                "11 _why(exc)", "15 str(exc)", "16 exc.args[0]",
                                "18 f'{error}'", "19 exc=exc"])

    def test_a_slot_is_found_however_it_is_written(self) -> None:
        self.assertEqual([_slots(one) for one in
                          ("Could not: {exc}", "{exc!r}", {"one": "{exc.args}"},
                           "{excuse}", "{count}")],
                         [True, True, True, False, False])


if __name__ == "__main__":
    unittest.main()
