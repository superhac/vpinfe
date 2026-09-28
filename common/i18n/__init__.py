"""Every string a person reads, looked up rather than written where it is shown.

**English is a translation.** `en` is a catalog like any other and the code holds keys,
not text, so there is no path that only English takes - which is what stops English
working while every other language is quietly broken.

A key is namespaced by what *owns* the string, never by the screen showing it: a label
moves between screens constantly and never moves between owners. Each segment has to be
a word a translator already knows or the name of a file they can open, because the
catalog's third audience is somebody who has never read this code.

No lookup raises. A key with no entry falls back to English and then to the key
itself, because a missing translation is a blemish and a traceback is an outage.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import threading
from pathlib import Path
from typing import Any, get_args

logger = logging.getLogger("vpinfe.common.i18n")

CATALOGS = Path(__file__).parent / "catalogs"
SOURCE = "en"

# What a leaf of a key says about how much the string costs to keep. Prose churns every
# time a surface is reworded and is two thirds of the volume, so a locale translates the
# chrome and lets these fall back to English without that being a defect.
PROSE_LEAVES = frozenset({"help", "description", "summary"})

# What an owner's key may start with. Core's namespaces are never among them, so an
# owner adds words and cannot change one of ours.
OWNED = ("app.", "ext.")

_catalogs: dict[str, dict[str, Any]] = {}
_owners: dict[str, tuple[Path, str]] = {}
_lock = threading.Lock()
_language = SOURCE


def own(prefix: str, directory: Path, *, section: str = "") -> None:
    """Serve `<directory>/<language>.json` under `prefix`.

    With `section`, only the file's keys under it are served, with `section` read as
    `prefix`: an extension's file holds its apps' words beside its own.
    Raises ValueError for a prefix outside `OWNED`.
    """
    if not prefix.startswith(OWNED) or prefix.endswith("."):
        raise ValueError(f"{prefix!r} is not a prefix an owner can hold")
    with _lock:
        _owners[prefix] = (Path(directory), section)
        _catalogs.clear()


def disown(prefix: str) -> None:
    with _lock:
        if _owners.pop(prefix, None) is not None:
            _catalogs.clear()


def _read(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except Exception:
        logger.warning("Could not read %s; treating it as empty", path)
        return {}


def _load(name: str) -> dict[str, Any]:
    found = _catalogs.get(name)
    if found is not None:
        return found
    with _lock:
        merged = _read(CATALOGS / f"{name}.json")
        for prefix, (directory, section) in _owners.items():
            under = f"{section}." if section else ""
            for key, entry in _read(directory / f"{name}.json").items():
                if key.startswith(under):
                    merged[f"{prefix}.{key[len(under):]}"] = entry
        _catalogs[name] = merged
        return merged


def chain(language: str = "") -> tuple[str, ...]:
    """The catalogs to try, most specific first. `de-AT` asks `de` before `en`."""
    said = (language or _language or SOURCE).replace("_", "-")
    out = [said]
    if "-" in said:
        out.append(said.split("-", 1)[0])
    if SOURCE not in out:
        out.append(SOURCE)
    return tuple(out)


def set_language(language: str) -> str:
    """Set the language every later lookup answers in, and say what was settled on.

    `auto` reads the operating system. An unknown name is not an error - it falls back
    through `chain`, so a typo costs English rather than a failed start.
    """
    global _language
    said = str(language or "").strip()
    if said.lower() in ("", "auto"):
        said = _from_the_system()
    _language = said
    return _language


def _from_the_system() -> str:
    """What the machine says it speaks, or English.

    The environment first, because `locale.getlocale()` answers `C` on a Mac that has
    never had `setlocale` called - and `C` is a POSIX default, not a language. Taking it
    at its word got `--lang=C` onto the browser command line.
    """
    import locale
    import os
    for value in (os.environ.get("LC_ALL"), os.environ.get("LC_MESSAGES"),
                  os.environ.get("LANG"), (locale.getlocale() or (None,))[0]):
        name = str(value or "").split(".")[0].split("@")[0].replace("_", "-").strip()
        if name and name.upper() not in ("C", "POSIX"):
            return name
    return SOURCE


def language() -> str:
    return _language


# Not a language. `qps` is the pseudo-locale the render check runs under - every letter
# replaced by one that is not ASCII, so anything still readable on screen never went
# through the catalog. Settable by hand for that test; never offered as a choice.
PSEUDO = "qps"


def available() -> tuple[str, ...]:
    """The catalogs on disk, so a settings control offers what exists."""
    return tuple(sorted(p.stem for p in CATALOGS.glob("*.json")
                        if not p.stem.endswith(".hashes") and p.stem != PSEUDO))


def is_prose(key: str) -> bool:
    return key.rsplit(".", 1)[-1] in PROSE_LEAVES


def first_key(*keys: str) -> str:
    """The first of these with an entry, or "" when none has one."""
    source = _load(SOURCE)
    return next((key for key in keys if key in source), "")


def literal_or(literal: str, *keys: str, fallback: str = "") -> tuple[str, str]:
    """The words and the key they came from: `literal` as written with no key, else the
    first of `keys` with an entry, else `fallback`."""
    if literal:
        return literal, ""
    key = first_key(*keys)
    return (t(key), key) if key else (fallback, "")


class _Blanks(dict):
    """A parameter nobody passed renders as its own name, not a KeyError.

    A translator can introduce a slot the caller does not fill, and one wrong brace
    should cost one ugly label rather than the page it is on.
    """

    def __missing__(self, key: str) -> str:
        logger.debug("No value for {%s}", key)
        return "{" + key + "}"


def _plural(forms: dict[str, Any], count: Any, language_name: str) -> str:
    """The form for this count. Two categories cover every language we ship."""
    try:
        number = abs(int(count))
    except (TypeError, ValueError):
        number = 1
    # Languages that do not count in the grammar take `other` for everything. The rest
    # of CLDR's categories arrive with the locale that needs them, not before.
    if language_name.split("-")[0] in ("ja", "zh", "ko", "vi", "th"):
        return str(forms.get("other") or "")
    return str(forms.get("one" if number == 1 else "other") or forms.get("other") or "")


def t_source(key: str, /, **params: Any) -> str:
    """What this key says in English, whatever language is set.

    For a log line. A log is read by whoever is debugging it and quoted into an issue,
    so it says the same thing on every install - which is the opposite of what the
    screen wants, and the reason these are two functions rather than one with a flag.
    """
    entry = _load(SOURCE).get(key)
    if isinstance(entry, dict):
        entry = _plural(entry, params.get("count"), SOURCE)
    return str(entry).format_map(_Blanks(params)) if entry else key


def t(key: str, /, **params: Any) -> str:
    """What this key says, in the language now set.

    Parameters are named and the whole sentence is one entry, so word order, agreement
    and punctuation belong to the translator. Never build a sentence by adding fragments
    together - the join is different in most languages and invisible in this one.
    """
    for name in chain():
        entry = _load(name).get(key)
        if entry is None:
            continue
        if isinstance(entry, dict):
            entry = _plural(entry, params.get("count"), name)
        if not entry:
            continue
        try:
            return str(entry).format_map(_Blanks(params))
        except (ValueError, IndexError):
            logger.warning("Could not fill %r from %s", key, name)
            return str(entry)
    logger.debug("No entry for %r in %s", key, "/".join(chain()))
    return key


# The locales NiceGUI ships a Quasar pack for. Ours is the wider set - a language with no
# pack still gets a fully translated VPinFE, just English date pickers - so this maps in
# rather than constraining what `language` may be set to.
# Where a language has several packs and no bare one, which we mean. `en` is US English
# throughout this repo, and sorting alphabetically would pick en-GB.
_PREFERRED_PACK = {"en": "en-US"}


def nicegui_language() -> str | None:
    """The closest Quasar pack to the language now set, or None to leave it unset."""
    try:
        from nicegui.language import Language
    except Exception:
        return None
    packs = set(get_args(Language))
    for name in chain():
        if name in packs:
            return name
        base = name.split("-")[0]
        if _PREFERRED_PACK.get(base) in packs:
            return _PREFERRED_PACK[base]
        matched = sorted(p for p in packs if p.split("-")[0] == base)
        if matched:
            return matched[0]
    return None


def under(prefix: str) -> dict[str, Any]:
    """Every entry below a prefix, resolved, with the prefix stripped.

    For handing a block of strings to something that wants them all at once - AG Grid's
    `localeText` is one dictionary, not a lookup per phrase.
    """
    out: dict[str, Any] = {}
    dotted = prefix if prefix.endswith(".") else prefix + "."
    for name in reversed(chain()):
        for key, entry in _load(name).items():
            if key.startswith(dotted):
                out[key[len(dotted):]] = dict(entry) if isinstance(entry, dict) else t(key)
    return out


# Month names are catalog entries and the order of the parts is a catalog entry, because
# neither is the same everywhere: "%d %b %Y" hardcodes both, and %b is English whatever
# the language is unless setlocale has been called process-wide, which is not a thing to
# do to a running app.
def date(when: dt.date) -> str:
    """A date as this language writes it. Short month, no leading zero on the day."""
    month = t(f"date.month.{when.month}")
    return t("date.short", day=when.day, month=month, year=when.year)


def number(value: int) -> str:
    """A whole number with its digits grouped as this language groups them."""
    return f"{value:,}".replace(",", t("number.group"))


_SIZE_UNITS = ("bytes", "kilobytes", "megabytes", "gigabytes", "terabytes")


def size(count: float) -> str:
    """A byte count as this language writes it. Powers of 1024; bytes whole, the rest
    to one decimal."""
    value, step = float(count), 0
    while abs(value) >= 1024 and step < len(_SIZE_UNITS) - 1:
        value /= 1024
        step += 1
    return t(f"size.{_SIZE_UNITS[step]}", value=f"{value:.0f}" if step == 0 else f"{value:.1f}")
