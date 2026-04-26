from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class MediaSpec:
    key: str
    attr: str
    filename_template: str
    asset_group: str | None = None

    def filename(self, table_type: str = "table") -> str:
        return self.filename_template.format(tabletype=table_type)


MEDIA_SPECS = (
    MediaSpec("bg", "BGImagePath", "bg.png", "1k"),
    MediaSpec("dmd", "DMDImagePath", "dmd.png", "1k"),
    MediaSpec("table", "TableImagePath", "{tabletype}.png", "table_resolution"),
    MediaSpec("fss", "FSSImagePath", "fss.png"),
    MediaSpec("wheel", "WheelImagePath", "wheel.png"),
    MediaSpec("cab", "CabImagePath", "cab.png"),
    MediaSpec("realdmd", "realDMDImagePath", "realdmd.png"),
    MediaSpec("realdmd_color", "realDMDColorImagePath", "realdmd-color.png"),
    MediaSpec("flyer", "FlyerImagePath", "flyer.png"),
    MediaSpec("table_video", "TableVideoPath", "{tabletype}.mp4", "table_video_resolution"),
    MediaSpec("bg_video", "BGVideoPath", "bg.mp4", "table_video_resolution"),
    MediaSpec("dmd_video", "DMDVideoPath", "dmd.mp4", "table_video_resolution"),
    MediaSpec("audio", "AudioPath", "audio.mp3"),
)


def specs_for_table_type(table_type: str = "table") -> list[MediaSpec]:
    specs: list[MediaSpec] = []
    for spec in MEDIA_SPECS:
        key = table_type if spec.key == "table" else f"{table_type}_video" if spec.key == "table_video" else spec.key
        specs.append(MediaSpec(key, spec.attr, spec.filename_template, spec.asset_group))
    return specs


def media_filename_map(table_type: str = "table") -> dict[str, str]:
    return {spec.key: spec.filename(table_type) for spec in specs_for_table_type(table_type)}


def media_attr_key_map(table_type: str = "table") -> dict[str, str]:
    return {spec.attr: spec.key for spec in specs_for_table_type(table_type)}


def media_attr_map(table_type: str = "table") -> dict[str, str]:
    return {spec.attr: spec.filename(table_type) for spec in specs_for_table_type(table_type)}


def default_media_path(table_dir: str | Path, key: str, table_type: str = "table") -> Path:
    filenames = media_filename_map(table_type)
    if key not in filenames:
        raise KeyError(f"Unknown media key: {key}")
    return Path(table_dir) / "medias" / filenames[key]


def apply_media_paths(table, table_contents: set[str], medias_contents: set[str], table_type: str = "table") -> None:
    table_dir = Path(table.fullPathTable)
    medias_dir = table_dir / "medias"
    for attr, filename in media_attr_map(table_type).items():
        if filename in medias_contents:
            setattr(table, attr, str(medias_dir / filename))
        elif filename in table_contents:
            setattr(table, attr, str(table_dir / filename))


def table_media_payload(table) -> dict[str, str | None]:
    return {
        spec.attr: getattr(table, spec.attr, None)
        for spec in MEDIA_SPECS
    }
