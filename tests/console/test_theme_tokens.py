"""The token layer, checked. It had no test and it decayed.

In a few weeks the stylesheet grew four tokens nothing referenced and one that was
referenced and never defined - `var(--warn)`, which resolves to nothing, so a menu item
meant to read as destructive drew in the inherited color instead. Nothing failed,
because nothing was looking.

Three rules, and they are the seam the tokenizing pass needs under it: every `var()`
resolves, every token has a user, and a color is named rather than typed.
"""

from __future__ import annotations

import re
import unittest

from console import theme

# Every block that ships, in one string - a token may be defined in one and used in
# another, and checking them apart would report both halves as broken.
STYLESHEET = theme._TOKENS + theme._FLAIR + theme._COMPONENTS

DEFINED = re.compile(r"^\s*(--[a-z0-9-]+)\s*:", re.MULTILINE)
USED = re.compile(r"var\(\s*(--[a-z0-9-]+)")
# Hex, or rgb()/rgba() with a literal triple. Not a var() inside one.
HEX = re.compile(r"#[0-9a-fA-F]{3,8}\b")

# AG Grid reads its own palette off these, so they are written for it rather than for
# us: defined here, used by a stylesheet we do not ship.
FOREIGN_PREFIXES = ("--ag-", "--q-")

# Set on the element while the page runs, from the workbench's own drag handlers, so
# the stylesheet reads them and never defines them.
RUNTIME = {"--dock-h", "--rows"}


def _ours(names):
    return {n for n in names
            if not n.startswith(FOREIGN_PREFIXES) and n not in RUNTIME}


class TokenTests(unittest.TestCase):
    def setUp(self) -> None:
        self.defined = _ours(set(DEFINED.findall(STYLESHEET)))
        self.used = _ours(set(USED.findall(STYLESHEET)))

    def test_every_var_resolves_to_a_token_that_exists(self) -> None:
        """`var(--warn)` shipped for weeks. A missing custom property is not an error
        in CSS - the declaration is dropped and the element inherits, so the only
        symptom is a color quietly being the wrong one."""
        self.assertEqual(sorted(self.used - self.defined), [])

    def test_every_token_has_a_user(self) -> None:
        """A token nothing reads is a decision nobody can see. Four of them
        accumulated - and one, `--fs-subject`, read like a heading level the Console had
        never actually had."""
        self.assertEqual(sorted(self.defined - self.used), [])


class LiteralTests(unittest.TestCase):
    """A ratchet, not a gate.

    The colors that already had a token are named. What is left has none, and each
    needs a name invented for it rather than a substitution - so the pass lands in
    pieces. This holds the direction while it does: the count comes down and never up.

    Lower CEILING as it falls. Raising it is the thing to notice.
    """

    CEILING = 18

    def test_no_new_color_is_typed_rather_than_named(self) -> None:
        found = sorted(set(HEX.findall(theme._FLAIR + theme._COMPONENTS)))

        self.assertLessEqual(
            len(found), self.CEILING,
            f"{len(found)} distinct unnamed colors, ceiling {self.CEILING}. "
            "Name it in _TOKENS and use var().")

    def test_the_token_block_is_where_a_color_is_named(self) -> None:
        """The other half: if the token block held no hex either, the ratchet would be
        passing because it is reading the wrong string."""
        self.assertTrue(HEX.findall(theme._TOKENS))


if __name__ == "__main__":
    unittest.main()
