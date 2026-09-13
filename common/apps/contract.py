"""What an app must answer to play an entry.

An app is the program that plays something; a launcher is a configured wrapper around
one and holds the values for the fields the app declares. This module is the whole of
the boundary: an implementation under `apps/` imports it and nothing else of ours.

Six capability groups. `claim` and `kinds` are declarations every app makes; `format`,
`launch`, `config` and `capability` are behavior, and None is a real answer for each.
Consumers ask before they call.

Nothing here takes or returns a VPinFE object.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass(frozen=True)
class Availability:
    available: bool
    # Required for a no: "unavailable" alone leaves a person nothing to act on.
    reason: str = ""


@dataclass(frozen=True)
class Field:
    """One thing configuring an app takes, shaped like `config_schema.ConfigOption`
    minus the section so a generated editor looks like every settings page."""

    key: str
    label: str
    type: str = "string"
    default: str = ""
    description: str = ""
    # `(value, label)` where the answers are a closed set. Stored value first.
    choices: tuple[tuple[str, str], ...] = ()
    # How many rows a `text` field gets; one line otherwise.
    lines: int = 0
    minimum: float | None = None
    maximum: float | None = None
    # "file", "dir" or "exe" where this names something on disk. Declared rather than
    # guessed from the key: `bin_path` and `ini_path` end the same way and want
    # different answers.
    path: str = ""


@dataclass(frozen=True)
class Entry:
    """One playable thing, as the app sees it.

    Three forms, and the form is read off what is set rather than stored: a `table`
    inside `game_dir` is contained, a `table` outside it is referenced, and a `key` with
    no file is keyed.
    """

    entry_id: str = ""
    # The folder. The launchable artifact inside it is the table.
    game_dir: str = ""
    # Absolute, and empty for a keyed entry.
    table: str = ""
    # The app's own native handle - a ROM name, a store id. Empty for a file-backed entry.
    key: str = ""


# --- claim ------------------------------------------------------------------------


@dataclass(frozen=True)
class Claim:
    """Which files and keys belong to this app. Suffixes are lowercase, with the dot."""

    suffixes: tuple[str, ...] = ()
    # Whether this app can play an entry that has no file at all.
    accepts_keys: bool = False
    # What travels with one of its tables, sharing the table's stem: a backglass, a
    # patched script, a point of view. Declared by the app because it is the app that
    # knows - a generic list here would be one program's habits taught to everything.
    companions: tuple[str, ...] = ()

    def claims(self, filename: str) -> bool:
        lowered = str(filename or "").lower()
        return any(lowered.endswith(suffix) for suffix in self.suffixes)

    def strip_suffix(self, filename: str) -> str:
        """Not `Path.stem`: "Foo (Bar 1.2).ext" keeps everything up to an extension we
        know, and only that."""
        name = str(filename or "")
        lowered = name.lower()
        found = next((s for s in self.suffixes if lowered.endswith(s)), "")
        return name[: -len(found)] if found else name


# --- format -----------------------------------------------------------------------


@dataclass(frozen=True)
class Parsed:
    """What reading one entry told us. What core does not model goes in `extra` under
    the app's own name, and nothing else reads it."""

    entry_id: str = ""
    title: str = ""
    version: str = ""
    author: str = ""
    release_date: str = ""
    manufacturer: str = ""
    year: str = ""
    # What the entry declares it needs. Whether it is installed is a machine fact,
    # answered by `capability`.
    rom: str = ""
    detects_emulator: bool | None = None
    file_hash: str = ""
    extra: Mapping[str, Any] = field(default_factory=dict)
    # Parsing a library must not stop at the first damaged file.
    error: str = ""


@runtime_checkable
class Format(Protocol):
    """`parse` takes a list and answers one per entry in order. Core calls it across a
    threaded library scan, and a per-entry call across a boundary gives that back."""

    def parse(self, entries: Sequence[Entry]) -> list[Parsed]: ...

    def script(self, entry: Entry, settings: Mapping[str, Any]) -> str: ...


# --- launch -----------------------------------------------------------------------

# How the end of a session is known. `NONE` is an answer rather than a gap: play stats
# have to say "we cannot tell when this ended" instead of recording three seconds.
SESSION_CHILD = "child"
SESSION_CHILD_WITH_READINESS = "child_with_readiness"
SESSION_DETACHED = "detached"
SESSION_NONE = "none"


@dataclass(frozen=True)
class Session:
    kind: str = SESSION_CHILD
    # For `child_with_readiness`: what the app writes once it is actually up.
    readiness_marker: str = ""


@runtime_checkable
class Launch(Protocol):
    """argv, never a shell string: substituting a path into a string that is then split
    is how a filename with a space becomes a crash or an injection."""

    def command(self, entry: Entry, settings: Mapping[str, Any]) -> list[str]: ...

    def session(self, settings: Mapping[str, Any]) -> Session: ...


# --- config -----------------------------------------------------------------------

# Where a value is written. A person reads these as "everything this launcher plays",
# "this folder" and "this table"; which file is behind each is the app's business.
SCOPE_LAUNCHER = "launcher"
SCOPE_FOLDER = "folder"
SCOPE_ENTRY = "entry"


@dataclass(frozen=True)
class ConfigGroup:
    """Declared rather than derived from the sections an app's file happens to have: a
    group can span sections and a section can feed two groups."""

    key: str
    label: str
    settings: tuple[Field, ...] = ()


@dataclass(frozen=True)
class ConfigValue:
    """One setting at a scope: what the app will use, and which layer answered.

    Four facts rather than a value, because somebody editing one layer of several has to
    see which layer is answering.
    """

    value: str = ""
    # Empty where nothing has set it and the app's own default wins.
    scope: str = ""
    set_here: bool = False
    # False with `set_here` true is a value another layer is shadowing - invisible
    # otherwise, and the bug report we would get.
    in_effect: bool = True
    # What would win if this scope stopped naming it, and which layer would supply it.
    # Clearing a value has to be able to say what it will follow instead, or somebody
    # has to change it to find out.
    fallback: str = ""
    fallback_scope: str = ""


@runtime_checkable
class Config(Protocol):
    """An app's own configuration, and where it keeps it.

    `files` names them; copying one somewhere safe is core's, which owns moving files
    for every kind already. Only the app knows which file its settings are in, and only
    core should be deciding where a copy of one goes.
    """

    def groups(self, settings: Mapping[str, Any]) -> tuple[ConfigGroup, ...]: ...

    def scopes(self) -> tuple[str, ...]: ...

    def read(self, scope: str, target: str,
             settings: Mapping[str, Any]) -> dict[str, ConfigValue]: ...

    def write(self, scope: str, target: str, values: Mapping[str, str],
              settings: Mapping[str, Any]) -> None: ...

    def files(self, settings: Mapping[str, Any]) -> dict[str, str]: ...


# --- kinds ------------------------------------------------------------------------


@dataclass(frozen=True)
class Kinds:
    """Which of core's kinds mean anything for this app's entries. An app narrows the
    set and never adds to it; None means all."""

    applicable: frozenset[str] | None = None

    def applies(self, kind: str) -> bool:
        return True if self.applicable is None else str(kind or "") in self.applicable


# --- capability -------------------------------------------------------------------


@runtime_checkable
class Capability(Protocol):
    """What this app can do on this machine right now, keyed by capability name. Probed
    from evidence: a version test that two builds eighteen months apart both satisfy
    answers nothing."""

    def probe(self, settings: Mapping[str, Any]) -> Mapping[str, Availability]: ...


# --- the app ----------------------------------------------------------------------


@dataclass(frozen=True)
class App:
    """`fields` is what a launcher of this app holds. `config` is the app's own
    settings surface, which is a different thing."""

    id: str
    name: str
    claim: Claim = Claim()
    fields: tuple[Field, ...] = ()
    kinds: Kinds = Kinds()
    format: Format | None = None
    launch: Launch | None = None
    config: Config | None = None
    capability: Capability | None = None
