"""VPinFE's tests, grouped by what they exercise.

This file is what keeps the group folders from colliding with the packages they test:
without it, `tests/frontend/` is importable as top-level `frontend` and shadows the real
one. With it, every module is `tests.<group>.<name>` and nothing is ambiguous.

`python -m unittest discover tests` finds everything, as it always has.
"""

from __future__ import annotations

import os
import subprocess

# Nothing in the suite may power the machine off, restart it, or replace the test
# process with a new one.
#
# This is not hypothetical. A test that wired the real lifecycle performers and asked for
# a system stop shut a developer's Mac down, with no prompt and no warning: the confirm
# hook is off by default, so there is nothing between the request and the command. It
# happened twice - the second time from a check meant to prove this guard worked, which
# ran the suite with the guard removed.
#
# A test that means to exercise a power path patches `common.host.system_actions` and
# asserts on the patch. Reaching a real command is a bug in the test, so it raises rather
# than being quietly dropped: a swallowed one leaves the test passing while claiming to
# have done something it did not.
#
# Matched by program plus argument, not by loose keywords, because the same program is
# safe or not depending on what it is told:
#
#   Linux    systemctl poweroff | reboot | halt
#   macOS    osascript ... "shut down" / "restart";  shutdown -h / -r
#   Windows  shutdown /s | /r | /f;  wmic ... shutdown
#
# `shutdown` is the trap. On Windows it needs a flag to do anything, on macOS `-h`/`-r`,
# and a bare `shutdown --help` is harmless - so the program name alone is neither
# sufficient nor safe to match on.

# program -> (exact flags/verbs, substrings)
#
# A flag has to match an argument exactly, because `-h` is a substring of `--help` and
# blocking `shutdown --help` would be wrong. A substring matches anywhere in the line,
# because osascript carries its whole instruction inside one quoted argument.
_POWER_PROGRAMS = {
    "systemctl": (("poweroff", "reboot", "halt", "suspend", "hibernate"), ()),
    "shutdown": (("/s", "/r", "/f", "/sg", "-h", "-r", "-s",
                  "--halt", "--reboot", "--poweroff"), ()),
    "osascript": ((), ("shut down", "restart", "sleep", "log out")),
    "poweroff": ((), ()),          # takes no argument to be dangerous
    "reboot": ((), ()),
    "halt": ((), ()),
    "wmic": (("shutdown",), ()),
    "rundll32": ((), ("exitwindows",)),
}

_real_popen = subprocess.Popen
_real_system = os.system
_real_execv = os.execv
_real_execvp = os.execvp
_real_execve = os.execve


class RefusedPowerCommandError(AssertionError):
    """A test tried to power off, restart or halt the machine running it."""


def _program(path: str) -> str:
    """The command name, however it was spelled: a bare name, a path, or `X.exe`.

    Splits on both separators rather than using os.path.basename, which only knows the
    host's. A Windows command line checked on a POSIX box - which is what CI does - would
    otherwise arrive as one long unsplit string and match nothing.
    """
    name = str(path).replace("\\", "/").rsplit("/", 1)[-1].lower()
    return name[:-4] if name.endswith(".exe") else name


def _is_power_command(args) -> str | None:
    """The offending command line, or None. Case-insensitive; Windows flags are not."""
    if isinstance(args, (list, tuple)):
        parts = [str(a) for a in args]
    else:
        parts = str(args).split()
    if not parts:
        return None

    entry = _POWER_PROGRAMS.get(_program(parts[0]))
    if entry is None:
        return None
    flags, phrases = entry
    printable = " ".join(parts)
    if not flags and not phrases:
        return printable        # the program name alone is the whole command

    arguments = [part.lower() for part in parts[1:]]
    if any(flag.lower() in arguments for flag in flags):
        return printable
    line = " ".join(arguments)
    if any(phrase.lower() in line for phrase in phrases):
        return printable
    return None


def _refuse(printable: str, how: str) -> None:
    raise RefusedPowerCommandError(
        f"a test tried to {how} a real power command: {printable!r}. "
        "Patch common.host.system_actions and assert on the patch instead."
    )


def _guarded_popen(args, *rest, **kwargs):
    offending = _is_power_command(args)
    if offending:
        _refuse(offending, "run")
    return _real_popen(args, *rest, **kwargs)


def _guarded_system(command):
    """`os.system` takes a string and never reaches Popen, so it needs its own guard."""
    offending = _is_power_command(command)
    if offending:
        _refuse(offending, "run")
    return _real_system(command)


def _guarded_exec(real, name):
    """`restart_if_requested` re-execs the process, which spawns nothing.

    Not a power command, but just as destructive here: it would replace the test runner
    with a fresh VPinFE and the suite would simply stop, mid-run, looking like a crash.
    """
    def guard(path, args, *rest):
        _refuse(f"{path} {' '.join(map(str, args))}", f"{name}")
    return guard


subprocess.Popen = _guarded_popen
os.system = _guarded_system
os.execv = _guarded_exec(_real_execv, "exec")
os.execvp = _guarded_exec(_real_execvp, "exec")
os.execve = _guarded_exec(_real_execve, "exec")
