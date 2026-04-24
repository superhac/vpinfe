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
