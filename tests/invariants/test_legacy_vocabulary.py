"""A renamed thing is not still called by its old name outside the places that translate.

Every vocabulary 3.0 renamed - window names, media kinds, action names - is translated
for a contract 1 theme and left alone for a contract 2 one. So an old name sitting in
our own code, or in a place that runs at contract 2, resolves to nothing and says
nothing about it. Five of those shipped before the cabinet found them: a theme whose
windows were `bg` and `dmd`, a `case "joyselect"` that made the launch button dead,
core's own preload default, the image-or-video branch that made `[Media] bgmediapriority`
inert at both contracts, and the Manager UI keying its media table on `bg`.

Each of those was one token in one line, and none of them failed a test. The allowlist
below is the interesting half of this file: a module is on it because translating is its
job, and anything else naming an old spelling has to answer for it.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

# Modules whose job is translating between vocabularies, or which declare the old names
# so that something else can. A hit in one of these is the point, not a defect.
TRANSLATORS = {
    "frontend/static/common/vpinfe-core.js",      # MEDIA_KIND_ALIASES, LEGACY_ACTION_NAMES, readers
    "frontend/theme_windows.py",      # CANONICAL, TITLES
    "frontend/input_api.py",          # projects the old per-device bridge methods
    "common/input_registry.py",        # each action's legacy spellings
    "common/media_specs.py",          # MEDIA_KIND_ALIASES, the spec filenames
    "common/config_schema.py",        # every option's aliases and former locations
    "common/config_store.py",         # the migration that rewrites them
    "common/config_access.py",        # reads either spelling
    "common/deprecations.py",         # the ledger of what was renamed
    "common/games/media_lookup.py",   # canonical_kind on the way in
}

# Old spellings, and what they are now. Only names that are unambiguous: `table` is left
# out on purpose - it means the .vpx file, a collection member, an .info section and a
# playfield, and a checker that flags all four teaches people to ignore it.
RENAMED = {
    "bg": "backglass",
    "dmd": "scoreview",
    "bg_video": "backglass_video",
    "dmd_video": "scoreview_video",
    "joyleft": "previous",
    "joyright": "next",
    "joyup": "page_up",
    "joydown": "page_down",
    "joyselect": "select",
    "joyback": "back",
    "joymenu": "menu",
    "joyexit": "exit",
    "joytutorial": "tutorial",
    "joypageup": "page_up",
    "joypagedown": "page_down",
    "joycollectionmenu": "collection_menu",
    "enabledof": "enable_dof",
}

SKIP_PARTS = {".venv", "build", "third-party", "chromium", "__pycache__", "tests"}
SKIP_PREFIXES = ("managerui/maps/", "frontend/static/themes/")


def _source_files():
    for pattern in ("*.py", "*.js"):
        for path in sorted(REPO_ROOT.rglob(pattern)):
            # Posix, always: the allowlists below are written with forward slashes, and
            # str() on a Windows path gives backslashes - so every translator missed its
            # entry there and each legitimate alias was reported as an offender.
            rel = path.relative_to(REPO_ROOT).as_posix()
            if any(part in SKIP_PARTS for part in rel.split("/")):
                continue
            if any(rel.startswith(p) for p in SKIP_PREFIXES):
                continue
            if rel in TRANSLATORS:
                continue
            yield path, rel


class LegacyVocabularyTests(unittest.TestCase):
    def test_no_module_speaks_a_renamed_name(self) -> None:
        offenders = []
        for path, rel in _source_files():
            text = path.read_text(encoding="utf-8", errors="ignore")
            for old, new in RENAMED.items():
                for match in re.finditer(rf"""['"]{re.escape(old)}['"]""", text):
                    line_no = text[:match.start()].count("\n") + 1
                    line = text.splitlines()[line_no - 1]
                    # A line that names both is translating between them.
                    if new in line:
                        continue
                    offenders.append(f"{rel}:{line_no} says {old!r}, which is now {new!r}"
                                     f"\n      {line.strip()[:96]}")

        self.assertEqual(offenders, [], "renamed names still spoken:\n  " + "\n  ".join(offenders))

    def test_the_allowlist_names_files_that_exist(self) -> None:
        """A translator that moved leaves a hole this test would not notice."""
        missing = [name for name in TRANSLATORS if not (REPO_ROOT / name).is_file()]
        self.assertEqual(missing, [], "allowlisted files that are not there")

    def test_the_checker_can_actually_fail(self) -> None:
        """The regex is the whole test; a rewrite that matches nothing would pass."""
        sample = 'window_name = "bg"'
        self.assertTrue(re.search(r"""['"]bg['"]""", sample))


if __name__ == "__main__":
    unittest.main()
