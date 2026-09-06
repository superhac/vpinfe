"""An app for a program VPinFE genuinely does not understand.

A binary and arguments, and an entry that is either a file or a key its program knows
how to look up. No parsing, no ROM resolution, no configuration surface, and no way to
tell when a session ended.

It is an app rather than a special case so that answering almost nothing is declared and
visible instead of discovered. It is also the contract's test case: two implementations,
one deliberately poor, is how we find out where the contract quietly assumed Visual
Pinball. It must never grow knowledge of a particular program - the first `if` on a
program's name is where the boundary dies, and a program worth special-casing has earned
its own app.
"""

from __future__ import annotations

import shlex
from collections.abc import Mapping
from typing import Any

from common.apps.contract import (
    SESSION_NONE,
    App,
    Availability,
    Claim,
    Entry,
    Field,
    Kinds,
    Session,
)

# A wheel, a video and a backglass are as true of an emulator or a video game as of a
# table. A script, a point of view, a ROM in our sense and the sidecars around them are
# not, and without saying so coverage reads "2 of 13" for an entry that can never have
# eleven of them.
KINDS: frozenset[str] = frozenset({
    "game_info", "media", "readme",
    "backglass", "scoreview", "playfield", "playfield_fss", "wheel", "cab",
    "real_dmd", "real_dmd_color", "flyer", "playfield_video", "backglass_video",
    "scoreview_video", "audio", "instruction_card", "topper", "topper_video",
    "loading", "audio_launch", "rule_sheet", "logo",
})

FIELDS: tuple[Field, ...] = (
    Field("bin_path", "Program", path="exe",
          description="The program this launcher runs."),
    Field("args", "Arguments",
          description="Arguments to pass, quoted the way a shell would be. Write "
                      "{table} or {key} where the entry goes; left out, it is "
                      "added last."),
    Field("launch_env", "Environment",
          description="Variables to set before launching, one NAME=value per line."),
)


class GenericLaunch:
    def command(self, entry: Entry, settings: Mapping[str, Any]) -> list[str]:
        """Substitution happens per argument, after the split. A path with a space in it
        breaks or injects when it is put into a string that is then split.

        An argument a substitution emptied is dropped rather than passed along as a bare
        "": a keyed entry has no table, and handing a program an empty argument is not
        the same as not handing it one.
        """
        args = shlex.split(str(settings.get("args") or ""))
        placed = [arg.replace("{table}", entry.table).replace("{key}", entry.key)
                  for arg in args]
        kept = [arg for arg in placed if arg]
        if placed == args:
            target = entry.table or entry.key
            if target:
                kept.append(target)
        return [str(settings.get("bin_path") or ""), *kept]

    def session(self, settings: Mapping[str, Any]) -> Session:
        """Unobservable, and said rather than implied. A program we know nothing about
        may hand off to another process and exit immediately, so waiting on the child
        would record a three-second session instead of a game."""
        return Session(kind=SESSION_NONE)


class GenericCapability:
    def probe(self, settings: Mapping[str, Any]) -> Mapping[str, Availability]:
        bin_path = str(settings.get("bin_path") or "").strip()
        if not bin_path:
            return {"program": Availability(False, "This launcher has no program set.")}
        return {"program": Availability(True)}


# Claims no suffix at all: a file this app could play is one a person pointed a launcher
# at, and claiming an extension here would let it take tables away from the app that
# actually understands them.
GENERIC = App(
    id="generic",
    name="Generic",
    claim=Claim(accepts_keys=True),
    fields=FIELDS,
    kinds=Kinds(applicable=KINDS),
    launch=GenericLaunch(),
    capability=GenericCapability(),
)
