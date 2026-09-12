#!/usr/bin/env python3
"""Maintaining the translation catalogs. Run by a translator, not by the app.

A translation is a copy of `en.json` with the values rewritten. This reports what is
missing, what has gone stale because the English moved under it, and what nothing asks
for any more. Nothing here edits a translation - the file is the translator's.
"""

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CATALOGS = ROOT / "common" / "i18n" / "catalogs"
SOURCE = "en"
HASHES = CATALOGS / f"{SOURCE}.hashes.json"
PROSE_LEAVES = {"help", "description", "summary"}

# Where a key can be written. A key built at runtime - `f"filter.{name}.label"` - is
# found by its prefix, because the whole point of deriving it is that it is not typed out.
KEY_TEXT = re.compile(r"""["']([a-z][a-z0-9_]*(?:\.[a-z0-9_{}]+)+)["']""")
KEY_FSTRING = re.compile(r"""f["']([a-z][a-z0-9_]*(?:\.[a-z0-9_]*)*)\{""")


def load(name):
    path = CATALOGS / f"{name}.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True,
                                     ensure_ascii=False).encode()).hexdigest()[:12]


def tier(key):
    return "prose" if key.rsplit(".", 1)[-1] in PROSE_LEAVES else "chrome"


def referenced():
    """Every catalog key the tree asks for, literal or built from a prefix."""
    exact, prefixes = set(), set()
    for path in ROOT.rglob("*.py"):
        if any(p in path.parts for p in (".venv", "__pycache__", "tests", "scripts")):
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        exact.update(KEY_TEXT.findall(text))
        prefixes.update(KEY_FSTRING.findall(text))
    return exact, {p for p in prefixes if p}


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--missing", metavar="LANG", help="keys with no translation yet")
    ap.add_argument("--stale", metavar="LANG",
                    help="translations written against English that has since changed")
    ap.add_argument("--unused", action="store_true", help="catalog keys nothing asks for")
    ap.add_argument("--coverage", action="store_true", help="percentage per locale, per tier")
    ap.add_argument("--record", action="store_true",
                    help=f"rewrite {HASHES.name} to match {SOURCE}.json, after a reword")
    args = ap.parse_args()

    source = load(SOURCE)

    if args.record:
        HASHES.write_text(json.dumps({k: digest(v) for k, v in sorted(source.items())},
                                     indent=2) + "\n", encoding="utf-8")
        print(f"recorded {len(source)} keys in {HASHES.name}")
        return 0

    if args.missing:
        other = load(args.missing)
        gaps = [k for k in sorted(source) if not other.get(k)]
        for key in gaps:
            print(f"{tier(key):7} {key}")
        print(f"\n{len(gaps)} of {len(source)} keys have no {args.missing}")
        return 0

    if args.stale:
        other, recorded = load(args.stale), load(f"{SOURCE}.hashes")
        if not recorded:
            print(f"No {HASHES.name}. Run --record once to start tracking.", file=sys.stderr)
            return 1
        moved = [k for k in sorted(other)
                 if k in source and recorded.get(k) not in (None, digest(source[k]))]
        for key in moved:
            print(f"{key}\n    now: {source[key]}\n    has: {other[key]}")
        print(f"\n{len(moved)} {args.stale} entries were written against older English")
        return 0

    if args.unused:
        exact, prefixes = referenced()
        orphans = [k for k in sorted(source)
                   if k not in exact and not any(k.startswith(p) for p in prefixes)]
        for key in orphans:
            print(key)
        print(f"\n{len(orphans)} of {len(source)} catalog keys are asked for by nothing")
        return 0

    if args.coverage:
        names = sorted(p.stem for p in CATALOGS.glob("*.json")
                       if not p.stem.endswith(".hashes"))
        totals = {t: sum(1 for k in source if tier(k) == t) for t in ("chrome", "prose")}
        print(f"{'locale':10} {'chrome':>14} {'prose':>14}")
        for name in names:
            other = load(name)
            cells = []
            for t, total in totals.items():
                have = sum(1 for k in source if tier(k) == t and other.get(k))
                cells.append(f"{have:4}/{total:<4} {100*have//max(total,1):3}%")
            print(f"{name:10} {cells[0]:>14} {cells[1]:>14}")
        return 0

    ap.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
