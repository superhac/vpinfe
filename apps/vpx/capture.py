"""Visual Pinball launched to have its screens recorded.

What a recording changes goes into copies in the folder core hands over, never into a file
Visual Pinball keeps: it writes its settings back when it exits.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from common.apps.contract import Entry

from . import ini as vini
from .config import read_file, settings_file, table_layer
from .launch import VPXLaunch

# In the program's own values: SyncMode 0 is No Sync, MaxFramerate -1 follows the display.
PACING = {"Player.SyncMode": "0", "Player.MaxFramerate": "-1"}
MUTED = {"Player.PlaySound": "0", "Player.PlayMusic": "0",
         "Player.SoundVolume": "0", "Player.MusicVolume": "0"}

SETTINGS_COPY = "VPinballX.ini"
TABLE_COPY = "table.ini"

_LAUNCH = VPXLaunch()


def recording_values(sound: bool) -> dict[str, str]:
    return dict(PACING) if sound else {**PACING, **MUTED}


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
