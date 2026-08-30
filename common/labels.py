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


def _word(word: str) -> str:
    return word.upper() if word.lower() in ACRONYMS else word[:1].upper() + word[1:]


def humanize(key: str) -> str:
    """`real_dmd_color` -> `Real DMD Color`. Word by word rather than `str.title`,
    which capitalizes after an apostrophe: "author's" would come back "Author'S"."""
    return _WORDS.sub(lambda m: _word(m.group(0)),
                      str(key or "").replace("_", " ")).strip()
