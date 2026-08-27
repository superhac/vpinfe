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

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from common.games.collection_store import DEFAULT_DIRECTION, DEFAULT_ORDER_BY


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
    devices: str | None = None


class ServiceEndpoint(ApiModel):
    """One of this install's servers. The port only - the host is wherever the caller
    reached this document, which is the address already known to route here."""

    port: int


class Discovery(ApiModel):
    """`name` is the product and is the same on every install; `install_id` is which
    install this is, which is what a hub holding several of them addresses. A hub files
    that same value under `device_id` in its registry."""

    name: str
    install_id: str
    display_name: str
    roles: list[str]
    api_version: str
    app_version: str
    capabilities: list[CapabilityInfo]
    # Servers that are not the API. `assets` is where artwork is fetched from, which a
    # device cannot guess: it is a different port from the one it asked this on.
    services: dict[str, ServiceEndpoint] = Field(default_factory=dict)
    extensions: list[dict]
    links: DiscoveryLinks


class Health(ApiModel):
    status: str


# --- Devices ---------------------------------------------------------------

class DeviceLinks(ApiModel):
    self_: str = Field(alias="self")


class DeviceResource(ApiModel):
    """One device a hub has seen. `display_name` and `roles` are what that install last
    reported about itself, cached so the registry reads without asking every device - they
    go stale by design, because the install owns them."""

    device_id: str
    kind: str
    display_name: str = ""
    roles: list[str] = Field(default_factory=list)
    address: str = ""
    first_seen: str = ""
    last_seen: str = ""
    links: DeviceLinks


class DeviceList(ApiModel):
    count: int
    devices: list[DeviceResource]


class DeviceAnnouncement(ApiModel):
    """What a device says about itself. The address is not here: the hub reads it off
    the socket, because a device behind a router does not know how it is reached.

    `kind` is a closed set, so an unrecognized one is a 422 rather than a string stored
    and handed to a consumer that switches on it.

    `device_id` is optional only for a device that cannot have one: a `vpx_mobile` entry
    is registered by a person, not by the phone, so the hub mints its id. Omitting it for
    a `vpinfe` install is an error - an install knows what it is called.

    `address` is read for a `vpx_mobile` entry and ignored for the rest. See the handler.
    """

    device_id: str = ""
    kind: Literal["vpinfe", "vpx_mobile"] = "vpinfe"
    display_name: str = ""
    roles: list[str] = Field(default_factory=list)
    address: str = ""


# --- Play ------------------------------------------------------------------

class PlayState(ApiModel):
    """Also the payload of the `play.state_changed` event, so a subscriber and a
    poller see the same shape. `source` is who asked - the frontend filters its
    own launches on it, so dropping the field breaks the remote overlay."""

    launching: bool
    game_name: str | None
    source: str | None


# --- Games -----------------------------------------------------------------

class AssetFileBinding(ApiModel):
    """One asset file, attributed: dedicated to a table, shared (folder-named),
    or orphaned - stem-named for a table that is no longer there."""

    file: str
    binding: str
    table: str | None = None


class AssetEntry(ApiModel):
    """One asset kind on a game. The list endpoint carries presence only; the
    detail endpoint adds the attributed files; alt_color carries its formats."""

    present: bool
    formats: list[str] | None = None
    files: list[AssetFileBinding] | None = None


class GameLinks(ApiModel):
    self_: str = Field(alias="self")
    tables: str
    media: str
    archive: str
    launch: str
    rating: str


class GameOverrides(ApiModel):
    """What the user said, against what was discovered about the machine.

    Kept beside the discovered values rather than written onto them: the fields VPS
    supplies are rebuilt wholesale on every scan, so a value written on top does not
    survive one. Empty means no override - the discovered value stands and is still
    there to go back to.

    These three are the game's because they are about the machine: its name, which VPS
    record it is, and the effect it asks for when somebody browses to it. The ones that
    govern a single file are on the table - see `TableOverrides`.
    """

    alt_title: str = ""
    alt_vps_id: str = ""
    frontend_dof_event: str = ""


class GameDiscovered(ApiModel):
    """What each overridable field would say with no override.

    On the wire because a surface offering to undo an override has to name what it
    undoes to, and the effective value has already resolved that away. Only the fields
    something outside VPinFE supplies appear here - the rest are the user's alone and
    have nothing underneath.
    """

    name: str = ""
    vps_id: str = ""


class TableOverrides(ApiModel):
    """What the user said about one launchable file.

    Per table, because each governs one file: which binary runs it, which ini it
    launches with, and whose nvram is its own. One folder can hold a VPX table and a
    Future Pinball one, and a single value cannot answer for both.
    """

    alt_launcher: str = ""
    plugin_profile: str = ""
    delete_nvram_on_close: bool = False


class OverridesPatch(ApiModel):
    """A change to some overrides. Every field is optional and only what is sent is
    written, so a client can set one without restating the others. Sending `""` (or
    false) clears an override, which is how a value goes back to what was discovered.

    One model for both levels: the route decides which keys it accepts, and a key that
    does not belong to that level is refused rather than quietly dropped.
    """

    alt_title: str | None = None
    alt_vps_id: str | None = None
    frontend_dof_event: str | None = None
    alt_launcher: str | None = None
    plugin_profile: str | None = None
    delete_nvram_on_close: bool | None = None


class GameResource(ApiModel):
    """A game: the pinball-machine concept, not a launchable file. vps_id correlates
    with VPSdb and anything keyed by it; `id` is what identifies the game here."""

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
    # The folder on disk. Reported because it is the one thing a user can act on
    # outside VPinFE, and because two games can read identically without it.
    folder: str = ""
    overrides: GameOverrides = GameOverrides()
    discovered: GameDiscovered = GameDiscovered()
    assets: dict[str, AssetEntry]
    links: GameLinks


class GameList(ApiModel):
    """`total` counts what matched before limit and offset were applied."""

    total: int
    offset: int
    count: int
    games: list[GameResource]


class ResolvedAsset(ApiModel):
    """What this table would use for one kind: dedicated, shared, or none,
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


class Table(ApiModel):
    """A launchable artifact.

    `available` is false for a file the metadata records but which is not on disk -
    worth reporting rather than hiding. `absent_since` says how long that has been
    true, which is the difference between a share that has not mounted and a deletion.

    `hidden` is the user's choice not to be offered this table in the frontend; the
    file stays on disk, because a patch base has to (the patched table cannot be
    rebuilt without it) and a variant may be wanted back. Consumers listing what to
    play should skip these; consumers managing a library should not.

    `default` names the file the table's metadata was derived from, not the one to
    launch - every visible table is independently launchable.
    """

    id: str
    format: str
    app: str
    filename: str
    default: bool
    hidden: bool
    available: bool
    absent_since: str | None = None
    # Read out of the .vpx itself, so a table nobody has matched still says who built
    # it and which revision it is. Both are advisory: a table's embedded metadata is
    # only as careful as its author was, and a VPS match is the better answer wherever
    # there is one. Empty is common and means nothing was recorded.
    version: str = ""
    authors: list[str] = []
    # Of the .vpx and of its script. The pair is how a client tells "the same table
    # again" from "a different build with the same name", which no filename does.
    file_hash: str = ""
    vbs_hash: str = ""
    # What the script was seen to use. Three-valued per feature: true, false, and
    # null for a table nothing has parsed yet - which is not the same as "no".
    features: dict[str, bool | None] = {}
    overrides: TableOverrides = TableOverrides()
    assets: dict[str, ResolvedAsset]
    dependencies: Dependencies


class TableList(ApiModel):
    tables: list[Table]


class LaunchApp(ApiModel):
    """A program that plays a table, and the files it claims.

    `settings_key` names where its binary is configured, so a client can ask whether
    this machine can actually run one rather than assuming a path.
    """

    id: str
    name: str
    suffixes: list[str]
    settings_key: str = ""


class LaunchAppList(ApiModel):
    apps: list[LaunchApp]


class TableRow(ApiModel):
    """A table seen as a row in the library rather than as one game's child.

    Carries its game's name and maker so the row can be read on its own. `rom` is the
    resolved pinmame rom for this file, which is one of the few things that genuinely
    differs between two tables of the same game.
    """

    id: str
    game_id: str
    game: str
    manufacturer: str = ""
    year: str = ""
    filename: str
    version: str = ""
    authors: list[str] = []
    rom: str = ""
    # Whether that rom is actually installed. **Null when the table declares none** -
    # a table with no rom is not required to have one, and reporting that as missing
    # would call every EM table broken. Absence of a declaration and absence of a file
    # are different facts and stay apart.
    rom_installed: bool | None = None
    default: bool = False
    hidden: bool = False
    available: bool = True
    absent_since: str | None = None
    app: str = ""


class TableRowList(ApiModel):
    total: int
    offset: int
    count: int
    tables: list[TableRow]


class TableVisibility(ApiModel):
    """Whether the frontend should offer this table. Hiding never touches the file: a
    patch base has to stay on disk, and a variant may be wanted back."""

    hidden: bool


class TableDefault(ApiModel):
    """Which table a game offers first. Empty clears the choice, which puts it back to
    being resolved from what is in the folder."""

    table: str = ""


class TableForgotten(ApiModel):
    """The id whose record went. No file is named because none was touched - the entry
    described a .vpx that is not on disk."""

    forgotten: str


class PlayRecord(ApiModel):
    """What a person did with this, in a consumer's units rather than the file's - the
    `.info` keeps LastRun as an epoch integer and RunTime in minutes."""

    rating: int = 0
    favorite: bool = False
    tags: list[str] = Field(default_factory=list)
    last_played: str | None = None
    play_count: int = 0
    play_time_seconds: int = 0


class TablePlayRecord(ApiModel):
    """One table's own play record. Counters only - nothing sets a per-table rating."""

    last_played: str | None = None
    play_count: int = 0
    play_time_seconds: int = 0


class EntryGame(ApiModel):
    """The game half of an entry: enough to show it without a second request, which is
    what the play lens is for. `links.game` has the rest.

    No filesystem path - where a game lives is true only of the machine that answered.
    """

    id: str
    vps_id: str
    name: str
    manufacturer: str
    year: str
    type: str
    themes: list[str] = Field(default_factory=list)
    dir_name: str = ""
    manufacturer_logo: str | None = None
    # When the folder appeared, which is what "Newest" sorts on. A stat of the hub's
    # filesystem, so a client sorting its own copy has to be told rather than look.
    created_at: str | None = None
    # Flat, and again inside `user`. The flat one shipped first and clients may read it;
    # `user.rating` is where it belongs beside the rest of the play record.
    rating: int
    user: PlayRecord = Field(default_factory=PlayRecord)


class EntryTable(ApiModel):
    """The table half. `default` is the game's own default, not this entry's position.

    `release_date` is when this build was published, which is the table's own answer and
    not the game's. The .vpx also records a company name, a company year and a playfield
    variant; none is here, because none is populated in practice and the first two would
    duplicate the game's.

    `id` is the same id `GET /games/{id}/tables` reports, so a client can hold one table
    across both lenses.
    """

    id: str
    filename: str
    version: str
    rom: str
    file_hash: str = ""
    default: bool
    hidden: bool = False
    release_date: str | None = None
    authors: list[str] = Field(default_factory=list)
    detects: dict[str, bool] = Field(default_factory=dict)
    user: TablePlayRecord = Field(default_factory=TablePlayRecord)


class EntryAssets(ApiModel):
    """What the game needs to play as intended - not the artwork it is browsed by."""

    pup_pack: bool = False
    alt_color: bool = False
    alt_sound: bool = False


class EntryLinks(ApiModel):
    game: str
    launch: str
    media: str


class Entry(ApiModel):
    """One row of a resolved collection: a table, with the game it belongs to.

    There is no entry id - `table.id` is the identity, and a table appears at most once
    in a collection. `siblings` is how many tables its game offers, so a client can tell
    whether there is anything to switch to without walking the list.
    """

    game: EntryGame
    table: EntryTable
    siblings: int
    assets: EntryAssets = Field(default_factory=EntryAssets)
    # Which art exists, not where it lives: the names of the kinds that resolved. The
    # bytes come from `endpoints.assets`, so naming files here would put a filesystem
    # path on the wire and several hundred kilobytes with it.
    media: list[str] = Field(default_factory=list)
    # Which group this entry falls in under the collection's order - a letter, a year, a
    # rating. Absent when the order has no groups; `EntryList.group_by` says which.
    group: str | None = None
    links: EntryLinks


class EntryList(ApiModel):
    """One entry per game. `collection` is empty for the whole library."""

    collection: str
    count: int
    # What kind of group each entry carries, empty when the order has none - so a client
    # can tell "no grouping here" from "the group happens to be empty".
    group_by: str = ""
    entries: list[Entry]


# --- Media -----------------------------------------------------------------

class MediaEntryLinks(ApiModel):
    self_: str | None = Field(alias="self")


class MediaEntry(ApiModel):
    """Every kind is listed, present or not, so a client enumerates what is
    possible instead of guessing from omissions. `via` says why this file is the one
    being used; `origin` says who put it there, which nothing can derive from the
    other - "unknown" is the honest answer for a file nobody recorded."""

    present: bool
    file: str | None
    via: str | None = None
    origin: str | None = None
    links: MediaEntryLinks


class MediaOverride(ApiModel):
    """A table that has its own file for a kind the game also has one for.

    Named per table rather than counted, because "which one" is the question - a game
    with four tables and one odd backglass is looking for that one.
    """

    table: str
    filename: str
    version: str = ""
    file: str


class MediaOverrideList(ApiModel):
    """Keyed by media kind. A kind no table overrides is absent rather than empty."""

    overrides: dict[str, list[MediaOverride]]


class MediaTier(ApiModel):
    """One tier that holds a file for this kind, and whether it is the one being used.

    The losers are listed too, because they are the answer to the only hard question a
    curator asks: art was replaced and nothing changed, which is always a more specific
    file sitting above the one that was edited.
    """

    tier: str
    file: str
    wins: bool


class MediaDetail(ApiModel):
    """One slot in the detail curation needs and playing a game never asks for.

    Its own route rather than more fields on MediaEntry: this costs a stat and an
    image header read per candidate file, and the media list is on the path a frontend
    walks every time the player changes game - on a library over the network that is
    the difference between free and not. `width`/`height` are images only; reading a
    video's frame size would mean a dependency on ffprobe that nothing else here needs.
    """

    kind: str
    family: str
    present: bool
    file: str | None
    via: str | None = None
    origin: str | None = None
    size_bytes: int | None = None
    modified: str | None = None
    width: int | None = None
    height: int | None = None
    tiers: list[MediaTier] = []
    links: MediaEntryLinks


class FilesystemRoot(ApiModel):
    """A folder browsing may start from. `source` says why it is allowed - this game's
    own folder, the game library, or a folder the owner listed - so a client can
    explain the boundary rather than just enforcing it."""

    path: str
    name: str
    source: str


class FilesystemRootList(ApiModel):
    roots: list[FilesystemRoot]


class FilesystemEntry(ApiModel):
    """One folder or media file. `family` is empty for a folder, which is also how a
    client tells the two apart without reading `kind` twice."""

    name: str
    path: str
    kind: str
    family: str = ""
    size_bytes: int | None = None


class FilesystemListing(ApiModel):
    """`parent` is null at a root, so a client knows where "up" stops without having
    to know which folders are allowed."""

    path: str
    parent: str | None = None
    entries: list[FilesystemEntry]


class MediaSource(ApiModel):
    """An online catalog. `kinds` is what it can serve, so a client can tell a source
    with nothing for this slot from one that is switched off."""

    id: str
    name: str
    url: str
    enabled: bool
    kinds: list[str]


class MediaSourceList(ApiModel):
    sources: list[MediaSource]


class MediaOffer(ApiModel):
    """One file a catalog will hand over. `size` is that source's own word for a
    variant - "4k" against VPinMediaDB - and is empty for a source that publishes one
    of a thing; only the source that produced it has to understand it again."""

    source: str
    name: str
    url: str
    kind: str
    size: str = ""


class MediaOfferList(ApiModel):
    offers: list[MediaOffer]


class MediaPlacement(ApiModel):
    """One place a file could land for this kind, and what putting it there costs.

    `table` is empty for the name every table in the folder resolves, and a table's id
    for a name only that build resolves. It is what a write addresses, so a client
    picks one of these rather than deciding a tier for itself.

    `base` has no extension because the file decides that, and `displaces` does not
    depend on it: a write takes the whole family at that tier, so a .jpg arriving over
    a .png removes the .png and the answer is the same either way.
    """

    table: str
    label: str
    base: str
    displaces: list[str]


class MediaPlacementList(ApiModel):
    """`extensions` is what this kind accepts, in the order the resolver tries them."""

    placements: list[MediaPlacement]
    extensions: list[str]


class MediaImport(ApiModel):
    """A file elsewhere on this machine to copy into the slot, as an absolute path,
    and which build it should serve. Refused unless it is under a browsable root."""

    path: str
    table: str = ""


class CatalogOption(ApiModel):
    """One file vpinmediadb publishes for a kind. `size` is "" for the kinds it
    carries at a single size, which is most of them."""

    size: str
    url: str
    md5: str = ""


class CatalogEntry(ApiModel):
    """What vpinmediadb has for one VPS id, keyed by our media kinds. A kind it does
    not carry is absent rather than empty - there is no topper in the catalog at all,
    and offering an empty one would be a dead choice on a menu."""

    vps_id: str
    kinds: dict[str, list[CatalogOption]]


class MediaFetch(ApiModel):
    """Which source to take a file from, for which VPS entry, and at which size.

    No URL. The hub follows only links a source produced for that id and kind, so a
    caller can never point it at a host of their choosing."""

    source: str
    vps_id: str
    size: str = ""
    table: str = ""


class MediaList(ApiModel):
    media: dict[str, MediaEntry]


class MediaWritten(ApiModel):
    """The name the file was given, and the slot as it stands afterwards.

    Those differ: a folder-named file is outranked by any table-named one, so a
    write can succeed and change nothing about what resolves."""

    written: str
    media: dict[str, MediaEntry]


class MediaRetier(ApiModel):
    """Which build a file should serve after the move. An empty `table` means the
    folder's shared name, which every table in it resolves."""

    table: str = ""


class MediaDisplaced(ApiModel):
    """Folder-relative paths a place would overwrite or delete, answered before the
    bytes are sent. Empty means the slot is free at that tier."""

    displaced: list[str]


class MediaRemoved(ApiModel):
    """Folder-relative paths that went. Empty means there was nothing at that tier."""

    removed: list[str]


# --- Collections -----------------------------------------------------------

class CollectionFilters(ApiModel):
    """A filter collection's criteria. "All" means unconstrained on that axis -
    the vocabulary the filter engine already uses, kept rather than translated so
    a client sees the same values the Manager UI shows.

    `order_by` is the field the collection sorts on and `direction` is which way. They
    used to be `sort_by` and `order_by`, which is what 2.x wrote into the criteria block
    on disk - and there `order_by` is the direction. Carrying that up here gave one word
    two meanings on the wire; the disk keeps its spelling, the wire does not repeat it."""

    letter: str = "All"
    theme: str = "All"
    game_type: str = "All"
    manufacturer: str = "All"
    year: str = "All"
    rating: str = "All"
    rating_or_higher: bool = False
    # Absent rather than false when the collection says nothing about play, because
    # false is a criterion of its own here - it selects what has never been played.
    played: bool | None = None
    order_by: str = DEFAULT_ORDER_BY
    direction: str = DEFAULT_DIRECTION


class CollectionLinks(ApiModel):
    self_: str = Field(alias="self")
    games: str


class CollectionResource(ApiModel):
    """`type` is `manual` (an explicit list of games) or `filter` (criteria applied
    at display time). `game_count` is null for a filter collection, whose membership
    is not a stored list - ask /collections/{name}/games for its current members.
    `filters` is set only for a filter collection."""

    name: str
    type: str
    image: str | None
    game_count: int | None
    filters: CollectionFilters | None
    links: CollectionLinks


class CollectionList(ApiModel):
    collections: list[CollectionResource]


class CreateCollectionRequest(ApiModel):
    """Supplying `filters` makes a filter collection; supplying `games` (or neither)
    makes a manual one. Sending both is refused rather than guessed at."""

    name: str
    filters: CollectionFilters | None = None
    games: list[str] = Field(default_factory=list)


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


class FilterAxis(ApiModel):
    """One thing a collection can filter on.

    `values` are the ones this library actually has, so a client offers a choice that
    matches something. A `rating` axis has no values: it is 0-5 whatever is installed.
    """

    name: str
    scope: str
    kind: str
    summary: str
    values: list[str] | None = None


class FilterAxisList(ApiModel):
    axes: list[FilterAxis]


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
    games: int


class ManufacturerList(ApiModel):
    manufacturers: list[ManufacturerEntry]


# --- Launch ----------------------------------------------------------------

class RatingRequest(ApiModel):
    """0-5, where 0 means unrated. A value outside that is refused rather than
    clamped: silently storing 5 for a caller that sent 9 hides its bug."""

    rating: int = Field(ge=0, le=5)


class Rating(ApiModel):
    rating: int


class LaunchRequest(ApiModel):
    """`file` picks one of the game's tables; absent means the default."""

    file: str | None = None


class LaunchLinks(ApiModel):
    state: str
    events: str


class LaunchAccepted(ApiModel):
    """202: the launch is under way, not finished - watch /events for the rest."""

    launching: bool
    game_id: str
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
    media_kind: str
    root: str
    size: int
    detail: str
    preview: str = ""


class Analysis(ApiModel):
    """`unrecognized` lists source-relative paths no rule claimed; `bundle_info` is
    the parsed .info when the upload carried one."""

    source_kind: str
    source_name: str
    has_game: bool
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
    media_kind: str


class ImportPlanResource(ApiModel):
    game_dir: str
    new_game_dir_name: str
    rom_name: str
    items: list[PlanItem]
    blocked: list[BlockedAsset]


class ImportReport(ApiModel):
    """vps_associated and vps_error report a post-import association that is allowed
    to fail without failing the import - the files are already on disk by then."""

    imported: list[str]
    skipped: list[str]
    game_dir: str
    new_game: bool
    media_kinds: list[str]
    blocked: list[BlockedAsset]
    vps_associated: bool | None = None
    vps_error: str | None = None


class DeclaredIdentity(ApiModel):
    """What the sender says one uploaded file is.

    Whatever delivered the bytes knows what it asked for, and re-deriving that from the
    bytes afterwards is the guess this exists to replace. Every field is optional: a
    caller that inferred an identity says nothing and the file joins the manual queue.

    `confirmed_by` is how the caller knows, not what it wants done about it. The accepted
    values are `declared` - it fetched the file from that record - and `user`, a person in
    that client picked it. There is no value meaning "I guessed", which is what stops a
    client asserting a confidence it did not earn.
    """

    vps_file_id: str = ""
    host_item_id: str = ""
    host: str = ""
    game_id: str = ""
    table_id: str = ""
    confirmed_by: str = ""


class PlanRequest(ApiModel):
    """Every field optional: an empty body plans the upload as it stands."""

    vps_id: str = ""
    game_dir: str = ""
    rom_name: str = ""
    allow_new_game: bool = False


class ImportRequest(PlanRequest):
    """`selected` picks plan items by index; omitted means the plan's own defaults.
    `new_game_dir_name` omitted falls back to the VPS-derived name, then the vpx stem.

    `declared` is keyed by the uploaded file's name, because a bundle carrying a .vpx, a
    backglass and a ROM is one VPS game and three VPS file records - the binding cannot
    live on the session the way `vps_id` does.
    """

    new_game_dir_name: str | None = None
    selected: list[int] | None = None
    declared: dict[str, DeclaredIdentity] | None = None


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
