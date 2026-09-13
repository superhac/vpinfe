"""The commands that run around a table, and what they are told about it.

Two sets, nested: the install's run outside the launcher's. That is execution order and
not evidence they are one thing - the install's are about the machine, and run whichever
launcher plays the table; the launcher's are about one way of playing.

**If VPinFE stops between the two halves, the second never runs.** So the fact that the
first ran is written down, and the next start finishes what it began before doing
anything else. That turns a machine left muted, or with a service stopped, from something
somebody has to work out into something that fixes itself.
"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path

from common import tokens
from common.atomic_write import write_atomic
from common.config_access import cfg_bool, cfg_get, cfg_int
from common.extensions import services as ext_services
from common.games import tables
from common.host import commands
from common.paths import CONFIG_DIR

logger = logging.getLogger("vpinfe.common.host.table_commands")

# What ran and has not been finished. One file: a machine plays one table at a time.
PENDING_PATH = CONFIG_DIR / "unfinished_commands.json"


@dataclass
class Around:
    """One table's two halves, and what the second of them will be told."""

    values: dict[str, str] = field(default_factory=dict)
    timeout: int = commands.DEFAULT_TIMEOUT
    install_after: str = ""
    launcher_after: str = ""
    ran: bool = False


def player_name() -> str:
    """Who this is being recorded against, in the form a person would recognize.

    Initials, because that is what a cabinet asks for and what shows on a score.
    """
    profile = ext_services.ask("guest.active")
    if profile is None:
        return ""
    return str(getattr(profile, "initials", "") or getattr(profile, "user_id", "") or "")


def _values(game, playing, launcher) -> dict[str, str]:
    """What a command about this table may say. Strings, all of them, because they are
    going into an argument list.

    Every name the context offers resolves to something, empty included: a command
    mentioning one that happens not to apply to this entry should run with a blank, not
    fail. An entry with no file has no `{table}`, and that is normal.
    """
    entries = tables.table_entries(getattr(game, "meta_config", {}))
    entry = entries.get(playing.entry_id) or {}
    settings = ({one.key: launcher.value(one.key) for one in launcher.fields()}
                if launcher is not None else {})
    return {
        "game_dir": str(playing.game_dir or ""),
        "table": str(playing.table or ""),
        "table_stem": Path(playing.table).stem if playing.table else "",
        "game_name": str(getattr(game, "gameDirName", "") or ""),
        "id": str(playing.entry_id or ""),
        # The app's own name for the entry. Something in the folder has none.
        "key": str(playing.key or ""),
        "rom": str(entry.get("rom") or ""),
        "launcher_bin": str(settings.get("bin_path") or ""),
        "launcher_ini": str(settings.get("ini_path") or ""),
        "location": str(getattr(game, "location_id", "") or ""),
        "player": player_name(),
    }


def before(game, playing, launcher, ini_config) -> Around:
    """The install's commands and then this launcher's, in that order.

    A failure stops the launch only where somebody said it should. What that means is a
    share that has to be mounted against an audio route that would be nice to switch,
    and only they know which they wrote.
    """
    around = Around(values=_values(game, playing, launcher))
    around.timeout = cfg_int(ini_config, "general", "command_timeout",
                             commands.DEFAULT_TIMEOUT)
    around.install_after = cfg_get(ini_config, "general", "on_table_exit", "")
    settings = ({one.key: launcher.value(one.key) for one in launcher.fields()}
                if launcher is not None else {})
    around.launcher_after = str(settings.get("on_table_exit") or "")

    _run(cfg_get(ini_config, "general", "on_table_start", ""), around,
         required=cfg_bool(ini_config, "general", "table_start_required", False),
         whose="this install")
    _run(str(settings.get("on_table_start") or ""), around,
         required=_as_bool(settings.get("on_start_required")),
         whose=f"the {getattr(launcher, 'display_name', 'launcher')} launcher")

    if around.ran:
        _remember(around)
    return around


def after(around: Around, *, started_at: float | None = None) -> None:
    """The other half, whenever the first ran. The launcher's first, then the install's:
    it nests, so what was put on last comes off first."""
    if not around.ran:
        return
    values = dict(around.values)
    values["duration"] = str(int(time.time() - started_at)) if started_at else "0"
    values.setdefault("exit_code", "")
    for text in (around.launcher_after, around.install_after):
        if not str(text or "").strip():
            continue
        commands.run(text, values, context=tokens.TABLE, after=True,
                     timeout=around.timeout, on_failure=commands.BEST_EFFORT,
                     env=os.environ.copy())
    _forget()


def _run(text: str, around: Around, *, required: bool, whose: str) -> None:
    if not str(text or "").strip():
        return
    try:
        outcome = commands.run(
            text, around.values, context=tokens.TABLE, timeout=around.timeout,
            on_failure=commands.REQUIRED if required else commands.BEST_EFFORT,
            env=os.environ.copy())
    except commands.CommandRefusedError as exc:
        # Whatever did run still has to be undone, so this counts as having run.
        around.ran = True
        _remember(around)
        raise commands.CommandRefusedError(
            f"A command {whose} runs before a table did not work, and was set to stop "
            f"the launch if it did not: {exc}") from exc
    around.ran = around.ran or outcome.ran


def _as_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in ("1", "true", "yes", "on")


def _remember(around: Around) -> None:
    """Write down that the first half ran, so a VPinFE that dies here is a restart
    rather than a machine somebody has to put back by hand."""
    try:
        PENDING_PATH.parent.mkdir(parents=True, exist_ok=True)
        write_atomic(PENDING_PATH, lambda handle: json.dump({
            "values": around.values, "timeout": around.timeout,
            "install_after": around.install_after,
            "launcher_after": around.launcher_after,
        }, handle, indent=2))
    except Exception:  # noqa: BLE001 - never the thing that stops a launch
        logger.exception("Could not note that the pre-table commands ran")


def _forget() -> None:
    try:
        PENDING_PATH.unlink(missing_ok=True)
    except OSError:
        logger.exception("Could not clear the note")


def finish_unfinished() -> bool:
    """Run the half that never ran, before anything else on the next start.

    A machine left muted, or with a service stopped, is otherwise something somebody has
    to work out. Returns whether there was anything to finish.
    """
    try:
        payload = json.loads(PENDING_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return False
    except Exception:  # noqa: BLE001
        logger.exception("Could not read what was left unfinished; clearing it")
        _forget()
        return False

    logger.info("Finishing the commands a previous run left")
    after(Around(values=dict(payload.get("values") or {}),
                 timeout=int(payload.get("timeout") or commands.DEFAULT_TIMEOUT),
                 install_after=str(payload.get("install_after") or ""),
                 launcher_after=str(payload.get("launcher_after") or ""),
                 ran=True))
    return True
