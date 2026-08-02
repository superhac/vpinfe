"""Docs may not name a file that is not there.

A doc that cites `common/tableparser.py` is not merely out of date - it sends a reader
to a path that does not exist, and nothing fails when it happens. The vocabulary rename
made several docs wrong this way at once: modules moved under `common/games/`, a
stylesheet became `games.css`, and the docs kept the old names.

Only repo-shaped paths are checked. A doc is full of paths that are not ours - a user's
`~/tables`, an example `<table>/pinmame/roms`, a media file inside a game folder - so the
first segment has to be a real top-level directory before a missing file counts.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Only paths rooted at one of these are ours to verify.
TOP_LEVEL = {"common", "frontend", "httpapi", "managerui", "web", "scripts", "tests",
             "docs", "icon"}

# `common/games/gameparser.py`, `managerui/static/games.css`, `common/host/`
PATH_REF = re.compile(r"`([a-z_]+(?:/[A-Za-z0-9_.-]+)+/?)`")

# A bare `games.css` or `gameparser.py` carries no directory, so it is checked by name
# against the whole tree instead. Without this the stylesheet rename read as clean: the
# doc still said `tables.css` and nothing had a path to disagree with.
BARE_REF = re.compile(r"`([A-Za-z0-9_.-]+\.(?:py|css|js))`")


# Two paths are cited on purpose by something that is not there, and both are right to be.
KNOWN_ABSENT = {
    # "Create a module in `managerui/pages/`, for example ..." - a file you would write.
    "managerui/pages/network.py",
    # PAR-20 records that this module was deleted. The ledger is a history, so it names
    # things that no longer exist; that is the entry's whole point.
    "common/info_restore.py",
}

# Bare names that are real files, just not ours to hold.
KNOWN_ABSENT_FILES = {
    "theme.js",                 # a theme author writes this one; we only document it
    "ledcontrol_pull.py",       # ships inside the third-party DOF package
    "libdmdutil_wrapper.py",    # ships inside the bundled libdmdutil package
}


def _doc_files() -> list[Path]:
    return sorted(REPO_ROOT.joinpath("docs").glob("*.md")) + [REPO_ROOT / "readme.md"]


class DocPathReferenceTests(unittest.TestCase):

    def test_every_repo_path_a_doc_cites_exists(self) -> None:
        missing = []
        for doc in _doc_files():
            if not doc.is_file():
                continue
            for number, line in enumerate(doc.read_text(encoding="utf-8").splitlines(), 1):
                for ref in PATH_REF.findall(line):
                    if ref.split("/")[0] not in TOP_LEVEL:
                        continue
                    if ref.rstrip("/") in KNOWN_ABSENT:
                        continue
                    # A trailing slash means a directory; both are just paths on disk.
                    if (REPO_ROOT / ref.rstrip("/")).exists():
                        continue
                    missing.append(f"{doc.name}:{number} cites {ref!r}")

        self.assertEqual(missing, [], "\n".join(missing))

    def test_every_bare_source_filename_a_doc_cites_exists(self) -> None:
        present = {p.name for p in REPO_ROOT.rglob("*")
                   if p.is_file() and ".git" not in p.parts}

        missing = []
        for doc in _doc_files():
            if not doc.is_file():
                continue
            for number, line in enumerate(doc.read_text(encoding="utf-8").splitlines(), 1):
                for ref in BARE_REF.findall(line):
                    if ref in KNOWN_ABSENT_FILES or ref in present:
                        continue
                    missing.append(f"{doc.name}:{number} cites {ref!r}")

        self.assertEqual(missing, [], "\n".join(missing))


if __name__ == "__main__":
    unittest.main()
