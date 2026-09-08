"""What a user's command can say, and what each thing stands for.

Declared, the way settings are: each token says what it is, what it resolves to, and
where it is available. Declared rather than assembled at the call site because a surface
that offers them has to be able to list them - the difference between a feature people
use and one they guess at.

Two rules matter more than the list.

**Substituted into an argument, never into the line.** A line is split into arguments
first and each argument is resolved on its own, so a path with a space in it is one
argument. Resolving first and splitting after is how the same path becomes two arguments,
or worse.

**An unknown name refuses.** Resolving it to nothing turns `--config {launcher_ini}` into
a dangling flag that the program reads as whatever comes next. Not knowing a name and
having no value for one are different answers and both are said out loud.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Where a command runs, which decides what there is to talk about. VPinFE starting has no
# game and no launcher; a table starting has both.
VPINFE = "vpinfe"
TABLE = "table"

# `{name}`. Braces are free: media specs use `(Wheel)`.
TOKEN = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")


@dataclass(frozen=True)
class Token:
    name: str
    says: str
    contexts: frozenset[str]


TOKENS: tuple[Token, ...] = (
    Token("game_dir", "The folder the game is in", frozenset({TABLE})),
    # `table`, not `game_file`: the launchable artifact is a table everywhere else here.
    Token("table", "The full path of the table being played", frozenset({TABLE})),
    Token("table_stem", "The table's filename without its extension", frozenset({TABLE})),
    Token("game_name", "What the game is called", frozenset({TABLE})),
    Token("id", "The table's id", frozenset({TABLE})),
    Token("key", "The app's own name for the entry, where it has one",
          frozenset({TABLE})),
    Token("rom", "The ROM the table declares, where it declares one", frozenset({TABLE})),
    Token("launcher_bin", "The program this launcher runs", frozenset({TABLE})),
    Token("launcher_ini", "The configuration file this launcher reads",
          frozenset({TABLE})),
    Token("location", "The folder the library found this game under",
          frozenset({TABLE})),
    Token("player", "The player this is being recorded against",
          frozenset({VPINFE, TABLE})),
    # After the fact, so only the half that runs after has them.
    Token("exit_code", "What the program exited with", frozenset({TABLE})),
    Token("duration", "How long it ran, in whole seconds", frozenset({TABLE})),
)

# Which of them only mean anything once something has finished.
AFTER_ONLY = frozenset({"exit_code", "duration"})


class UnknownTokenError(ValueError):
    """A name no token declares. Its own type because the surface says something
    different for it than for a command that simply failed."""


def offered(context: str, *, after: bool = False) -> tuple[Token, ...]:
    """The tokens a command in this context may use, in declared order."""
    return tuple(one for one in TOKENS
                 if context in one.contexts and (after or one.name not in AFTER_ONLY))


def resolve(argument: str, values: dict[str, str], *, context: str,
            after: bool = False) -> str:
    """One argument, with its names filled in.

    A name this context does not offer is refused by name, so the message says which
    word was wrong rather than that something was.
    """
    known = {one.name for one in offered(context, after=after)}

    def swap(found: re.Match[str]) -> str:
        name = found.group(1)
        if name not in known:
            raise UnknownTokenError(name)
        return str(values.get(name, ""))

    return TOKEN.sub(swap, argument)


def unknown_names(text: str, *, context: str, after: bool = False) -> list[str]:
    """Every name in this text that the context does not offer, for a surface that has
    to say so while somebody is still typing."""
    known = {one.name for one in offered(context, after=after)}
    return sorted({name for name in TOKEN.findall(text) if name not in known})
