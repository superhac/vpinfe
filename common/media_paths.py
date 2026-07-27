from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

# Extension families, ordered: resolution tries them in order and the first hit
# wins. Aligned with what import accepts, so a file import writes is never
# invisible to the scan - which it was, when resolution demanded one exact name.
IMAGE_FAMILY = (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif")
VIDEO_FAMILY = (".mp4",)
AUDIO_FAMILY = (".mp3", ".ogg")
DOC_FAMILY = (".pdf", ".md", ".txt", ".html")


@dataclass(frozen=True)
class MediaSpec:
    key: str
    attr: str
    filename_template: str
    asset_group: str | None = None
    # The spec token for tiers 1 and 2 - "(Wheel) Name.png". Video kinds share
    # their image counterpart's token; the extension family tells them apart.
    token: str | None = None
    family: tuple[str, ...] = IMAGE_FAMILY

    def filename(self, table_type: str = "table") -> str:
        return self.filename_template.format(tabletype=table_type)

    def stem(self, table_type: str = "table") -> str:
        return self.filename(table_type).rsplit(".", 1)[0]


MEDIA_SPECS = (
    MediaSpec("bg", "BGImagePath", "bg.png", "1k", token="(Backglass)"),
    MediaSpec("dmd", "DMDImagePath", "dmd.png", "1k", token="(DMD)"),
    MediaSpec("table", "TableImagePath", "{tabletype}.png", "table_resolution",
              token="(Playfield)"),
    MediaSpec("fss", "FSSImagePath", "fss.png", token="(FSS)"),
    MediaSpec("wheel", "WheelImagePath", "wheel.png", token="(Wheel)"),
    MediaSpec("cab", "CabImagePath", "cab.png", token="(Cabinet)"),
    MediaSpec("realdmd", "realDMDImagePath", "realdmd.png", token="(RealDMD)"),
    MediaSpec("realdmd_color", "realDMDColorImagePath", "realdmd-color.png",
              token="(RealColorDMD)"),
    MediaSpec("flyer", "FlyerImagePath", "flyer.png", token="(GameInfo)"),
    MediaSpec("table_video", "TableVideoPath", "{tabletype}.mp4", "table_video_resolution",
              token="(Playfield)", family=VIDEO_FAMILY),
    MediaSpec("bg_video", "BGVideoPath", "bg.mp4", "table_video_resolution",
              token="(Backglass)", family=VIDEO_FAMILY),
    MediaSpec("dmd_video", "DMDVideoPath", "dmd.mp4", "table_video_resolution",
              token="(DMD)", family=VIDEO_FAMILY),
    MediaSpec("audio", "AudioPath", "audio.mp3", token="(Audio)", family=AUDIO_FAMILY),
    # The 3.0 additions - spec tokens except rulesheet, which the spec keeps
    # outside its media scheme and we bring in so it gets the chain.
    MediaSpec("rulecard", "RuleCardImagePath", "rulecard.png", token="(GameHelp)"),
    MediaSpec("topper", "TopperPath", "topper.png", token="(Topper)",
              family=(".png", ".jpg", ".mp4")),
    MediaSpec("loading", "LoadingVideoPath", "loading.mp4", token="(Loading)",
              family=VIDEO_FAMILY),
    MediaSpec("audiolaunch", "AudioLaunchPath", "audiolaunch.mp3",
              token="(AudioLaunch)", family=AUDIO_FAMILY),
    MediaSpec("rulesheet", "RuleSheetPath", "rulesheet.pdf", token="(RuleSheet)",
              family=DOC_FAMILY),
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


def resolve_media_files(table_dir: str | Path, table_contents: set[str],
                        medias_contents: set[str],
                        table_type: str = "table",
                        game_file_stem: str | None = None) -> dict[str, Path | None]:
    """Canonical media key -> the file that serves it, or None.

    Three tiers, most specific wins, per kind:

      1. "(Token) <game-file-stem>.<ext>"  - this build's own media
      2. "(Token) <folder-name>.<ext>"     - shared by every build in the folder
      3. "wheel.png"-style fixed names     - what vpinmediadb writes

    Within a tier the kind's extension family is tried in order, first hit wins -
    so a hand-placed wheel.jpg finally resolves instead of being invisible.
    Matching is case-insensitive, like every other companion lookup. The medias/
    folder is canonical and the folder root is the fallback at every tier, which
    keeps tier 3 exactly as it always behaved.

    Keyed by MEDIA_SPECS keys, stable across table types - under table_type "fss"
    the playfield's *filename* changes but its key stays "table".
    """
    table_dir = Path(table_dir)
    medias_dir = table_dir / "medias"
    in_medias = {name.lower(): name for name in medias_contents}
    in_root = {name.lower(): name for name in table_contents}
    folder_name = table_dir.name

    def find(name: str) -> Path | None:
        hit = in_medias.get(name.lower())
        if hit is not None:
            return medias_dir / hit
        hit = in_root.get(name.lower())
        if hit is not None:
            return table_dir / hit
        return None

    resolved: dict[str, Path | None] = {}
    for spec in MEDIA_SPECS:
        candidates: list[str] = []
        if spec.token:
            if game_file_stem:
                candidates += [f"{spec.token} {game_file_stem}{ext}" for ext in spec.family]
            candidates += [f"{spec.token} {folder_name}{ext}" for ext in spec.family]
        fixed_stem = spec.stem(table_type)
        candidates += [f"{fixed_stem}{ext}" for ext in spec.family]

        resolved[spec.key] = next(
            (path for name in candidates if (path := find(name)) is not None), None)
    return resolved


def apply_media_paths(table, table_contents: set[str], medias_contents: set[str],
                      table_type: str = "table",
                      game_file_stem: str | None = None) -> None:
    resolved = resolve_media_files(table.fullPathTable, table_contents,
                                   medias_contents, table_type, game_file_stem)
    for spec in MEDIA_SPECS:
        path = resolved[spec.key]
        if path is not None:
            setattr(table, spec.attr, str(path))


def table_media_payload(table) -> dict[str, str | None]:
    return {
        spec.attr: getattr(table, spec.attr, None)
        for spec in MEDIA_SPECS
    }
