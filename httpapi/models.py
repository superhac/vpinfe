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

    `feature` is the switch that turns it on, or null for infrastructure that is present
    wherever the API is.
    """

    name: str
    feature: str | None = None
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
    features: list[str]
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
    """One device this install has seen. `display_name` and `features` are what that
    install last
    reported about itself, cached so the registry reads without asking every device - they
    go stale by design, because the install owns them."""

    device_id: str
    kind: str
    display_name: str = ""
    features: list[str] = Field(default_factory=list)
    address: str = ""
    # With the address, what it takes to reach this device. 0 means it never said, which
    # is every entry written before an install sent one.
    port: int = 0
    first_seen: str = ""
    # When it last announced itself, which is once per startup.
    last_seen: str = ""
    # When it was last known to be there, by either route - it announced, or the hub
    # asked and got an answer. This is the one that means "available".
    last_reachable: str = ""
    links: DeviceLinks


class DeviceList(ApiModel):
    count: int
    devices: list[DeviceResource]


class Action(ApiModel):
    """One thing an install can be told to do to itself.

    `available` is whether anything on this build performs it, which is not the same as
    whether the vocabulary has it: a headless install owns no frontend windows.
    """

    scope: str
    action: str
    label: str
    available: bool = True
    reason: str = ""


class ActionList(ApiModel):
    count: int
    actions: list[Action]


class ActionRequest(ApiModel):
    """Which one, and why - the reason travels into the log and to every other surface,
    so "restarted from the Console" reads better afterwards than "restarted"."""

    scope: str
    action: str
    reason: str = ""


class ActionResult(ApiModel):
    """`performed` is false where the request was declined or nothing did it. For an
    action that takes this process or the machine down it means the work was handed
    over, because a process that is stopping cannot report that it stopped."""

    scope: str
    action: str
    what: str
    performed: bool


class LogRecord(ApiModel):
    """One thing that was logged. `message` carries its continuation lines, so a
    traceback arrives whole rather than as a dozen rows with no level."""

    when: str
    level: str
    logger_name: str = Field(alias="logger")
    message: str


class LogRecords(ApiModel):
    count: int
    records: list[LogRecord]
    # Where the file is, so somebody can go and read the rest of it. Empty on an install
    # started with file logging off.
    path: str = ""


class DiscoveredInstall(ApiModel):
    """One install heard announcing itself on this network.

    Not a device: nothing here has been recorded or decided about. Anything on the LAN
    can claim to be a VPinFE install, so this is a list of what said it was there, which
    is what a picker offers and a person confirms.
    """

    install_id: str
    display_name: str = ""
    features: list[str] = Field(default_factory=list)
    address: str = ""
    port: int = 0
    url: str = ""


class DiscoveredList(ApiModel):
    count: int
    installs: list[DiscoveredInstall]


class DeviceProbe(ApiModel):
    """What one device said when asked.

    `state` is `answering`, `unreachable`, or `unaskable` - the last meaning there was
    nothing to dial, which a device being switched off never causes and switching it on
    never fixes. `what` is the product on the other end, written for a person.
    """

    device_id: str
    state: str
    what: str = ""
    reason: str = ""
    features: list[str] = Field(default_factory=list)
    install_id: str = ""
    display_name: str = ""
    # What it said it can do, from the same response its name came in. Absent - rather
    # than empty - from anything that did not answer, and from a build too old to say.
    capabilities: list[str] | None = None


class DeviceProbeList(ApiModel):
    probes: list[DeviceProbe]


class DeviceAnnouncement(ApiModel):
    """What a device says about itself. The address is not here: the hub reads it off
    the socket, because a device behind a router does not know how it is reached.

    `kind` is a closed set, so an unrecognized one is a 422 rather than a string stored
    and handed to a consumer that switches on it.

    `device_id` is optional only for a device that cannot have one: a `vpx_mobile` entry
    is registered by a person, not by the phone, so the hub mints its id. Omitting it for
    a `vpinfe` install is an error - an install knows what it is called.

    `address` is read for a `vpx_mobile` entry and ignored for the rest. See the handler.

    `port` is the other half of being reachable, and unlike the address the device is the
    only party that knows it - the socket says where a request came from, never what that
    machine listens on. Without it a hub has half an address and can only ever read what
    a device chose to tell it.
    """

    device_id: str = ""
    kind: Literal["vpinfe", "vpx_mobile"] = "vpinfe"
    display_name: str = ""
    features: list[str] = Field(default_factory=list)
    address: str = ""
    port: int = 0


# --- Play ------------------------------------------------------------------

class PlayState(ApiModel):
    """Also the payload of the `play.state_changed` event, so a subscriber and a
    poller see the same shape. `source` is who asked - the frontend filters its
    own launches on it, so dropping the field breaks the remote overlay."""

    launching: bool
    game_name: str | None
    source: str | None


class PlayStopped(ApiModel):
    """`stopped` is false when there was nothing to stop, which is an answer rather
    than a failure - a caller racing the player closing it themselves is right either
    way. `game_name` is what was closed, so a UI can say so."""

    stopped: bool
    game_name: str | None


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


class ConfigOptionInfo(ApiModel):
    """One setting as a client should render it. `type` says how to read the value, not
    how it is stored; `choices` is non-empty only for a choice."""

    section: str
    key: str
    type: str
    default: str
    label: str
    description: str = ""
    choices: list[str] = []
    writable: bool = True
    # What this string names on disk, when it names something: file, dir or exe. Empty
    # for everything that is only text, so a client need not match on the key's name.
    path: str = ""
    # A live list worth offering beside this setting, named rather than included: it
    # changes while the install runs, so a client asks for it when it draws. Empty for
    # everything a person simply types.
    suggest: str = ""


class ConfigSection(ApiModel):
    section_name: str = Field(alias="name")
    writable: bool = True
    options: list[ConfigOptionInfo]


class ConfigSchema(ApiModel):
    """What this install has, not what a client thinks it has - a settings page built
    from this cannot offer a setting the install does not carry."""

    sections: list[ConfigSection]
    count: int


class LibraryPolicy(ApiModel):
    """What this library collects. Empty means everything, in all three - so a kind or a
    source added in a later version arrives switched on rather than silently absent.

    The library's rather than an install's: every device reading one hub gets this
    answer, instead of each carrying a copy of a question about somebody else's files.
    """

    hidden_media_kinds: list[str] = Field(default_factory=list)
    hidden_asset_kinds: list[str] = Field(default_factory=list)
    asset_sources: list[str] = Field(default_factory=list)


class LibraryPolicyChange(ApiModel):
    """A patch. An absent key is left alone; a key sent empty is stored empty, because
    "collect everything" is an answer and not the absence of one."""

    hidden_media_kinds: list[str] | None = None
    hidden_asset_kinds: list[str] | None = None
    asset_sources: list[str] | None = None


class ConfigPathCheck(ApiModel):
    """One path setting against this machine's disk.

    `state` is `unset` when the value is blank, which is not a failure - most of these
    are optional and blank means the default. `reason` is written for the person who
    typed it and says what was found, because the path is right there to compare against.
    """

    section: str
    key: str
    path: str
    state: str
    reason: str = ""


class ConfigPathChecks(ApiModel):
    checks: list[ConfigPathCheck]


class ConfigValues(ApiModel):
    """Values keyed section then key, typed as the store types them. A setting the file
    omits answers its default, which is what the install is running on."""

    values: dict[str, dict[str, object]]


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


class PlayRecord(ApiModel):
    """What a person did with this, in a consumer's units rather than the file's - the
    `.info` keeps LastRun as an epoch integer and RunTime in minutes."""

    rating: int = 0
    favorite: bool = False
    tags: list[str] = Field(default_factory=list)
    last_played: str | None = None
    play_count: int = 0
    play_time_seconds: int = 0


class ParkedMatch(ApiModel):
    """`table` names the file it was claimed against, which is what makes the offer to
    restore it specific rather than mysterious."""

    value: str
    table: str = ""
    set_aside: str = ""


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
    # Both read off the game's default table, so both are one of possibly several.
    # `table_count` is what says whether there was a choice to make.
    rom: str
    version: str
    table_count: int = 0
    rating: int
    collections: list[str]
    # The folder on disk. Reported because it is the one thing a user can act on
    # outside VPinFE, and because two games can read identically without it.
    folder: str = ""
    overrides: GameOverrides = GameOverrides()
    discovered: GameDiscovered = GameDiscovered()
    assets: dict[str, AssetEntry]
    # A manual VPS match set aside when the table it was claimed against was replaced.
    # Nothing resolves through it - an invariant says so - and it reaches a client only
    # so a person can be offered it back. Null where there is none.
    parked_vps_id: ParkedMatch | None = None
    # The play record - rating, favorite, tags and the counters. It reached only the
    # play lens (`EntryGame`), so the surface that manages a library could not show
    # what somebody thought of a game or how much they had played it.
    user: PlayRecord = Field(default_factory=PlayRecord)
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


class TablePlayRecord(ApiModel):
    """One table's own play record. Counters only - nothing sets a per-table rating."""

    last_played: str | None = None
    play_count: int = 0
    play_time_seconds: int = 0


class TableSource(ApiModel):
    """Which upstream release a table is, and what established that.

    `confirmed_by` is a closed set with no value meaning "I guessed" - `user` where a
    person picked from a list, `declared` where whatever delivered the bytes said which
    record it fetched, `construction` where we built the file ourselves. Anything that
    inferred an identity sends nothing and the file stays unclaimed.

    A patched file also stores what it was built from. That is not published here: no
    consumer reads it, and a field carrying null on every table is one a reader is
    invited to trust as a discriminator.
    """

    vps_file_id: str = ""
    confirmed_by: str = ""
    # The release named, resolved here because the catalog is already open on this side
    # and the alternative is a client fetching every build of the machine to render one
    # row. Empty where the id names nothing the catalog still holds.
    version: str = ""
    authors: list[str] = []


class TableSourceRequest(ApiModel):
    """An empty id unbinds. There is no field for how sure the caller is: the basis is
    what the endpoint records, and this one always records a person."""

    vps_file_id: str = ""


class AssetSourceRequest(ApiModel):
    """Which VPS record the file at `path` is. `path` is folder-relative, as the ledger
    keys it; an empty id unbinds. Same basis rule as `TableSourceRequest`."""

    path: str
    vps_file_id: str = ""


class AssetSource(ApiModel):
    """One ledger entry's `source`, after a write.

    `host` and `hash` say who placed the file and what they published it as; the other
    two say which upstream record it is. The pair come apart in both directions - a
    hand-placed file can be matched, a downloaded one can be unidentified.
    """

    host: str = ""
    hash: str = ""
    vps_file_id: str = ""
    confirmed_by: str = ""


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
    # Why it is the default, not only that it is: `user` where somebody chose it,
    # `auto` where the resolver picked one - a filename matching the folder, else first
    # alphabetically, which `default_table` itself calls "deterministic rather than
    # correct". Empty on a table that is not the default. A reader needs the two apart:
    # a choice does not move, and a derived pick changes when a table is installed.
    default_kind: str = ""
    # Null on almost every table, and that is the honest answer rather than a gap:
    # nothing has looked, which is a different state from having looked and found
    # nothing. Only a matcher can produce the second, and there is no matcher.
    source: TableSource | None = None
    hidden: bool
    # The table's own, 0 where it has none - which is most of them. The game's rating is
    # the headline and this refines it, so 0 means "the game's stands", not "poor".
    rating: int = 0
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
    # Whether every required-to-launch asset resolves for this file. Three-valued like
    # the rom it is built from: null is a table nothing has parsed, and only false is
    # a fault. Computed here so a second client does not have to re-derive it.
    launchable: bool | None = None
    # This table's own counters. The game's record is the headline; a table that has
    # been played and a sibling that has not is the thing a game's total cannot say.
    user: TablePlayRecord = Field(default_factory=TablePlayRecord)
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
    # This table's own rating, not its game's. 0 is unrated, which is most of them.
    rating: int = 0
    # What the script was seen to use, three-valued per feature: true, false, and null
    # for a table nothing has parsed - which is not the same as no.
    features: dict[str, bool | None] = {}
    # What this table would use per kind, the launch lens `GET .../tables` already
    # answers for a single game. The list projection named its fields by hand and
    # left this one out, so a client showing assets had to ask per game.
    assets: dict[str, ResolvedAsset] = {}
    rom: str = ""
    # Whether that rom is actually installed. **Null when the table declares none** -
    # a table with no rom is not required to have one, and reporting that as missing
    # would call every EM table broken. Absence of a declaration and absence of a file
    # are different facts and stay apart.
    rom_installed: bool | None = None
    # Whether every required-to-launch asset resolves. Three-valued like the rom it is
    # built from: null is a table nothing has parsed, and only false is a fault.
    launchable: bool | None = None
    user: TablePlayRecord = Field(default_factory=TablePlayRecord)
    default: bool = False
    # Why it is the default, not only that it is: `user` where somebody chose it,
    # `auto` where the resolver picked one - a filename matching the folder, else first
    # alphabetically, which `default_table` itself calls "deterministic rather than
    # correct". Empty on a table that is not the default. A reader needs the two apart:
    # a choice does not move, and a derived pick changes when a table is installed.
    default_kind: str = ""
    hidden: bool = False
    available: bool = True
    absent_since: str | None = None
    app: str = ""


class TableRowList(ApiModel):
    total: int
    offset: int
    count: int
    tables: list[TableRow]


class MediaSlot(ApiModel):
    """One media file the library holds, or the absence of one.

    `table` is empty on the **shared** row - the file every table in the folder falls
    through to - and names a table on the rows that have a file of their own. Absence
    is only ever reported on the shared row: an empty table row would assert that a
    table-specific file ought to exist.
    """

    id: str
    game_id: str
    game: str
    manufacturer: str = ""
    year: str = ""
    kind: str
    label: str
    table: str = ""
    table_file: str = ""
    vps_id: str = ""
    # How many tables fall through to this file. **Null on a table row**, which serves
    # the one it is named for - not 1, because the question does not apply.
    serves: int | None = None
    present: bool = False
    file: str | None = None
    path: str | None = None
    # Why this file is the one being used, or why it is not being used at all:
    # "orphan" names a table the folder does not have, and "unused" is correctly named
    # but covered by something more specific - the fallback, which resolves again the
    # moment what covers it is removed.
    via: str | None = None
    # Who put the file here, as far as the .info ledger recorded. "unknown" is the
    # honest answer for anything placed before the ledger or by another tool.
    origin: str | None = None
    matched_to: str | None = None
    # What is filling this slot on the cabinet while the slot itself is empty - a set,
    # or a cross-kind fallback. Another slot's file, so it does not make this row
    # present, but a curator reading "Missing" against a machine that shows something
    # needs to know why.
    standing_in: str = ""


class AssetSlot(ApiModel):
    """One asset file the library holds, or the absence of one.

    `binding` is who the file answers for: "table" where it is named for one .vpx,
    "game" where it is the folder-named file every table falls back to, "orphaned"
    where it is named for a table that is not there, and "none" on the row that stands
    for a file the folder does not have.
    """

    id: str
    game_id: str
    game: str
    manufacturer: str = ""
    year: str = ""
    kind: str
    label: str
    table: str = ""
    table_file: str = ""
    vps_id: str = ""
    binding: str
    present: bool = False
    # How many tables this file answers for. Null on a file named for one table, and
    # **0 on a folder-named file for a kind VPX resolves stem-only** - a `.vbs` or a
    # `.pov` named for the folder is inert, which is a thing worth being able to see.
    serves: int | None = None
    file: str | None = None
    path: str | None = None
    origin: str | None = None
    matched_to: str | None = None


class AssetSlotList(ApiModel):
    total: int
    offset: int
    count: int
    assets: list[AssetSlot]


class MediaSlotList(ApiModel):
    total: int
    offset: int
    count: int
    media: list[MediaSlot]


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
    # Folder-relative, as the ledger keys it. A name cannot be the address: the same
    # name resolves in two places and which is not a client's to guess.
    path: str | None = None
    via: str | None = None
    origin: str | None = None
    # Null means nobody has said, not that a look came back empty.
    matched_to: str | None = None
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
    path: str | None = None
    via: str | None = None
    origin: str | None = None
    matched_to: str | None = None
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

# What a many-valued criterion accepts on the way in. Reported as a list on the way
# out, so a client reads one shape whatever it sent.
MultiValue = str | list[str]


class CollectionFilters(ApiModel):
    """A filter collection's criteria. "All" means unconstrained on that axis -
    the vocabulary the filter engine already uses, kept rather than translated so
    a client sees the same values the Manager UI shows.

    `order_by` is the field the collection sorts on and `direction` is which way. They
    used to be `sort_by` and `order_by`, which is what 2.x wrote into the criteria block
    on disk - and there `order_by` is the direction. Carrying that up here gave one word
    two meanings on the wire; the disk keeps its spelling, the wire does not repeat it."""

    # The many-valued axes accept a list and are always reported as one. A criterion
    # has always been stored comma-joined and the matcher has always split it, so this
    # is the contract catching up with the behavior rather than a new capability - and
    # a bare string typed the schema as single-valued, so no generated client could
    # ever produce one. A list also carries a value containing a comma, which the
    # joined form cannot.
    letter: MultiValue = "All"
    theme: MultiValue = "All"
    game_type: MultiValue = "All"
    manufacturer: MultiValue = "All"
    year: MultiValue = "All"
    # Single by declaration: two ratings at once say nothing that the floor does not
    # say better.
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
    """`type` is derived, not stored: `filter` where the collection carries criteria,
    `manual` where it does not. The two are not kinds - a collection may hold criteria,
    hand-picked members and exclusions together, and `type` only says whether anything
    about it is dynamic.

    `game_count` counts the *stored* members, which is not what the collection resolves
    to: criteria contribute rows that are not stored, and a member naming something
    this library no longer has is counted and resolves to nothing. Ask
    /collections/{name}/members for the stored membership with the state of each, or
    /collections/{name}/games for what it currently resolves to."""

    name: str
    type: str
    # What it is for, in the owner's words. The name has to be short and is the
    # identity; this is where the reason lives.
    description: str = ""
    image: str | None
    # What it resolves to right now - its size, which is the number a reader means by
    # "how big is this collection". `game_count` is the stored membership and the two
    # differ by design: criteria contribute rows that are stored nowhere.
    count: int = 0
    game_count: int | None
    filters: CollectionFilters | None
    # The cap, and how the list is ordered. Both were settable and neither was reported,
    # so a client could apply a cap and have no way to see that one was in force.
    # `manual` order means the stored member array is the order.
    limit: int | None = None
    order_by: str = ""
    direction: str = ""
    # Which boundary the frontend pages between. Empty means the collection says
    # nothing and the player's own setting decides. Settable in the store since paging
    # was built and on no wire model until now, so the Manager UI had a control for it
    # that no API client could have.
    paging_group: str = ""
    links: CollectionLinks


class CollectionList(ApiModel):
    collections: list[CollectionResource]


class CreateCollectionRequest(ApiModel):
    """Supplying `filters` makes a filter collection; supplying `games` (or neither)
    makes a manual one. Sending both is refused rather than guessed at."""

    name: str
    description: str = ""
    filters: CollectionFilters | None = None
    games: list[str] = Field(default_factory=list)


class PatchCollectionRequest(ApiModel):
    """What a collection is, changed in place. Every field is optional and only what is
    sent is written - a rename must not have to restate the criteria.

    `games` replaces the whole membership, in the order given, because the order *is*
    the membership for a manual collection. Refused on a filter collection, whose
    membership comes from its criteria.

    Sending `filters` turns a manual collection into a filter one, which discards a
    hand-picked list - so it is only ever explicit, never a side effect of another edit.
    """

    name: str | None = None
    # "" clears it, which is why this is not a bare falsy check on the way in.
    description: str | None = None
    image: str | None = None
    filters: CollectionFilters | None = None
    games: list[str] | None = None
    limit: int | None = None
    # Absent leaves the cap alone; `limit: null` cannot say "lift it" because absent and
    # null are the same thing over JSON. This says it in a word.
    clear_limit: bool = False
    # How the list is handed out. Settable here for every collection, not only through
    # a filter block: a manual collection has an order too, and until this existed the
    # only way to give it one was to arrange it, so `Title` was unreachable for it.
    # `manual` means the stored member array and is refused where there is not one.
    order_by: str | None = None
    direction: str | None = None
    paging_group: str | None = None


class PreviewRequest(ApiModel):
    """Criteria to resolve against the library without storing anything.

    What an unsaved rule is: `builtin:all` plus these criteria, which is the same
    resolve every saved collection gets. Without it the only way to see what a rule
    would match is to save it first, which makes every experiment live to whoever is
    playing.
    """

    filters: CollectionFilters | None = None
    limit: int | None = None


class MemberTable(ApiModel):
    """One table of a member game, and whether this collection holds it.

    `origin` says which rule put it in or kept it out: `named` (a member names exactly
    this table), `default` (the member names the game and this is what it resolves to),
    `excluded`, `hidden`, or `missing` where the ref names a table the library does not
    have.
    """

    id: str
    # The fields a table is named from, not a name built here. One formatter, and it
    # is the client's: a label computed on both sides is two that can disagree, which
    # is how four surfaces ended up saying the same table four ways.
    version: str = ""
    authors: list[str] = Field(default_factory=list)
    filename: str = ""
    included: bool = True
    origin: str = ""


class CollectionMember(ApiModel):
    """One line of a collection's stored membership, with why it is there.

    Not the resolved list - the *stored* one. A member naming a game that is no longer
    in the library resolves to nothing and vanishes from every other lens; here it is a
    row with `origin: "missing"`, which is what lets an editor offer to clean it up.

    `origin`: `named` (somebody put it here), `filter` (the criteria matched it),
    `excluded` (kept out), `missing` (named, but not in this library).
    """

    game: str
    name: str = ""
    origin: str = ""
    included: bool = True
    # The table *this row names*, empty when it names none. Not the table it resolves
    # to, which is under `tables` - a row naming no table still resolves to one. It is
    # the row's identity: without it a client cannot address one row of a game that has
    # several, and sending the resolved table back matches no ref at all.
    ref_table: str = ""
    tables: list[MemberTable] = Field(default_factory=list)


class CollectionMemberList(ApiModel):
    """`playable` counts the members that resolve to something launchable, which is
    what the collection actually hands out."""

    collection: str
    count: int
    playable: int
    members: list[CollectionMember]


class MemberRequest(ApiModel):
    """Which table a member or an exclusion names, if it names one.

    Absent or empty means the game: a member resolves to whichever table is its
    default, and an exclusion removes the game entire. Naming a table holds the
    collection to exactly that one - COLLECTIONS 2.10 and 2.12.
    """

    table: str = ""
    # Where the new ref goes: directly after this game's ref naming this table, with
    # "" meaning the one that names none. Absent appends, which is what every caller
    # did before this existed. A second table landing at the end of a long collection
    # is indistinguishable from nothing having happened.
    after_table: str | None = None


class MemberTableRequest(ApiModel):
    """Which table a member should name from now on.

    Empty `table` hands the game back its default, so the member follows a replacement
    again. `was` names the ref being changed, which matters only where a game appears
    more than once (COLLECTIONS 2.10); empty means the ref that names no table.
    """

    table: str = ""
    was: str = ""


class CollectionOrderRequest(ApiModel):
    """The membership in the order it should be read.

    A whole list rather than per-item positions: atomic, and neither side does index
    arithmetic. Every id must already be a member - reordering is not a way to add.
    """

    games: list[str]


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


class UpdateCheck(ApiModel):
    """Whether a newer build is published, and whether this install can take it.

    `update_supported` is not the same question as `update_available`: a build that
    cannot replace itself - one run from source, or on a platform with no published
    asset - still wants to be told a newer version exists. `support_reason` says which
    case it is, so a client offers a link where it cannot offer a button.
    """

    update_available: bool = False
    current_version: str | None = None
    latest_version: str | None = None
    update_supported: bool = False
    support_reason: str | None = None
    triplet: str | None = None
    asset_name: str | None = None
    # Set when the check could not be made at all. Not knowing is its own answer and is
    # never reported as "no update".
    error: str | None = None


class UpdateRequest(ApiModel):
    """`stop_table` is the caller saying their user was asked and answered. Default
    false, so a request that says nothing never takes a table away from somebody."""

    stop_table: bool = False


class UpdateStarted(ApiModel):
    """The update is staged and this install is going down to take it.

    Answered before the handoff completes, because completing it means this process is
    gone. A client's next request failing is the update working.
    """

    latest_version: str
    stopped_table: str | None = None


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
    # The name a reader sees. `name` is the stored key and never changes; this may be
    # reworded freely, and a client that derives its own from the key gets "Game type"
    # where the rest of the app says "Type".
    label: str = ""
    summary: str
    # Whether a criterion on this axis may hold several values, which is an OR across
    # them. A client renders a multi-select from this rather than from a list of axis
    # names it holds itself, which is what keeps adding an axis free.
    many: bool = False
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


class FavoriteRequest(ApiModel):
    favorite: bool


class TagsRequest(ApiModel):
    tags: list[str]


class TagMerge(ApiModel):
    """`sources` fold into `into`. Renaming is one source into a name nothing uses."""

    sources: list[str]
    into: str


class TagSweep(ApiModel):
    """How many games changed - not how many carried a source, since one that already
    held the survivor is not a change."""

    changed: int


class Tags(ApiModel):
    """What was stored, which is not always what was sent: each is trimmed and internal
    whitespace collapsed, and the set keeps the first spelling of a repeat."""

    tags: list[str]


class Favorite(ApiModel):
    favorite: bool


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

class VpsKindState(ApiModel):
    """One kind of file, for one game: what we hold and what the catalog lists.

    `obtainable` counts the records pointing at a file rather than a page, and says
    the catalog lists one - never that it is yours to take. A host can hold something
    this account may not see, and nothing here can tell without asking it.

    `why_not` names what the rest are, so a consumer can say "a folder to browse"
    rather than reporting them as missing downloads.
    """

    kind: str
    ours: list[str] = []
    # Which inventory answers whether one is here - `asset` or `media`. On the wire
    # because the two vocabularies share names for different things: `backglass` is a
    # .directb2s among assets and a picture among media, and VPS lists the first.
    held_in: str = ""
    held: bool = False
    # Whether anything here is bound to one of this kind's records. Without it only
    # the vague transition can be reported, which measures four times noisier.
    identified: bool = False
    # The two transitions, and the only fields here measured against a stored
    # baseline rather than derived. `updated` is the record you hold having moved;
    # `new_upstream` counts ones you are not bound to, which is the honest claim when
    # nothing knows which you have. Both silent until watching has been started.
    updated: bool = False
    new_upstream: int = 0
    listed: int = 0
    obtainable: int = 0
    why_not: list[str] = []


class VpsState(ApiModel):
    """State, not findings: which of it is worth surfacing is the consumer's call, made
    with the library in front of it."""

    matched: bool = False
    kinds: list[VpsKindState] = []


class Watching(ApiModel):
    """When this install started counting a catalog change as new. Empty is a real
    third state - not answered - and is why nothing is reported until it is."""

    since: str = ""


class WatchingRequest(ApiModel):
    """An empty `since` means review everything, which is the beginning of time rather
    than the empty string: absent has to keep meaning nobody has answered."""

    since: str = ""


class AcknowledgeRequest(ApiModel):
    """Dismissing one record, for one game and kind."""

    game_id: str
    kind: str
    vps_file_id: str


class LibraryVpsKindTally(ApiModel):
    """One kind, counted in games rather than files. Games, because the question the
    rollup exists to answer is about the collection: a kind held by no game at all is
    a category the collector never engaged with, not a gap in one."""

    kind: str
    ours: list[str] = []
    held_in: str = ""
    holding: int = 0
    identified: int = 0
    listed: int = 0
    obtainable: int = 0
    updated: int = 0
    new_upstream: int = 0


class LibraryVpsState(ApiModel):
    """The rollup, as last counted. `computed` empty means never - which is not the
    same as every count being zero, and reading it as such would report a library
    nobody has looked at as one holding nothing."""

    computed: str = ""
    games: int = 0
    matched: int = 0
    kinds: list[LibraryVpsKindTally] = []


class VpsFieldDiff(ApiModel):
    """One detail the game and its entry disagree about, both sides as one line each -
    a year is a number and themes are a list, and a comparison wants neither shape."""

    field: str
    ours: str
    theirs: str


class VpsDetails(ApiModel):
    """Empty for a game whose details came from the entry it is still matched to,
    which is every game nobody has re-matched: the details were written from the entry,
    so they agree with it by construction."""

    differs: list[VpsFieldDiff] = []


class VpsSearchResult(ApiModel):
    """Straight off a VPSdb entry, so every field is as optional as that data is."""

    vps_id: str | None
    name: str | None
    manufacturer: str | None
    year: int | str | None
    type: str | None
    folder_name: str
    # How many builds exist for this machine. Context for choosing which machine you
    # have, not a choice in itself - the release is a later question.
    releases: int = 0
    # A photograph of the machine, where VPS has one - it does for 39% of entries, so
    # a consumer cannot lay out around it being there.
    img_url: str = ""
    # The entry on VPS, so a surface can link out rather than making somebody search
    # for what it has already identified.
    url: str = ""


class VpsSearchResults(ApiModel):
    results: list[VpsSearchResult]


class VpsSyncState(ApiModel):
    """How fresh the local catalog is. `checked` is when it was last asked, which is not
    when it last changed - asking is cheap and the answer is usually "no"."""

    schedule: str = "daily"
    checked: str = ""
    due: bool = False


class VpsSyncResult(ApiModel):
    """`checked` false means the schedule said not yet; it is not a failure. `changed`
    is the one a surface reports, because a check that found nothing new is the ordinary
    outcome and worth saying quietly."""

    checked: bool = False
    ok: bool = False
    changed: bool = False
    version: str = ""
    at: str = ""
    reason: str = ""


class VpsRelease(ApiModel):
    """One build of a machine, as VPSdb lists it.

    Every field is as optional as the catalog is. `img_url` is the exception worth
    naming: it is present on 95% of releases where it is on 39% of the entries above,
    so a surface over releases can lay out around having a picture.
    """

    vps_file_id: str
    version: str = ""
    authors: list[str] = []
    format: str = ""
    features: list[str] = []
    comment: str = ""
    img_url: str = ""
    updated_at: str = ""
    url: str = ""


class VpsReleases(ApiModel):
    releases: list[VpsRelease]
