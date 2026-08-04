from __future__ import annotations

from dataclasses import dataclass, replace
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
    # The token for tiers 1 and 2 - "(Wheel) Name.png". Video kinds share their
    # image counterpart's token; the extension family tells them apart.
    token: str | None = None
    # Also accepted, tried after token. Where VPX's published name is opaque we
    # lead with the plain-English one and keep theirs readable.
    alt_tokens: tuple[str, ...] = ()
    family: tuple[str, ...] = IMAGE_FAMILY
    # Another kind whose resolved file serves when this kind has none - below
    # every tier of this kind, so any real file of its own outranks it.
    fallback_kind: str | None = None
    # Whether medias/<kind>s/<set>/ folders participate in resolution.
    supports_sets: bool = False

    def filename(self, playfield_variant: str = "table") -> str:
        return self.filename_template.format(playfield_variant=playfield_variant)

    def stem(self, playfield_variant: str = "table") -> str:
        return self.filename(playfield_variant).rsplit(".", 1)[0]


MEDIA_SPECS = (
    MediaSpec("bg", "BGImagePath", "bg.png", "1k", token="(Backglass)"),
    MediaSpec("dmd", "DMDImagePath", "dmd.png", "1k", token="(DMD)"),
    MediaSpec("table", "PlayfieldImagePath", "{playfield_variant}.png", "table_resolution",
              token="(Playfield)"),
    MediaSpec("fss", "FSSImagePath", "fss.png", token="(FSS)"),
    MediaSpec("wheel", "WheelImagePath", "wheel.png", token="(Wheel)",
              fallback_kind="logo", supports_sets=True),
    MediaSpec("cab", "CabImagePath", "cab.png", token="(Cabinet)"),
    MediaSpec("real_dmd", "realDMDImagePath", "realdmd.png", token="(RealDMD)"),
    MediaSpec("real_dmd_color", "realDMDColorImagePath", "realdmd-color.png",
              token="(RealColorDMD)"),
    MediaSpec("flyer", "FlyerImagePath", "flyer.png", token="(Flyer)",
              alt_tokens=("(GameInfo)",)),
    MediaSpec("table_video", "PlayfieldVideoPath", "{playfield_variant}.mp4",
              "table_video_resolution", token="(Playfield)", family=VIDEO_FAMILY),
    MediaSpec("bg_video", "BGVideoPath", "bg.mp4", "table_video_resolution",
              token="(Backglass)", family=VIDEO_FAMILY),
    MediaSpec("dmd_video", "DMDVideoPath", "dmd.mp4", "table_video_resolution",
              token="(DMD)", family=VIDEO_FAMILY),
    MediaSpec("audio", "AudioPath", "audio.mp3", token="(Audio)", family=AUDIO_FAMILY),
    # The 3.0 additions - spec tokens except rule_sheet, which the spec keeps
    # outside its media scheme and we bring in so it gets the chain.
    MediaSpec("instruction_card", "InstructionCardImagePath", "instructioncard.png",
              token="(InstructionCard)", alt_tokens=("(RuleCard)", "(GameHelp)")),
    MediaSpec("topper", "TopperPath", "topper.png", token="(Topper)"),
    MediaSpec("topper_video", "TopperVideoPath", "topper.mp4", token="(Topper)",
              family=VIDEO_FAMILY),
    MediaSpec("loading", "LoadingVideoPath", "loading.mp4", token="(Loading)",
              family=VIDEO_FAMILY),
    MediaSpec("audio_launch", "AudioLaunchPath", "audiolaunch.mp3",
              token="(AudioLaunch)", family=AUDIO_FAMILY),
    MediaSpec("rule_sheet", "RuleSheetPath", "rulesheet.pdf", token="(RuleSheet)",
              family=DOC_FAMILY),
    # The game's title art - usually the source a wheel is derived from, which
    # is why the wheel falls back to it.
    MediaSpec("logo", "LogoImagePath", "logo.png", token="(Logo)"),
)


def specs_for_playfield_variant(playfield_variant: str = "table") -> list[MediaSpec]:
    """The spec list with the playfield keys renamed for this playfield variant.

    Only the key changes: replace() copies the rest, so a spec from here still
    carries its token, extension family, fallback and set support. Rebuilding one
    field by field silently handed back defaults for everything not passed.
    """
    specs: list[MediaSpec] = []
    for spec in MEDIA_SPECS:
        key = playfield_variant if spec.key == "table" else f"{playfield_variant}_video" if spec.key == "table_video" else spec.key
        specs.append(replace(spec, key=key))
    return specs


def media_filename_map(playfield_variant: str = "table") -> dict[str, str]:
    return {spec.key: spec.filename(playfield_variant)
            for spec in specs_for_playfield_variant(playfield_variant)}


def media_attr_key_map(playfield_variant: str = "table") -> dict[str, str]:
    return {spec.attr: spec.key for spec in specs_for_playfield_variant(playfield_variant)}


def media_attr_map(playfield_variant: str = "table") -> dict[str, str]:
    return {spec.attr: spec.filename(playfield_variant)
            for spec in specs_for_playfield_variant(playfield_variant)}


def default_media_path(game_dir: str | Path, key: str, playfield_variant: str = "table") -> Path:
    filenames = media_filename_map(playfield_variant)
    if key not in filenames:
        raise KeyError(f"Unknown media key: {key}")
    return Path(game_dir) / "medias" / filenames[key]


# Theme-side set overrides. common/ cannot import frontend/, so the frontend
# pushes its active theme's choice down here at boot; the ini default applies
# otherwise. kind -> set name.
_set_overrides: dict[str, str] = {}


def set_media_set_override(kind: str, set_name: str | None) -> None:
    if set_name:
        _set_overrides[kind] = set_name
    else:
        _set_overrides.pop(kind, None)


def active_set_for(kind: str, configured: str = "") -> str | None:
    return _set_overrides.get(kind) or (configured.strip() or None)


def available_sets(kind: str, medias_tree: set[str]) -> list[str]:
    """Set names present under medias/<kind>s/, from a relative-path listing."""
    prefix = f"{kind}s/"
    names = {rel.split("/", 2)[1] for rel in medias_tree
             if rel.lower().startswith(prefix) and rel.count("/") >= 2}
    return sorted(names)


def list_media_sets(game_root: str | Path, kind: str = "wheel") -> list[str]:
    """Every set name across the library, plus the reserved virtual ones.

    "logo" is always offered for the wheel: it needs no wheels/ folder because
    it resolves from each table's logo media directly.
    """
    names: set[str] = set()
    root = Path(game_root)
    try:
        game_dirs = [d for d in root.iterdir() if d.is_dir()]
    except OSError:
        game_dirs = []
    for game_dir in game_dirs:
        sets_dir = game_dir / "medias" / f"{kind}s"
        try:
            names.update(d.name for d in sets_dir.iterdir() if d.is_dir())
        except OSError:
            continue
    if kind == "wheel":
        names.add("logo")
    return sorted(names, key=str.lower)


def resolve_media_files(game_dir: str | Path, game_contents: set[str],
                        medias_contents: set[str],
                        playfield_variant: str = "table",
                        table_stem: str | None = None,
                        active_sets: dict[str, str] | None = None) -> dict[str, Path | None]:
    """Canonical media key -> the file that serves it, or None.

    Three tiers, most specific wins, per kind:

      1. "(Token) <table-stem>.<ext>"      - this table's own media
      2. "(Token) <folder-name>.<ext>"     - shared by every table in the folder
      3. "wheel.png"-style fixed names     - what vpinmediadb writes

    Within a tier the kind's extension family is tried in order, first hit wins -
    so a hand-placed wheel.jpg finally resolves instead of being invisible.
    Matching is case-insensitive, like every other companion lookup. The medias/
    folder is canonical and the folder root is the fallback at every tier, which
    keeps tier 3 exactly as it always behaved.

    Keyed by MEDIA_SPECS keys, stable across variants - under playfield_variant "fss"
    the playfield's *filename* changes but its key stays "table".

    `medias_contents` may carry relative paths (wheels/tarcisio/wheel.png) for
    set folders. For a set-supporting kind with an active set, the order is:
    the user's own spec-named files, then the set's files (its own full chain),
    then the plain fixed default - so activating a set never clobbers a
    hand-made per-version file, and a media refresh never beats the set. The
    reserved set name "logo" prefers the logo kind in that middle slot.
    """
    game_dir = Path(game_dir)
    medias_dir = game_dir / "medias"
    in_medias = {name.lower(): name for name in medias_contents}
    in_root = {name.lower(): name for name in game_contents}
    folder_name = game_dir.name

    def find(name: str) -> Path | None:
        hit = in_medias.get(name.lower())
        if hit is not None:
            return medias_dir / hit
        hit = in_root.get(name.lower())
        if hit is not None:
            return game_dir / hit
        return None

    resolved: dict[str, Path | None] = {}
    virtual_pending: dict[str, Path | None] = {}
    for spec in MEDIA_SPECS:
        # Tier outranks token preference: a table-specific alias still beats a
        # folder-level preferred token, or "most specific wins" would not hold.
        tokens = ((spec.token,) + spec.alt_tokens) if spec.token else ()
        user_names: list[str] = []
        if table_stem:
            user_names += [f"{token} {table_stem}{ext}"
                           for token in tokens for ext in spec.family]
        user_names += [f"{token} {folder_name}{ext}"
                       for token in tokens for ext in spec.family]
        fixed_stem = spec.stem(playfield_variant)
        fixed_names = [f"{fixed_stem}{ext}" for ext in spec.family]

        active = (active_sets or {}).get(spec.key) if spec.supports_sets else None
        set_names: list[str] = []
        if active and active != "logo":
            set_names = [f"{spec.key}s/{active}/{name}"
                         for name in user_names + fixed_names]

        first = lambda names: next(  # noqa: E731
            (path for name in names if (path := find(name)) is not None), None)

        if active == "logo":
            # The reserved virtual set: prefer the logo kind between the user's
            # own files and the plain default. Logo resolves later in the spec
            # order, so finish this kind in the post-pass.
            resolved[spec.key] = first(user_names)
            virtual_pending[spec.key] = first(fixed_names)
        else:
            resolved[spec.key] = first(user_names) or first(set_names) or first(fixed_names)

    for key, fixed_hit in virtual_pending.items():
        if resolved[key] is None:
            resolved[key] = resolved.get("logo") or fixed_hit

    # Cross-kind fallbacks, after everything: a kind with no file of its own at
    # any tier borrows its fallback kind's winner.
    for spec in MEDIA_SPECS:
        if spec.fallback_kind and resolved[spec.key] is None:
            resolved[spec.key] = resolved.get(spec.fallback_kind)
    return resolved


def apply_media_paths(game, game_contents: set[str], medias_contents: set[str],
                      playfield_variant: str = "table",
                      table_stem: str | None = None,
                      active_sets: dict[str, str] | None = None) -> None:
    resolved = resolve_media_files(game.fullPathGame, game_contents,
                                   medias_contents, playfield_variant, table_stem,
                                   active_sets)
    for spec in MEDIA_SPECS:
        path = resolved[spec.key]
        if path is not None:
            setattr(game, spec.attr, str(path))


def game_media_payload(game) -> dict[str, str | None]:
    return {
        spec.attr: getattr(game, spec.attr, None)
        for spec in MEDIA_SPECS
    }
