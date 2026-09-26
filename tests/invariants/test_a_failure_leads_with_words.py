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
MESSAGES = {"notify", "notification", "label", "intro", "note", "lede", "tooltip",
            "markdown"}
# What an exception holds as its own text, rather than as data it carries.
TEXT = {"args", "msg", "message", "strerror", "reason"}

SLOT = re.compile(r"\{exc(?:[.!:\[][^}]*)?\}")

NOT_YET: frozenset[str] = frozenset({
    "common/games/media_ops.py",
    "console/about.py",
    "console/app_settings.py",
    "console/art_fill.py",
    "console/collection_adds.py",
    "console/collections.py",
    "console/community.py",
    "console/devices.py",
    "console/ext_action.py",
    "console/ext_page.py",
    "console/games.py",
    "console/import_dialog.py",
    "console/launchers.py",
    "console/locations.py",
    "console/mediasource.py",
    "console/page.py",
    "console/remote.py",
    "console/sections.py",
    "console/send_to_device.py",
    "console/settings.py",
    "console/stars.py",
    "console/tageditor.py",
    "console/themes.py",
    "console/undo.py",
    "console/uploads.py",
    "console/vps_match.py",
    "console/workbench.py",
    "extensions/library_importer/adopt.py",
    "extensions/library_importer/emulationstation.py",
    "extensions/library_importer/gamestats.py",
    "extensions/library_importer/pinballx.py",
    "extensions/library_importer/popper.py",
    "extensions/library_importer/registry.py",
    "extensions/vpinplay/community.py",
})


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
            for value in _given(call):
                for one in _as_text(value, node.name):
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
                 if path.relative_to(ROOT).as_posix() not in NOT_YET
                 for line, said in offenders(path.read_text(encoding="utf-8"))]
        self.assertEqual(found, [], "the lead-in is the message; why() goes in the caption")

    def test_no_entry_has_a_slot_for_one(self) -> None:
        sweeping = [(ROOT / name).read_text(encoding="utf-8") for name in NOT_YET]

        def named(key: str) -> bool:
            own = key.split(".", 2)[-1] if key.startswith(("app.", "ext.")) else key
            return any(f'"{own}"' in text for text in sweeping)

        self.assertEqual(sorted(key for key, value in served().items()
                                if _slots(value) and not named(key)), [])

    def test_the_paths_still_to_sweep_are_not_already_clean(self) -> None:
        clean = sorted(name for name in NOT_YET
                       if not offenders((ROOT / name).read_text(encoding="utf-8")))
        self.assertEqual(clean, [])

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
                  "    except Exception as error:\n"
                  "        row['error'] = ctx.t('x.game_file', error=f'{error}')\n"
                  "    return lambda exc: t('x.could_not', exc=exc)\n")

        said = [f"{line} {text}" for line, text in offenders(source)]

        self.assertEqual(said, ["5 exc=exc", "7 str(exc)", "9 exc.msg",
                                "11 _why(exc)", "15 f'{error}'", "16 exc=exc"])

    def test_a_slot_is_found_however_it_is_written(self) -> None:
        self.assertEqual([_slots(one) for one in
                          ("Could not: {exc}", "{exc!r}", {"one": "{exc.args}"},
                           "{excuse}", "{count}")],
                         [True, True, True, False, False])


if __name__ == "__main__":
    unittest.main()
