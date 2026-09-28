"""Visual Pinball launched to have its screens recorded.

What a recording changes goes into copies in the folder core hands over, never into a file
Visual Pinball keeps: it writes its settings back when it exits.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from common.apps.contract import Entry

from . import ini as vini
from .config import read_at_table, read_file, settings_file, table_layer
from .launch import VPXLaunch

# In the program's own values: SyncMode 0 is No Sync, MaxFramerate -1 follows the display.
PACING = {"Player.SyncMode": "0", "Player.MaxFramerate": "-1"}
MUTED = {"Player.PlaySound": "0", "Player.PlayMusic": "0",
         "Player.SoundVolume": "0", "Player.MusicVolume": "0"}

SETTINGS_COPY = "VPinballX.ini"
TABLE_COPY = "table.ini"

# Each window's display, and its Output Mode where it has one: the playfield always shows.
DISPLAYS = {"playfield": ("Player.PlayfieldDisplay", ""),
            "backglass": ("Backglass.BackglassDisplay", "Backglass.BackglassOutput"),
            "scoreview": ("ScoreView.ScoreViewDisplay", "ScoreView.ScoreViewOutput"),
            "topper": ("Topper.TopperDisplay", "Topper.TopperOutput")}
# Output Mode 1, a window of its own. Unset and 0 are Disabled; 2 is inside the playfield.
FLOATING = "1"
TITLES = {"Visual Pinball Player": "playfield", "Visual Pinball Backglass": "backglass",
          "Visual Pinball Score View": "scoreview", "Visual Pinball Topper": "topper"}

# `Samsung Electric Company SAMSUNG 0x00000001 (DP-1 via HDMI)`.
_CONNECTOR = re.compile(r"\(\s*([^\s()]+)[^()]*\)\s*$")

_LAUNCH = VPXLaunch()


def recording_values(sound: bool) -> dict[str, str]:
    return dict(PACING) if sound else {**PACING, **MUTED}


def connector(display: str) -> str:
    """The output a display name names in the parentheses it ends with, or ""."""
    found = _CONNECTOR.search(str(display or ""))
    return found.group(1) if found else ""


class VPXCapture:
    def command(self, entry: Entry, settings: Mapping[str, Any], *, sound: bool,
                folder: str) -> list[str]:
        """The launch command with `-ini` naming a copy of the Settings File, and
        `-tableini` a copy of the table's own file where that sets one of the recording's
        values, since the table's would win over the Settings File's."""
        values = recording_values(sound)
        copy = Path(folder) / SETTINGS_COPY
        copy.write_text(vini.written(read_file(settings_file(settings)), values),
                        encoding="utf-8")
        cmd = _LAUNCH.command(entry, {**settings, "ini_path": str(copy)})

        table = read_file(table_layer(entry.table))
        if any(table.value(key) is not None for key in values):
            table_copy = Path(folder) / TABLE_COPY
            table_copy.write_text(vini.written(table, values), encoding="utf-8")
            cmd[-2:-2] = ["-tableini", str(table_copy)]
        return cmd

    def outputs(self, entry: Entry, settings: Mapping[str, Any]) -> dict[str, str]:
        app = read_file(settings_file(settings))
        table = read_file(table_layer(entry.table))

        def value(key: str) -> str:
            said = table.value(key) if read_at_table(key) else None
            return (app.value(key) or "" if said is None else said).strip()

        found: dict[str, str] = {}
        for window, (display, mode) in DISPLAYS.items():
            if mode and value(mode) != FLOATING:
                found[window] = ""
            elif name := connector(value(display)):
                found[window] = name
        return found

    def window(self, app_id: str, title: str) -> str:
        return TITLES.get(str(title or "").strip(), "")
