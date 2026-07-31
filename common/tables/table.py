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
    iniExists: bool = False
    musicExists: bool = False

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
    RuleCardImagePath: str | None = None
    TopperPath: str | None = None
    LoadingVideoPath: str | None = None
    AudioLaunchPath: str | None = None
    RuleSheetPath: str | None = None
    LogoImagePath: str | None = None

    metaConfig: dict[str, Any] | None = None

    # Read during the scan because the scan already has both: the .info was opened, and
    # the folder was listed. Asking again later costs a second walk of the library, which
    # on a network share is the whole cost.
    #
    # info_restorable means a backup this build can actually read, not merely a backup.
    # After a restore the folder still holds the copies it could not use, and counting
    # those would leave the offer on screen with nothing behind it.
    info_pending_convert: bool = False
    info_restorable: bool = False
