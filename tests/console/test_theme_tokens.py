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
LITERAL = re.compile(r"#[0-9a-fA-F]{3,8}\b"
                     r"|rgba?\(\s*\d+\s*,\s*\d+\s*,\s*\d+\s*(?:,\s*[\d.]+\s*)?\)")
COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)

# AG Grid reads its own palette off these, so they are written for it rather than for
# us: defined here, used by a stylesheet we do not ship.
FOREIGN_PREFIXES = ("--ag-", "--q-")

# Set on the element while the page runs, from the workbench's own drag handlers, so
# the stylesheet reads them and never defines them.
RUNTIME = {"--dock-h", "--rows"}


def _same_color(literal):
    """One color typed two ways is one color: `rgba(15,7,34,.75)` and
    `rgba(15, 7, 34, 0.75)` differ only in whitespace."""
    return "".join(literal.split()).lower()


def _colors_typed_in(css):
    """Comments first, because a comment naming the color it rejected is the reason
    the rule reads the way it does. Counting those made the number argue against
    writing them down."""
    return {_same_color(m) for m in LITERAL.findall(COMMENT.sub("", css))}


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
    """A ceiling on colors typed by hand, not a ban on them.

    The colors that already had a token are named. What is left has none, and each
    needs a name invented for it rather than a substitution - so the pass lands in
    pieces. This holds the direction while it does: the count comes down and never up.

    Lower CEILING as it falls. Raising it is the thing to notice - with one exception
    already spent: it went 18 -> 61 when the pattern started matching the rgb()/rgba()
    it had always claimed to match. Fifty colors were there the whole time.
    """

    CEILING = 24

    def test_no_new_color_is_typed_rather_than_named(self) -> None:
        found = _colors_typed_in(theme._FLAIR + theme._COMPONENTS)

        self.assertLessEqual(
            len(found), self.CEILING,
            f"{len(found)} distinct unnamed colors, ceiling {self.CEILING}. "
            "Name it in _TOKENS and use var().")

    def test_the_token_block_is_where_a_color_is_named(self) -> None:
        """The other half: if the token block held no hex either, the count above would
        be passing because it is reading the wrong string."""
        self.assertTrue(LITERAL.findall(theme._TOKENS))


if __name__ == "__main__":
    unittest.main()
