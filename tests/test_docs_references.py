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
import subprocess
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

# `pages/games.py` - relative, the reader supplies the package. Checked by name like a
# bare reference, since only the filename is ours to resolve. Restricted to our own
# package directories so a user's `medias/wheel.png` is not mistaken for source.
PACKAGE_DIRS = {"pages", "services", "static", "host", "online", "games"}
RELATIVE_REF = re.compile(r"`((?:" + "|".join(PACKAGE_DIRS) + r")/[A-Za-z0-9_.-]+\.(?:py|css|js))`")

# `managerui.services.game_index_service` - an import, not a path. Needs two dots or more,
# which keeps `managerui.py` out: that is a filename that happens to contain one.
DOTTED_REF = re.compile(r"`(?:managerui|common|httpapi|frontend)((?:\.[a-z_]+){2,})`")

# load_page_style("games.css") in a fenced example - no backticks to match on.
QUOTED_FILE = re.compile(r'"([A-Za-z0-9_.-]+\.(?:py|css))"')


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
        # Tracked files only. rglob walks .venv too, where NiceGUI ships its own
        # elements/table.py - which was enough to make a dead `table.py` reference look
        # resolved.
        listed = subprocess.run(["git", "-C", str(REPO_ROOT), "ls-files"],
                                capture_output=True, text=True, check=True).stdout.split()
        files = [REPO_ROOT / item for item in listed]
        present = {p.name for p in files}
        # `pages/games.py` has to match on the tail, not the name: `tables.py` is a real
        # file under common/games/, so a name-only check calls `pages/tables.py` fine.
        tails = {p.relative_to(REPO_ROOT).as_posix() for p in files}

        def known(ref: str) -> bool:
            if "/" in ref:
                return any(t == ref or t.endswith("/" + ref) for t in tails)
            return ref in present

        missing = []
        for doc in _doc_files():
            if not doc.is_file():
                continue
            for number, line in enumerate(doc.read_text(encoding="utf-8").splitlines(), 1):
                cited = set(BARE_REF.findall(line))
                cited.update(RELATIVE_REF.findall(line))
                cited.update(QUOTED_FILE.findall(line))
                cited.update(d.rsplit(".", 1)[-1] + ".py" for d in DOTTED_REF.findall(line))

                for ref in sorted(cited):
                    if ref in KNOWN_ABSENT_FILES or known(ref):
                        continue
                    missing.append(f"{doc.name}:{number} cites {ref!r}")

        self.assertEqual(missing, [], "\n".join(missing))


class DocImportExampleTests(unittest.TestCase):
    """An import in a doc example has to be one a reader can actually run.

    The rename moved `apply_table_filters` and `get_tables_path` without the docs
    following, so three examples imported names that are not there - code a reader would
    copy, paste and watch fail. Unlike a path, an import can simply be executed.
    """

    IMPORT = re.compile(r"^from ((?:managerui|common|httpapi|frontend)[\w.]*) import (.+)$")

    def test_every_documented_import_resolves(self) -> None:
        import importlib

        broken = []
        for doc in _doc_files():
            if not doc.is_file():
                continue
            for number, line in enumerate(doc.read_text(encoding="utf-8").splitlines(), 1):
                found = self.IMPORT.match(line.strip())
                if not found:
                    continue
                module_name, names = found.group(1), found.group(2)
                try:
                    module = importlib.import_module(module_name)
                except ImportError:
                    broken.append(f"{doc.name}:{number} cannot import {module_name!r}")
                    continue
                for name in (n.strip() for n in names.split(",")):
                    if name and not hasattr(module, name):
                        broken.append(f"{doc.name}:{number} {module_name} has no {name!r}")

        self.assertEqual(broken, [], "\n".join(broken))


class DocRouteTests(unittest.TestCase):
    """A route in the docs has to be a route the app serves.

    `GET /api/v1/collections/{name}/tables` was documented after the API had moved to
    `/games`, so the endpoint table sent a reader to a 404. Routes are worth checking
    separately from paths on disk: the app can answer what the filesystem cannot.
    """

    # FastAPI serves these itself, so they are absent from the paths it reports.
    SERVED_ELSEWHERE = {"/api/v1/openapi.json", "/api/v1/docs"}
    ROUTE = re.compile(r"`(/api/v1/[A-Za-z0-9_{}/.-]*)`")

    def test_every_documented_route_exists(self) -> None:
        import httpapi

        real = set(httpapi.create_api_app().openapi()["paths"])
        # Every literal segment the app actually uses. Anything else in a doc URL is a
        # stand-in - `{id}` or a sample id like `tuF3WogthK` - and normalizes to one.
        literals = {seg for route in real for seg in route.split("/") if seg and "{" not in seg}

        def shape(route: str) -> str:
            route = re.sub(r"^/api/v1", "", route).rstrip("/") or "/"
            return "/".join(s if s in literals else "{}" for s in route.split("/"))

        known = {shape(r) for r in real}
        missing = []
        for doc in _doc_files():
            if not doc.is_file():
                continue
            for number, line in enumerate(doc.read_text(encoding="utf-8").splitlines(), 1):
                for ref in self.ROUTE.findall(line):
                    if ref in self.SERVED_ELSEWHERE or shape(ref) in known:
                        continue
                    missing.append(f"{doc.name}:{number} documents {ref!r}")

        self.assertEqual(missing, [], "\n".join(missing))


if __name__ == "__main__":
    unittest.main()
