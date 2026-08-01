"""The wire contract for /api/v1.

Every response body and every JSON request body is declared here, in one place, so
the contract is a thing you can read and import rather than something you infer by
reading handlers. FastAPI publishes these in the OpenAPI document, which is what
makes `GET /api/v1/openapi.json` worth generating a client from.

These describe the wire, not the domain. The domain shapes live under common/; a
model here is the projection of one onto the other, and the two are allowed to
differ - that is the point of having a boundary.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class ApiModel(BaseModel):
    """Base for every wire model.

    populate_by_name lets a field carry an alias for names Python will not take -
    `self` in a links object being the one that forces it. FastAPI serialises by
    alias, so the alias is what a client sees.
    """

    model_config = ConfigDict(populate_by_name=True)


# --- Instance --------------------------------------------------------------

class CapabilityInfo(ApiModel):
    """One capability as discovery reports it. `reason` is set only when unavailable.

    Residency is a list: naming both roles means each serves its own copy, not that
    one capability spans the two.
    """

    name: str
    residency: list[str]
    description: str
    available: bool
    reason: str | None


class DiscoveryLinks(ApiModel):
    """Relative so they survive a reverse proxy. A known link this instance does not
    offer is present and null, rather than absent."""

    self_: str = Field(alias="self")
    health: str
    openapi: str
    docs: str
    collections: str | None
    events: str | None
    jobs: str | None
    manufacturers: str | None


class Discovery(ApiModel):
    name: str
    api_version: str
    app_version: str
    capabilities: list[CapabilityInfo]
    extensions: list[dict]
    links: DiscoveryLinks


class Health(ApiModel):
    status: str


# --- Play ------------------------------------------------------------------

class PlayState(ApiModel):
    """Also the payload of the `play.state_changed` event, so a subscriber and a
    poller see the same shape. `source` is who asked - the frontend filters its
    own launches on it, so dropping the field breaks the remote overlay."""

    launching: bool
    table_name: str | None
    source: str | None


# --- Tables ----------------------------------------------------------------

class AssetFileBinding(ApiModel):
    """One asset file, attributed: dedicated to a game file, shared (folder-named),
    or orphaned - stem-named for a build that is no longer there."""

    file: str
    binding: str
    game_file: str | None = None


class AssetEntry(ApiModel):
    """One asset kind on a table. The list endpoint carries presence only; the
    detail endpoint adds the attributed files; alt_color carries its formats."""

    present: bool
    formats: list[str] | None = None
    files: list[AssetFileBinding] | None = None


class GameLinks(ApiModel):
    self_: str = Field(alias="self")
    game_files: str
    media: str
    archive: str
    launch: str


class GameResource(ApiModel):
    """A table: the pinball-machine concept, not a launchable file. vps_id correlates
    with VPSdb and anything keyed by it; `id` is what identifies the table here."""

    id: str
    vps_id: str
    name: str
    manufacturer: str
    year: str
    type: str
    themes: list[str]
    authors: list[str]
    rom: str
    version: str
    rating: int
    collections: list[str]
    assets: dict[str, AssetEntry]
    links: GameLinks


class GameList(ApiModel):
    """`total` counts what matched before limit and offset were applied."""

    total: int
    offset: int
    count: int
    tables: list[GameResource]


class ResolvedAsset(ApiModel):
    """What this game file would use for one kind: dedicated, shared, or none,
    plus the winning file."""

    resolution: str
    file: str | None = None


class NvramState(ApiModel):
    """Play state keyed by the effective rom, stat-ed per request so modified_at
    is live."""

    present: bool
    file: str | None = None
    modified_at: int | None = None


class PinmameChain(ApiModel):
    """declared -> alias -> effective -> required -> catalog/audit -> installed.
    Every unknown is null-with-reason, never a guess."""

    declared: str | None
    alias_of: str | None
    effective: str | None
    required: bool | None
    catalog: bool | None
    clone_of: str | None
    description: str | None = None
    audit: str | None
    installed: bool | None
    reason: str | None
    nvram: NvramState


class FlexDmdState(ApiModel):
    detected: bool | None
    declared: str | None
    installed: bool
    content: list[str]


class Dependencies(ApiModel):
    """Script-declared, content-satisfied - a different mechanism from an asset
    found by naming rule."""

    pinmame: PinmameChain
    flexdmd: FlexDmdState


class GameFile(ApiModel):
    """A launchable artifact.

    `available` is false for a file the metadata records but which is not on disk -
    worth reporting rather than hiding.

    `hidden` is the user's choice not to be offered this build in the frontend; the
    file stays on disk, because a patch base has to (the patched table cannot be
    rebuilt without it) and a variant may be wanted back. Consumers listing what to
    play should skip these; consumers managing a library should not.

    `default` names the file the table's metadata was derived from, not the one to
    launch - every visible game file is independently launchable.
    """

    format: str
    app: str
    filename: str
    default: bool
    hidden: bool
    available: bool
    assets: dict[str, ResolvedAsset]
    dependencies: Dependencies


class GameFileList(ApiModel):
    game_files: list[GameFile]


# --- Media -----------------------------------------------------------------

class MediaEntryLinks(ApiModel):
    self_: str | None = Field(alias="self")


class MediaEntry(ApiModel):
    """Every kind is listed, present or not, so a client enumerates what is
    possible instead of guessing from omissions. `via` names the kind whose file
    is standing in - a wheel served by the logo fallback says so."""

    present: bool
    file: str | None
    via: str | None = None
    links: MediaEntryLinks


class MediaList(ApiModel):
    media: dict[str, MediaEntry]


# --- Collections -----------------------------------------------------------

class CollectionFilters(ApiModel):
    """A filter collection's criteria. "All" means unconstrained on that axis -
    the vocabulary the filter engine already uses, kept rather than translated so
    a client sees the same values the Manager UI shows."""

    letter: str = "All"
    theme: str = "All"
    table_type: str = "All"
    manufacturer: str = "All"
    year: str = "All"
    rating: str = "All"
    rating_or_higher: bool = False
    sort_by: str = "Alpha"
    order_by: str = "Descending"


class CollectionLinks(ApiModel):
    self_: str = Field(alias="self")
    tables: str


class CollectionResource(ApiModel):
    """`type` is `manual` (an explicit list of tables) or `filter` (criteria applied
    at display time). `table_count` is null for a filter collection, whose membership
    is not a stored list - ask /tables for its current members. `filters` is set only
    for a filter collection."""

    name: str
    type: str
    image: str | None
    table_count: int | None
    filters: CollectionFilters | None
    links: CollectionLinks


class CollectionList(ApiModel):
    collections: list[CollectionResource]


class CreateCollectionRequest(ApiModel):
    """Supplying `filters` makes a filter collection; supplying `tables` (or neither)
    makes a manual one. Sending both is refused rather than guessed at."""

    name: str
    filters: CollectionFilters | None = None
    tables: list[str] = Field(default_factory=list)


# --- Jobs ------------------------------------------------------------------

class JobLinks(ApiModel):
    self_: str = Field(alias="self")
    events: str


class JobResource(ApiModel):
    """One run of slow work. `pct` and `message` are the last progress reported, so
    a client that connects late is correct without having seen the events. `error`
    is set only when state is `failed`; timestamps are epoch seconds."""

    id: str
    kind: str
    state: str
    pct: int
    message: str
    error: str | None
    started_at: float
    finished_at: float | None
    links: JobLinks


class JobList(ApiModel):
    jobs: list[JobResource]


class ScanRequest(ApiModel):
    """Absent body means both default to true, which is what the Manager UI's own
    scan does."""

    download_media: bool = True
    update_all: bool = True


# --- Manufacturers ---------------------------------------------------------

class ManufacturerEntry(ApiModel):
    """One manufacturer string and what the logo lookup does with it. `slug` is
    the filename stem the name computes; `aliased_to` is the effective alias
    redirecting it, or null; `logo` is the /assets/ web path that resolves, or
    null; `tables` counts library tables carrying exactly this string."""

    name: str
    slug: str
    aliased_to: str | None
    logo: str | None
    tables: int


class ManufacturerList(ApiModel):
    manufacturers: list[ManufacturerEntry]


# --- Launch ----------------------------------------------------------------

class LaunchRequest(ApiModel):
    """`file` picks one of the table's game files; absent means the default."""

    file: str | None = None


class LaunchLinks(ApiModel):
    state: str
    events: str


class LaunchAccepted(ApiModel):
    """202: the launch is under way, not finished - watch /events for the rest."""

    launching: bool
    table_id: str
    file: str
    links: LaunchLinks


# --- Uploads ---------------------------------------------------------------

class UploadBegun(ApiModel):
    id: str


class UploadSummary(ApiModel):
    file_count: int
    total_bytes: int


class Acknowledged(ApiModel):
    ok: bool


class FileStored(ApiModel):
    bytes: int


class DetectedAssetInfo(ApiModel):
    kind: str
    label: str
    media_key: str
    root: str
    size: int
    detail: str
    preview: str = ""


class Analysis(ApiModel):
    """`unrecognized` lists source-relative paths no rule claimed; `bundle_info` is
    the parsed .info when the upload carried one."""

    source_kind: str
    source_name: str
    has_table: bool
    assets: list[DetectedAssetInfo]
    notes: list[str]
    error: str
    unrecognized: list[str]
    bundle_info: dict | None


class BlockedAsset(ApiModel):
    kind: str
    reason: str


class PlanItem(ApiModel):
    """`index` addresses this item in the `selected` list of an import request."""

    index: int
    kind: str
    label: str
    detail: str
    destination: str
    action: str
    default_enabled: bool
    size: int
    media_key: str


class ImportPlanResource(ApiModel):
    table_path: str
    new_table_dir_name: str
    rom_name: str
    items: list[PlanItem]
    blocked: list[BlockedAsset]


class ImportReport(ApiModel):
    """vps_associated and vps_error report a post-import association that is allowed
    to fail without failing the import - the files are already on disk by then."""

    imported: list[str]
    skipped: list[str]
    table_path: str
    new_table: bool
    media_keys: list[str]
    blocked: list[BlockedAsset]
    vps_associated: bool | None = None
    vps_error: str | None = None


class PlanRequest(ApiModel):
    """Every field optional: an empty body plans the upload as it stands."""

    vps_id: str = ""
    table_path: str = ""
    rom_name: str = ""
    allow_new_table: bool = False


class ImportRequest(PlanRequest):
    """`selected` picks plan items by index; omitted means the plan's own defaults.
    `new_table_dir_name` omitted falls back to the VPS-derived name, then the vpx stem."""

    new_table_dir_name: str | None = None
    selected: list[int] | None = None


# --- VPS -------------------------------------------------------------------

class VpsSearchResult(ApiModel):
    """Straight off a VPSdb entry, so every field is as optional as that data is."""

    vps_id: str | None
    name: str | None
    manufacturer: str | None
    year: int | str | None
    type: str | None
    folder_name: str


class VpsSearchResults(ApiModel):
    results: list[VpsSearchResult]
