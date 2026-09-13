"""The token layer, checked. It had no test and it decayed.

In a few weeks the stylesheet grew four tokens nothing referenced and one that was
referenced and never defined - `var(--warn)`, which resolves to nothing, so a menu item
meant to read as destructive drew in the inherited color instead. Nothing failed,
because nothing was looking.

Three rules, and they are the seam the tokenizing pass needs under it: every `var()`
resolves, every token has a user, and a color is named rather than typed.
"""

from __future__ import annotations

import pathlib
import re
import unittest

from console import theme

# Every block that ships, in one string - a token may be defined in one and used in
# another, and checking them apart would report both halves as broken.
STYLESHEET = (theme.palette_css() + theme._SCROLLBAR
              + theme._FLAIR + theme._COMPONENTS)

DEFINED = re.compile(r"^\s*(--[a-z0-9-]+)\s*:", re.MULTILINE)
USED = re.compile(r"var\(\s*(--[a-z0-9-]+)")
# A palette is also read from Python: the nine Quasar brand values are looked up with
# `_token("--x")` rather than through a rule, and a token only read that way still has a
# reader. Without this, naming one is punished for not being written in CSS.
FROM_PYTHON = re.compile(r'_token\(\s*"(--[a-z0-9-]+)"')
# Hex, or rgb()/rgba() with a literal triple. Not a var() inside one.
LITERAL = re.compile(r"#[0-9a-fA-F]{3,8}\b"
                     r"|rgba?\(\s*\d+\s*,\s*\d+\s*,\s*\d+\s*(?:,\s*[\d.]+\s*)?\)")
COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
# A mask is a stencil, not a paint: inside one, black and white are the opacity
# channel and mean "hide this" and "keep this". A mode never restates them, so
# counting them as colors would leave a number that can never reach zero.
MASK = re.compile(r"(?:-webkit-)?mask(?:-image)?\s*:[^;]*;")

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
    writing them down. Masks after, for the reason above them."""
    return {_same_color(m)
            for m in LITERAL.findall(MASK.sub("", COMMENT.sub("", css)))}


def _ours(names):
    return {n for n in names
            if not n.startswith(FOREIGN_PREFIXES) and n not in RUNTIME}


class TokenTests(unittest.TestCase):
    def setUp(self) -> None:
        self.defined = _ours(set(DEFINED.findall(STYLESHEET)))
        source = pathlib.Path(theme.__file__).read_text(encoding="utf-8")
        self.used = _ours(set(USED.findall(STYLESHEET))
                          | set(FROM_PYTHON.findall(source)))

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


class PaletteTests(unittest.TestCase):
    """Every mode has to answer for every token.

    A mode that omits one does not fall back to another mode - there is no other mode in
    the page. The `var()` resolves to nothing, the declaration is dropped, and the element
    inherits whatever is above it. That is the same silent failure `--warn` shipped as,
    except a whole palette can carry it.
    """

    def test_every_palette_declares_the_same_tokens(self) -> None:
        declared = {mode: set(DEFINED.findall(block))
                    for mode, block in theme.PALETTES.items()}
        base = declared[theme.DEFAULT_MODE]
        for mode, names in declared.items():
            self.assertEqual(sorted(names ^ base), [],
                             f"{mode} does not declare the same tokens as "
                             f"{theme.DEFAULT_MODE}")

    def test_every_mode_renders_a_block_that_resolves(self) -> None:
        """The stylesheet is one string per mode, so a mode is only real if the rules
        can read it."""
        rules = theme._SCROLLBAR + theme._SURFACES + theme._REMOTE + \
            theme._FLAIR + theme._COMPONENTS
        want = _ours(set(USED.findall(rules)))
        for mode in theme.PALETTES:
            # Everything that ships in this mode - a few tokens are declared inside a
            # scoped rule rather than in the palette, and those resolve just as well.
            have = _ours(set(DEFINED.findall(theme.palette_css(mode) + rules)))
            self.assertEqual(sorted(want - have), [], f"{mode} leaves these unresolved")


class LiteralTests(unittest.TestCase):
    """A ceiling on colors typed by hand, not a ban on them.

    The colors that already had a token are named. What is left has none, and each
    needs a name invented for it rather than a substitution - so the pass lands in
    pieces. This holds the direction while it does: the count comes down and never up.

    Lower CEILING as it falls. Raising it is the thing to notice - with one exception
    already spent: it went 18 -> 61 when the pattern started matching the rgb()/rgba()
    it had always claimed to match. Fifty colors were there the whole time.
    """

    CEILING = 0

    def test_no_new_color_is_typed_rather_than_named(self) -> None:
        found = _colors_typed_in(theme._FLAIR + theme._COMPONENTS)

        self.assertLessEqual(
            len(found), self.CEILING,
            f"{len(found)} distinct unnamed colors, ceiling {self.CEILING}. "
            "Name it in the palette and use var().")

    def test_the_token_block_is_where_a_color_is_named(self) -> None:
        """The other half: if the palette held no hex either, the count above would
        be passing because it is reading the wrong string."""
        self.assertTrue(LITERAL.findall(theme.palette_css()))


if __name__ == "__main__":
    unittest.main()
