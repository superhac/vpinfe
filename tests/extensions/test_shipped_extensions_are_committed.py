"""Every file an extension we ship is made of is in the tree.

`.gitignore` excludes `*.json` and names the exceptions, because config, logs and caches
are JSON and there are far more of those than files worth keeping. The cost is that
adding one without its negation fails **silently**: it is on the author's disk, every
test passes, and a clean checkout does not have it.

That is not a small loss here. An extension declares itself in `extension.json`, so a
checkout missing one has the code and nothing that says what it is - and the host refuses
every extension the build ships, which is the whole feature gone. It happened, twice, and
nothing said so.

Reads git rather than the filesystem, so it sees what a clean checkout would.
"""

from __future__ import annotations

import pathlib
import subprocess
import unittest

REPO = pathlib.Path(__file__).resolve().parents[2]
EXTENSIONS = REPO / "extensions"


def _tracked() -> set[pathlib.Path]:
    listed = subprocess.run(["git", "-C", str(REPO), "ls-files", "extensions"],
                            capture_output=True, text=True)
    return {REPO / line for line in listed.stdout.splitlines() if line.strip()}


@unittest.skipIf(not (REPO / ".git").exists(), "not a git checkout")
class ShippedExtensionsAreCommittedTests(unittest.TestCase):
    def test_there_are_extensions_to_check(self) -> None:
        """A check over an empty directory passes and means nothing."""
        self.assertTrue(list(EXTENSIONS.iterdir()))

    def test_every_extension_ships_its_manifest(self) -> None:
        """The one file without which an extension is not one."""
        tracked = _tracked()
        missing = [
            folder.name for folder in sorted(EXTENSIONS.iterdir())
            if folder.is_dir() and "__pycache__" not in folder.parts
            and (folder / "extension.json") not in tracked
        ]

        self.assertEqual(missing, [],
                         "these declare themselves in a file a clean checkout will not "
                         f"have: {missing}. Add a .gitignore negation in the same "
                         "commit.")

    def test_every_file_they_are_made_of_is_tracked(self) -> None:
        tracked = _tracked()
        on_disk = {path for path in EXTENSIONS.rglob("*")
                   if path.is_file() and "__pycache__" not in path.parts
                   and path.name != ".DS_Store"}

        self.assertEqual(sorted(str(one.relative_to(REPO)) for one in on_disk - tracked),
                         [])


if __name__ == "__main__":
    unittest.main()
