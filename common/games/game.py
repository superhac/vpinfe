from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class Game:
    gameDirName: str | None = None
    fullPathGame: str | None = None
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
    PlayfieldImagePath: str | None = None
    FSSImagePath: str | None = None
    WheelImagePath: str | None = None
    CabImagePath: str | None = None
    realDMDImagePath: str | None = None
    realDMDColorImagePath: str | None = None
    FlyerImagePath: str | None = None

    PlayfieldVideoPath: str | None = None
    BGVideoPath: str | None = None
    DMDVideoPath: str | None = None

    AudioPath: str | None = None
    InstructionCardImagePath: str | None = None
    TopperPath: str | None = None
    LoadingVideoPath: str | None = None
    AudioLaunchPath: str | None = None
    RuleSheetPath: str | None = None
    LogoImagePath: str | None = None

    metaConfig: dict[str, Any] | None = None

    # Read during the scan, which already has both. info_restorable means a backup this
    # build can read, not merely a backup - after a restore the unusable copies remain.
    info_pending_upgrade: bool = False
    info_restorable: bool = False
    # Newest backup's timestamp: "before the upgrade" means nothing weeks later.
    info_backup_stamp: str = ""
