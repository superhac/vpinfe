"""One game folder, as the rest of the app sees it.

The attribute names are camelCase because a contract 1 theme reads them straight off
the payload. They are frozen by the parity gate, not by preference.
"""

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

    # Every .vpx the scan found in the folder. Recorded because discovery reconciles it
    # against what the .info describes, and the listing is already in hand here - asking
    # the disk a second time would be the expensive half of that job for nothing.
    table_files: list[str] | None = None

    # The same resolution, run once per .vpx in the folder: {filename: {kind: path}}.
    # The attributes above answer for the default table only, which is all a contract 1
    # theme can ask about; this is what lets /media/<table id>/<kind> answer for the
    # table it was actually addressed with. Keyed by filename because ids are backfilled
    # after the scan.
    media_by_table: dict[str, dict[str, str]] | None = None

    meta_config: dict[str, Any] | None = None

    # Read during the scan, which already has both. info_restorable means a backup this
    # build can read, not merely a backup - after a restore the unusable copies remain.
    info_pending_upgrade: bool = False
    info_restorable: bool = False
    # Newest backup's timestamp: "before the upgrade" means nothing weeks later.
    info_backup_stamp: str = ""
