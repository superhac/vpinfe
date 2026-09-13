"""Reading a Windows registry export.

A `.reg` file is the one form of a foreign machine's registry that arrives as a file, so
it is the one a library reached over a share can carry. The format is small and
documented: a header line, a bracketed key path, then `"name"=value` lines under it.

Values are typed by prefix. `dword:` is hex, a bare quoted string is text, `hex:` is
bytes, and the parenthesised forms carry the type the byte string should be read as.
Everything is returned as it was written as well as decoded, because a value we cannot
usefully decode is still one somebody may want to see.

Written in UTF-16 with a byte-order mark, like a PinballX config - a plain UTF-8 read of
one raises rather than returning nonsense, which is the good case.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

HEADER = "Windows Registry Editor"
KEY_LINE = re.compile(r"^\[(-?)([^]]+)\]\s*$")
VALUE_LINE = re.compile(r'^\s*(?:"((?:[^"\\]|\\.)*)"|(@))\s*=\s*(.*)$')

# The types a .reg file writes. Anything else is carried as its raw text.
DWORD = "dword"
QWORD = "hex(b)"
EXPAND = "hex(2)"
MULTI = "hex(7)"
BINARY = "hex"


@dataclass
class Key:
    """One registry key and the values directly under it."""

    path: str
    values: dict = field(default_factory=dict)
    # `[-HKEY...]` in an export means "delete this key". Kept rather than dropped: a
    # file that removes a setting is saying something about the machine it came from.
    removed: bool = False


def _unescape(text: str) -> str:
    return (text.replace(r"\\", "\x00").replace(r"\"", '"')
            .replace("\x00", "\\"))


def _bytes_from(text: str) -> bytes:
    parts = [one.strip() for one in text.split(",") if one.strip()]
    try:
        return bytes(int(one, 16) for one in parts)
    except ValueError:
        return b""


def decode(raw: str):
    """A written value, as the thing it stands for, or None where we cannot say.

    None is an answer here rather than a failure: the caller keeps the raw text either
    way, and guessing at a byte string's meaning would be worse than saying nothing.
    """
    text = raw.strip()
    if text.startswith('"') and text.endswith('"') and len(text) >= 2:
        return _unescape(text[1:-1])
    if text.startswith(f"{DWORD}:"):
        try:
            return int(text.split(":", 1)[1].strip(), 16)
        except ValueError:
            return None
    if text.startswith(f"{QWORD}:"):
        data = _bytes_from(text.split(":", 1)[1])
        return int.from_bytes(data, "little") if len(data) == 8 else None
    if text.startswith(f"{EXPAND}:"):
        return _bytes_from(text.split(":", 1)[1]).decode("utf-16-le", "replace") \
            .rstrip("\x00")
    if text.startswith(f"{MULTI}:"):
        joined = _bytes_from(text.split(":", 1)[1]).decode("utf-16-le", "replace")
        return [one for one in joined.split("\x00") if one]
    if text.startswith(f"{BINARY}:") or text.startswith("hex("):
        return None
    return None


def read_text(path: Path | str) -> tuple[str, str]:
    """The file's text, and anything worth saying about reading it.

    UTF-16 first because that is what the editor writes, then the UTF-8 forms, because a
    file somebody produced by hand or converted is a real thing to meet.
    """
    path = Path(path)
    for encoding in ("utf-16", "utf-8-sig", "utf-8"):
        try:
            return path.read_text(encoding=encoding), ""
        except UnicodeError:
            continue
        except OSError as exc:
            return "", f"{path.name} could not be read: {exc}"
    return "", f"{path.name} is not in an encoding this can read"


def parse(text: str) -> list[Key]:
    """Every key in an export, in the order it appears."""
    found: list[Key] = []
    current: Key | None = None
    pending = ""

    for line in text.splitlines():
        if pending:
            line = pending + line.strip()
            pending = ""
        stripped = line.strip()
        if not stripped or stripped.startswith(";") or stripped.startswith(HEADER):
            continue
        key = KEY_LINE.match(stripped)
        if key:
            current = Key(path=key.group(2).strip(), removed=bool(key.group(1)))
            found.append(current)
            continue
        if current is None:
            continue
        value = VALUE_LINE.match(line)
        if not value:
            continue
        raw = value.group(3).strip()
        # A long binary value is wrapped with a trailing backslash and continues on the
        # next line. Joined before it is read, or every one of them is truncated.
        while raw.endswith("\\"):
            pending = raw[:-1]
            break
        if pending:
            pending = f'"{value.group(1) or "@"}"={pending}'
            continue
        name = "@" if value.group(2) else _unescape(value.group(1) or "")
        current.values[name] = {"raw": raw, "value": decode(raw)}
    return found


def read(path: Path | str) -> tuple[list[Key], str]:
    text, said = read_text(path)
    if not text:
        return [], said
    if HEADER not in text.splitlines()[0]:
        return [], f"{Path(path).name} does not look like a registry export"
    return parse(text), said


# What VPinMAME keeps, and where. Verified out of the binaries on a real cabinet share
# rather than recalled - the key is spelled `PinMame` where the product is `PinMAME`.
VPINMAME = r"Software\Freeware\Visual PinMame"
# Paths that belong to the machine rather than to any game.
GLOBALS = "globals"
# What every ROM starts from.
DEFAULTS = "default"


def settings_for(keys: list[Key], rom: str) -> dict:
    """One ROM's settings, as VPinMAME would actually see them.

    A per-ROM key is usually a whole record and occasionally a sparse override, so the
    two are layered here once rather than left for each caller to remember. Measured
    against a real export of 398 ROMs: 397 of them held the full 114 values, `default`
    held 33 and every one of those also appeared in the ROM keys, and exactly one ROM
    held a single value and nothing else. Reading a key alone is therefore right almost
    always and silently wrong for that one, which is the worst shape a bug can have.

    Only 11 values ever differed from `default` across that whole library, nearly all of
    them DMD colour. So the merge is cheap and changes little - it is there for the rare
    key, not the common one.

    `globals` is deliberately not merged in: rompath and the directories are facts about
    the old machine, not about a game, and folding them into a game's settings would
    carry one cabinet's paths onto another.
    """
    held = under(keys, VPINMAME)
    merged = dict(held.get(DEFAULTS) or {})
    merged.update(held.get(str(rom or "").strip().lower(), {}) or {})
    return merged


def machine_settings(keys: list[Key]) -> dict:
    """What the old machine was configured with, as opposed to any one game."""
    return dict(under(keys, VPINMAME).get(GLOBALS) or {})


def roms(keys: list[Key]) -> list[str]:
    """Every ROM the export carries settings for, and nothing that is not one."""
    return sorted(name for name in under(keys, VPINMAME)
                  if name.lower() not in (GLOBALS, DEFAULTS) and "\\" not in name)


def under(keys: list[Key], prefix: str) -> dict[str, dict]:
    """The keys below one path, by what follows it.

    Case-folded, because a registry is case-insensitive about paths and an export
    carries whatever case the exporter felt like - the one on this machine's own
    binaries writes `Visual PinMame` where the product is spelled `PinMAME`.
    """
    wanted = prefix.strip("\\").lower()
    found: dict[str, dict] = {}
    for key in keys:
        path = key.path.replace("/", "\\").strip("\\")
        low = path.lower()
        marker = f"\\{wanted}\\"
        if marker not in f"\\{low}\\":
            continue
        tail = path[low.index(wanted) + len(wanted):].strip("\\")
        if tail:
            # Keyed folded, because a ROM name in an export carries whatever case the
            # exporter used and a caller has the name off a table's own record.
            found[tail.lower()] = dict(key.values)
    return found
