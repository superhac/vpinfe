"""Render the Console in a language where every catalog entry is unreadable.

The AST checks answer "is there a literal in a display position?" - and four rounds of
this work showed that a string can reach the screen without ever being one: through a
constant, a dict value, a function's return, a component the check was never told about.
This asks the only question that catches all of those at once: **what English is still on
screen when every word the catalog owns has been mangled?**

It found the entire navigation rail, which four passes of static checking had called
clean.
"""

from __future__ import annotations

import ast
import asyncio
import json
import re
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from tests.support.browser_session import BrowserSession, chromium_path
from tests.support.library import write_game
from tests.support.live_instance import LiveInstance

ROOT = Path(__file__).resolve().parents[2]
CATALOG = json.loads((ROOT / "common/i18n/catalogs/en.json").read_text(encoding="utf-8"))
GAME = "Attack from Mars"


# Under the pseudo-locale every letter the catalog owns is replaced by one that is not
# ASCII, so anything still spelled in plain ASCII did not come through it. Matching on
# *that* rather than on the words the catalog happens to hold is what catches a string
# nobody has ever translated - the first version of this check intersected with the
# catalog's own vocabulary and let a planted "Diagnostics" straight through.
ASCII_WORD = re.compile(r"\b[A-Za-z]{4,}\b")


def _icon_names() -> set[str]:
    """Material icons render their own name as ligature text, so the name is on screen.

    Read from the tree rather than listed: a name nobody passes is not on any page, and
    a hand-kept list here would go stale into a false pass.
    """
    names: set[str] = set()
    for path in (ROOT / "console").rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if not isinstance(node, ast.Call):
                continue
            if getattr(node.func, "attr", None) == "icon" and node.args \
               and isinstance(node.args[0], ast.Constant):
                names.add(str(node.args[0].value).lower())
            for kw in node.keywords:
                if kw.arg in ("icon", "mark") and isinstance(kw.value, ast.Constant) \
                   and isinstance(kw.value.value, str):
                    names.add(kw.value.value.lower())
    # The rail's icons sit at index 2 of a nav tuple, which no keyword scan reaches.
    from console import page
    for parent, items in page.NAV_GROUPS:
        if parent is not None:
            names.add(str(parent[2]).lower())
        names.update(str(item[2]).lower() for item in items)
    out = set(names)
    for name in names:
        out.update(name.split("_"))
    return out


class PseudoLocaleTests(unittest.TestCase):
    """Slow: boots a real instance and a real browser. Worth it - see the docstring."""

    def test_the_console_says_nothing_in_english(self) -> None:
        if not chromium_path():
            self.skipTest("no Chromium on this machine")
        if not (ROOT / "common/i18n/catalogs/qps.json").is_file():
            self.skipTest("no pseudo-locale; run scripts/i18n.py --pseudo")

        # The library's own words are content and are never translated, so they are not
        # a leak when they show up unchanged.
        content = {w.lower() for w in re.findall(r"[A-Za-z]{4,}", GAME)} | {"local", "dev"}
        allowed = _icon_names() | content

        async def look(instance) -> list[str]:
            async with BrowserSession(chromium_path()) as browser:
                await browser.navigate(instance.console_url("/console"))
                await browser.wait_for(
                    "document.querySelectorAll('.q-page, .nicegui-content').length > 0",
                    timeout=90.0)
                await asyncio.sleep(4)
                text = await browser.evaluate("document.body.innerText") or ""
            seen = {w.lower() for w in ASCII_WORD.findall(text)}
            return sorted(seen - allowed)

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_game(root, GAME)
            with LiveInstance(root,
                              extra_settings={("general", "language"): "qps"}) as instance:
                leaked = asyncio.run(look(instance))

        self.assertEqual(leaked, [], "these reached the screen without the catalog")


if __name__ == "__main__":
    unittest.main()
