"""Tracked code does not point at a document only one machine can read.

The design notes live outside the clone and are not published. A reference to one tells a
reader something exists, names it, and then cannot show it to them - which is worse than
saying nothing, because the reason is now somewhere they cannot go.

A PreToolUse hook already refuses a write that adds one. It checks what a call adds, so it
cannot see what predates it: two survived in `tests/` for weeks until a sweep found them.
This is the half that looks at what is already here.

The rule, in `docs/conventions.md`: state the reason instead. If the reason is too long to
state, it belongs in the design note alone and the code says nothing.
"""

from __future__ import annotations

import pathlib
import re
import subprocess
import unittest

REPO = pathlib.Path(__file__).resolve().parent.parent.parent

# Assembled rather than written out, for the same reason `test_no_private_library_data.py`
# assembles its own: a rule against naming these cannot name one to test itself.
SECTION_MARK = chr(0xA7)
PRIVATE_DOC = re.compile(r"[A-Za-z0-9_-]+\." + "local" + r"\.md")

# Only what git holds. An untracked note beside the code is nobody's business but this
# machine's, and the design documents themselves are exactly that.
SUFFIXES = {".py", ".md", ".js", ".toml", ".yml", ".yaml", ".spec", ".json"}

# The public docs may cite their own numbered sections; that is a reader following a link
# they can actually open. Only a pointer *out* of the tree is the problem.
ALLOWED = {
    "docs/conventions.md",
}


def _tracked() -> list[pathlib.Path]:
    found = subprocess.run(["git", "-C", str(REPO), "ls-files", "-z"],
                           capture_output=True, text=True, check=True)
    return [REPO / one for one in found.stdout.split("\0") if one]


def _offenders() -> list[str]:
    out = []
    for path in _tracked():
        if path.suffix.lower() not in SUFFIXES:
            continue
        relative = path.relative_to(REPO).as_posix()
        if relative in ALLOWED:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for number, line in enumerate(text.splitlines(), 1):
            if SECTION_MARK in line:
                out.append(f"{relative}:{number}: names a section of a document")
            hit = PRIVATE_DOC.search(line)
            if hit:
                out.append(f"{relative}:{number}: names a note that is not published")
    return out


class PrivateDocPointerTests(unittest.TestCase):
    def test_nothing_tracked_points_at_an_unpublished_note(self) -> None:
        """Say the reason. A pointer a reader cannot follow is worse than silence."""
        self.assertEqual(_offenders(), [], "\n".join([
            "These name a document, or a section of one, that is not in the tree.",
            "State the reason instead; if it is too long to state, leave it out.",
            *_offenders()]))

    def test_the_allowlist_only_names_files_that_exist(self) -> None:
        """A stale exemption silently widens the check."""
        gone = sorted(one for one in ALLOWED if not (REPO / one).exists())
        self.assertEqual(gone, [])

    def test_the_checker_can_actually_fail(self) -> None:
        """Both halves, against text written to break them."""
        self.assertIn(SECTION_MARK, f"see {SECTION_MARK}9 of the design")
        self.assertTrue(PRIVATE_DOC.search("read PLAYBACK." + "local" + ".md first"))
        self.assertFalse(PRIVATE_DOC.search("read docs/conventions.md first"))
