"""Building Visual Pinball's command line, and how one of its sessions is watched."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from common.apps.contract import (
    SESSION_CHILD_WITH_READINESS,
    Entry,
    Session,
)

logger = logging.getLogger("vpinfe.apps.vpx.launch")

# VPX writes this once the table is actually up. Before it, the process exists but the
# player is looking at nothing.
STARTUP_MARKER = "Startup done"


def _to_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in ("1", "true", "yes", "on")


def masked_tableini_path(table: str, enabled: Any, mask: str) -> str:
    """`{stem}.{mask}.ini` beside the table, for the per-table override pattern.

    A degenerate token system: it exists only because there was no general way to say
    "a file named after the table". VPX finds `<table>.ini` and `<folder>.ini` unaided,
    so this covers a non-standard name and nothing else.
    """
    if not _to_bool(enabled):
        return ""

    pattern = str(mask or "").strip()
    if not pattern:
        logger.warning("Per-table override is on but the pattern is empty; no -tableini")
        return ""

    table_file = Path(str(table or "").strip())
    if not table_file.name:
        return ""
    return str(table_file.with_name(f"{table_file.stem}.{pattern}.ini"))


def resolve_tableini_override(table: str, enabled: Any, mask: str) -> str:
    """The masked ini, but only if it is actually there."""
    masked = masked_tableini_path(table, enabled, mask)
    if not masked:
        return ""
    if not Path(masked).is_file():
        logger.info("Masked tableini does not exist; skipping -tableini: %s", masked)
        return ""
    return masked


class VPXLaunch:
    """`settings` is the launcher's, with `bin_path` already resolved to the executable -
    on macOS what a person picks is a `.app` directory, and VPX is inside it."""

    def command(self, entry: Entry, settings: Mapping[str, Any]) -> list[str]:
        """`-play <table>` is guaranteed last, and there is only ever one `-ini`.

        VPX accepts a single `-ini` and silently drops a second, which would make us the
        one who lost the setting without saying so.
        """
        cmd = [str(settings.get("bin_path") or "")]

        ini_override = str(settings.get("ini_override") or "").strip()
        if ini_override:
            cmd.extend(["-ini", ini_override])

        table_ini = resolve_tableini_override(
            entry.table,
            settings.get("table_ini_override_enabled"),
            str(settings.get("table_ini_override_mask") or ""),
        )
        if table_ini:
            cmd.extend(["-tableini", table_ini])

        cmd.extend(["-play", str(entry.table)])
        return cmd

    def session(self, settings: Mapping[str, Any]) -> Session:
        return Session(kind=SESSION_CHILD_WITH_READINESS,
                       readiness_marker=STARTUP_MARKER)
