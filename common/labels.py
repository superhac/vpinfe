"""A key as a person reads it, for where nothing has named it.

**The fallback, never the first answer.** `MediaSpec.label`, `AssetSpec.label`,
`FilterAxis.label` and `ConfigOption.label` all name their own things, and a registry
that knows the thing beats a rule that guesses at it.
"""

from __future__ import annotations

import re

# Only the acronyms VPinFE puts in a key. A general list would capitalize words that are
# ordinary here and be wrong more often than right.
ACRONYMS = frozenset({
    "api", "b2s", "cpu", "dmd", "dof", "fps", "fss", "gpu", "http", "https", "id",
    "ini", "ip", "json", "led", "nvram", "pup", "rgb", "rom", "ui", "url", "usb",
    "vni", "vps", "vpx", "vr",
})

_WORDS = re.compile(r"[^\W_]+(?:'[^\W_]+)*", re.UNICODE)


# Words a title leaves lowercase unless they lead or close it. "Point of View" is the
# house style already - `AssetSpec` writes it by hand - so a rule that produced "Point
# Of View" would disagree with the registry it is the fallback for.
SMALL_WORDS = frozenset({
    "a", "an", "and", "as", "at", "but", "by", "for", "from", "in", "into", "nor",
    "of", "on", "onto", "or", "over", "per", "so", "the", "to", "up", "via", "vs",
    "with", "yet",
})


def field_label(text: str) -> str:
    """A label as a person reads it: title case, acronyms as acronyms.

    One rule for every label the hub shows - a panel's fact, a column header, a picker
    entry - applied where they all pass rather than at each call site, so a hand-typed
    one cannot drift from the rest.

    Takes a key or a phrase, so `vps_id` and `VPS ID` both come back `VPS ID`.
    """
    said = str(text or "").replace("_", " ")
    found = list(_WORDS.finditer(said))
    last = len(found) - 1
    out, at = [], 0
    for place, match in enumerate(found):
        out.append(said[at:match.start()])
        out.append(_titled(match.group(0), lead_or_close=place in (0, last)))
        at = match.end()
    out.append(said[at:])
    return "".join(out).strip()


def _titled(word: str, *, lead_or_close: bool) -> str:
    """One word of a title. A small word stays down unless it leads or closes."""
    if word.lower() in ACRONYMS:
        return word.upper()
    if word.lower() in SMALL_WORDS and not lead_or_close:
        return word.lower()
    return word[:1].upper() + word[1:].lower()


def humanize(key: str) -> str:
    """`real_dmd_color` -> `Real DMD Color`. The older name, kept for the callers that
    read it; one rule now, so a column picker and a panel cannot case a word two ways."""
    return field_label(key)
