from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class Table:
    tableDirName: str | None = None
    fullPathTable: str | None = None
    fullPathVPXfile: str | None = None
    creation_time: float | None = None

    pupPackExists: bool = False
    altColorExists: bool = False
    altSoundExists: bool = False
    vniExists: bool = False
    b2sExists: bool = False
    romExists: bool = False

    BGImagePath: str | None = None
    DMDImagePath: str | None = None
    TableImagePath: str | None = None
    FSSImagePath: str | None = None
    WheelImagePath: str | None = None
    CabImagePath: str | None = None
    realDMDImagePath: str | None = None
    realDMDColorImagePath: str | None = None
    FlyerImagePath: str | None = None

    TableVideoPath: str | None = None
    BGVideoPath: str | None = None
    DMDVideoPath: str | None = None

    AudioPath: str | None = None

    metaConfig: dict[str, Any] | None = None

    # Read during the scan because the scan already listed the folder. Asking again later
    # costs a second walk of the library, which on a network share is the whole cost.
    #
    # Restorable means a saved copy this build can actually read, not merely a saved copy.
    # After a restore the folder still holds the ones it could not use, and counting those
    # would leave the offer on screen with nothing behind it.
    info_restorable: bool = False
    # Newest backup's timestamp, so the restore dialog can name the day it goes back to.
    info_backup_stamp: str = ""
