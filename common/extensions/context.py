"""The curated facade an extension is handed, and nothing else.

`register(ctx)` never receives the application. Everything below is a narrow view over
one core facility, named for the extension that holds it, so that "which extension did
this?" is answerable from a log line, a config file or a scope.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import TYPE_CHECKING, Any

from common import events as core_events

from . import accounts
from . import cards as cards_module
from .contract import ContractError, Manifest, words
from .contract import why as worded
from .games import ExtensionGames
from .store import ExtensionStore

if TYPE_CHECKING:
    from common import jobs

LOG_ROOT = "vpinfe.ext"


def logger_for(name: str) -> logging.Logger:
    return logging.getLogger(f"{LOG_ROOT}.{name}")


class ExtensionConfig:
    """An extension's settings, under its own name."""

    def __init__(self, name: str, store: ExtensionStore) -> None:
        self._name = name
        self._store = store

    def get(self, key: str, default: str = "") -> str:
        return self.all().get(str(key or "").strip(), default)

    def all(self) -> dict[str, str]:
        return self._store.settings(self._name)

    def set(self, key: str, value: str) -> None:
        self._store.set_setting(self._name, key, value)


class ExtensionEvents:
    """The bus, seen from one extension: it is told what core did, and publishes under
    its own namespace so nothing it emits can be mistaken for a core event."""

    def __init__(self, name: str, declared: tuple[str, ...],
                 on_failure: Callable[..., None]) -> None:
        self._name = name
        self._declared = frozenset(declared)
        self._on_failure = on_failure
        self._logger = logger_for(name)
        self.registered: list[tuple[str, Callable]] = []

    def subscribe(self, event: str, handler: Callable) -> None:
        def contained(**payload: Any) -> None:
            try:
                handler(**payload)
            except Exception:
                self._logger.exception("Handling %s failed", event)
                self._on_failure("extension.reason.failed_handling", event=event)

        core_events.subscribe(event, contained)
        self.registered.append((event, contained))

    def publish(self, event: str, **payload: Any) -> None:
        wanted = str(event or "").strip()
        if wanted not in self._declared:
            raise ContractError(f"{self._name} publishes {wanted!r}, which its manifest "
                                "does not declare")
        core_events.emit(f"{self._name}.{wanted}", **payload)


class ExtensionFiles:
    """The folders an extension works from, so core will accept a path inside one.

    Nothing here stops an extension reading a file - in-process Python cannot be
    prevented from opening one, and pretending otherwise would be theater. What it does
    is let core's own routes take a path the extension is working with: an importer
    converting somebody's old library has to hand core files that are nowhere near ours,
    and without this every one of them is refused.

    Declared rather than assumed, and only by an extension whose manifest asks for it, so
    what an install will read is something a person agreed to and can be shown.
    """

    def __init__(self, name: str, allowed: bool) -> None:
        self._name = name
        self._allowed = allowed
        self._roots: tuple[str, ...] = ()

    def roots(self) -> tuple[str, ...]:
        return self._roots

    def set_roots(self, paths: Iterable[str]) -> None:
        """Replace the set. The user moves a share or points somewhere else, and what
        core will accept has to follow rather than accumulate."""
        if not self._allowed:
            raise ContractError(f"{self._name} sets folders to read from, which needs "
                                "the fs:read capability its manifest does not declare")
        wanted = [str(one or "").strip() for one in paths]
        self._roots = tuple(str(Path(one).expanduser().resolve())
                            for one in wanted if one)


class ExtensionApps:
    """The programs this install can play a table with, as an extension may add to them.

    VPinFE plays Visual Pinball and, through the generic app, anything a person can point
    at a binary. An extension is how a format becomes first-class instead: something that
    claims its own suffixes, so a library of them can be imported and offered rather than
    read and dropped.
    """

    def __init__(self, name: str, scopes: Iterable[str],
                 directory: Path | None = None) -> None:
        self._name = name
        self._scopes = frozenset(scopes)
        self._directory = directory
        self._mine: list[str] = []

    def provide(self, **described: Any) -> str:
        """Add an app, described in plain data. Answers with the id it took.

        `id`, `suffixes`, and optionally `name`, `accepts_keys`, `companions`,
        `fields`, `kinds` and `command`. `command(entry, settings)` answers with a list
        of arguments, or with nothing to run the launcher's binary and arguments the way
        the generic app does.

        Its words are the extension's `i18n/<language>.json` under `app.<id>.`, keyed as
        an app's own file is. A `name` or a field's `label` given here is shown as written.
        """
        from . import provided_apps

        if provided_apps.APPS_PROVIDE not in self._scopes:
            raise ContractError(
                f"{self._name} provides an app, which needs "
                f"{provided_apps.APPS_PROVIDE}, and its manifest does not declare it")
        from common import apps, i18n

        built = provided_apps.build(self._name, described)
        apps.contribute(built)
        self._mine.append(built.id)
        if self._directory is not None:
            i18n.own(f"app.{built.id}", self._directory / "i18n", section=f"app.{built.id}")
        logger_for(self._name).info(
            "provides the %s app for %s", built.id,
            ", ".join(built.claim.suffixes) or "keyed entries")
        return built.id

    def suffixes(self) -> tuple[str, ...]:
        """Every file extension this install can play, its own and any provided.

        Ungated, unlike the library: this says what the build can do, not what the user
        has. An extension deciding whether a foreign library is worth importing needs it
        before it has been granted anything.
        """
        from common import apps

        found: list[str] = []
        for app in apps.all_apps():
            found.extend(app.claim.suffixes)
        return tuple(dict.fromkeys(found))

    def names(self) -> tuple[str, ...]:
        """The product names of the apps here. For a source that says which program a
        system used but not which files it holds - a database found in a folder named
        after the program is often all there is."""
        from common import apps

        return tuple(one.name for one in apps.all_apps() if one.name)

    def plays(self, name: str) -> bool:
        """Whether anything here plays a file of this name, or this bare suffix."""
        wanted = str(name or "").strip().lower()
        if not wanted:
            return False
        return any(wanted == one or wanted.endswith(one) for one in self.suffixes())

    def provided(self) -> tuple[str, ...]:
        """What this extension has added, which is what gets taken back with it."""
        return tuple(self._mine)

    def withdraw(self) -> None:
        """Take them all back. Called when the extension is unloaded, so a disabled
        extension does not leave a suffix claimed by something that is no longer here."""
        from common import apps, i18n

        for app_id in self._mine:
            apps.withdraw(app_id)
            i18n.disown(f"app.{app_id}")
        self._mine.clear()


COLUMN_KINDS = frozenset({"text", "number", "date"})
RANKING_KINDS = frozenset({"number", "date"})
RELATION_KEYS = frozenset({"vps_entry", "vps_release"})


class ExtensionUI:
    """What an extension offers a person: its actions, and the page they sit on.

    Declared rather than drawn. An extension that painted its own page would tie the
    Console's look to whoever wrote it, and would stop working the moment that extension
    moved out of this process - where a task described as data still does. Core owns the
    treatment; the extension owns what is asked and what happens.

    An action is one call on the extension's own router. What varies is whether it takes
    input, whether it warrants confirming, and whether it finishes now or hands back a
    job - and core reads each of those off what the extension answers rather than from a
    mode it declares, because a declared mode is a second statement of the same thing and
    the two drift.

    A form with no fields is pressed and happens. A form with fields is filled in first.
    A form naming a confirm gets a step showing what would happen before it runs. The
    run answers with a job where it is slow and with the outcome where it is not.

    A word left out is looked up in the extension's own `i18n/<language>.json`:
    `action.<key>.label`, `community.<key>.title`, `settings.label` and so on, as
    `docs/extensions.md` lists them. One given is shown as written.
    """

    def __init__(self, name: str, allowed: bool) -> None:
        self._name = name
        self._allowed = allowed
        self.actions: list[dict] = []
        self.community_lists: list[dict] = []
        self.settings_label = ""
        self.state_label = ""
        self.settings_base = ""
        self.state_base = ""
        self.account_offered: dict = {}

    def action(self, key: str, base: str, *, label: str = "",
               description: str = "") -> None:
        """A verb somebody can press, in the vocabulary the rest of the app uses."""
        if not self._allowed:
            raise ContractError(f"{self._name} offers an action, which needs the "
                                "ui:mount capability its manifest does not declare")
        wanted = str(key or "").strip()
        if not wanted:
            raise ContractError(f"{self._name} offers an action with no key")
        self.actions.append({
            "key": wanted,
            "label": str(label or "").strip(),
            "description": str(description or "").strip(),
            "base": str(base or "").strip(),
        })

    def community(self, key: str, base: str, *, columns: list[dict], title: str = "",
                  views: list[dict] | None = None, relation: dict | None = None,
                  tag: str = "", about: str = "") -> None:
        """A list this extension holds, shown under Community.

        `base` is a route of this extension's answering `{"rows": [...]}`. `about` is one
        answering `{"status", "acts"}`: the line the list's page says, and what its menu
        offers. A column is
        `{"field", "header", "kind"}` with `kind` one of `text`, `number`, `date`, and the
        first may name `under`: row fields drawn on the line beneath its value. A view is
        `{"key", "name", "columns", "sort": [{"field", "desc"}], "help", "ranks"}`, and one
        that `ranks` is offered as an order for a collection, so it needs a `relation` and
        a sort on number or date columns only. `relation` is `{"field", "keys"}`, `keys`
        being `vps_entry` or `vps_release`. `tag` is put on every game (`vps_entry`) or
        table (`vps_release`) of this library the list relates to, so it needs a
        `relation`.
        """
        self._needs_ui("a community list")
        wanted = str(key or "").strip()
        fields = [str((one or {}).get("field") or "").strip() for one in columns]
        if not wanted or not columns or not all(fields):
            raise ContractError(f"{self._name} declares a community list with no key or "
                                "a column with no field")
        if any((one or {}).get("under") for one in columns[1:]):
            raise ContractError(f"{self._name} puts a line under a column other than the "
                                "first, which is the only one drawn with one")
        kinds = {str((one or {}).get("kind") or "text") for one in columns}
        if not kinds <= COLUMN_KINDS:
            raise ContractError(f"{self._name} declares a column kind core does not draw: "
                                f"{', '.join(sorted(kinds - COLUMN_KINDS))}")
        for view in views or []:
            named = set(view.get("columns") or []) | {str(one.get("field") or "")
                                                      for one in view.get("sort") or []}
            if not str(view.get("key") or "").strip() or not named <= set(fields):
                raise ContractError(f"{self._name} declares a view with no key or on a "
                                    "column it does not have")
        if relation and (relation.get("field") not in fields
                         or relation.get("keys") not in RELATION_KEYS):
            raise ContractError(f"{self._name} relates its list on a field it does not "
                                "have, or by something other than a VPS entry or release")
        derived = " ".join(str(tag or "").split())
        if derived and not relation:
            raise ContractError(f"{self._name} derives a tag from a list that relates to "
                                "nothing in the library")
        measured = {field for field, one in zip(fields, columns, strict=True)
                    if str((one or {}).get("kind") or "text") in RANKING_KINDS}
        for view in views or []:
            if not view.get("ranks"):
                continue
            sorted_on = {str(one.get("field") or "") for one in view.get("sort") or []}
            if not sorted_on or not sorted_on <= measured:
                raise ContractError(f"{self._name} ranks by a view that sorts on nothing, "
                                    "or on a column that is not a number or a date")
            if not relation:
                raise ContractError(f"{self._name} ranks by a view of a list that relates "
                                    "to nothing in the library")
        self.community_lists.append({
            "key": wanted, "title": str(title or "").strip(),
            "base": str(base or "").strip(),
            "columns": [{"field": field, "header": str(one.get("header") or ""),
                         "kind": str(one.get("kind") or "text"),
                         "help": str(one.get("help") or ""),
                         "under": [str(name) for name in one.get("under") or []]}
                        for field, one in zip(fields, columns, strict=True)],
            "views": [{"key": str(view["key"]).strip(),
                       "name": str(view.get("name") or "").strip(),
                       "columns": list(view.get("columns") or fields),
                       "sort": [{"field": str(one["field"]), "desc": bool(one.get("desc"))}
                                for one in view.get("sort") or []],
                       "help": str(view.get("help") or ""),
                       "ranks": bool(view.get("ranks"))} for view in views or []],
            "relation": dict(relation) if relation else None,
            "tag": derived,
            "about": str(about or "").strip(),
        })

    def settings(self, base: str, label: str = "") -> None:
        """Say that this extension has settings, and where core may read and write them.

        Declared rather than drawn, like everything else here: the fields come back from
        that call and core renders them in the one grammar the rest of the application
        uses, so an extension's settings look like settings.
        """
        self._needs_ui("settings")
        self.settings_base = str(base or "").strip()
        self.settings_label = str(label or "").strip()

    def state(self, base: str, label: str = "") -> None:
        """Say that this extension holds something worth showing, and where to read it.

        A list of rows, each a label, a line under it, and at most two things you can do
        to it. Deliberately poor: it is enough for the accounts a connector is holding
        and not enough to become a page somebody draws, and the day a third extension
        needs more than this is the day to look again rather than to widen it now.
        """
        self._needs_ui("state")
        self.state_base = str(base or "").strip()
        self.state_label = str(label or "").strip()

    def account(self, base: str, *, label: str = "", cards: Iterable[str] = (),
                marker: str = "") -> None:
        """Say that a player can hold an account with this extension.

        `base` is a route of this extension's, asked with a player's id as
        `docs/extensions.md` lists: the fields, a status line, the acts, and the card.
        `cards` are the `type`s of card it reads. `marker` names where a card it makes
        hides its text, and is the extension's name unless given.
        """
        self._needs_ui("an account")
        if self.account_offered:
            raise ContractError(f"{self._name} offers a second account; a player holds "
                                "one account with an extension")
        wanted = str(base or "").strip()
        hidden = str(marker or self._name).strip()
        read = tuple(dict.fromkeys(str(one or "").strip() for one in cards))
        if not wanted or not all(read) or not cards_module.MARKER.match(hidden):
            raise ContractError(f"{self._name} offers an account with no route, a card "
                                "with no type, or a marker that is not a plain name")
        self.account_offered = {"base": wanted, "label": str(label or "").strip(),
                                "cards": list(read), "marker": hidden}

    def kept(self, key: str) -> dict | None:
        """The last good read core keeps of one of this extension's Community lists:
        `{"rows", "read_at"}`, or None where there has been none."""
        from common.games import community_lists

        self._needs_ui("a kept list")
        said = community_lists.kept(self._name, str(key or "").strip())
        if said["rows"] is None:
            return None
        return {"rows": said["rows"], "read_at": said["read_at"]}

    def _needs_ui(self, what: str) -> None:
        if not self._allowed:
            raise ContractError(f"{self._name} offers {what}, which needs the ui:mount "
                                "capability its manifest does not declare")


PLAYERS_READ = "players:read"


class ExtensionPlayers:
    """Who plays here, and the accounts this extension holds for them.

    The roster is read as plain data, the rows `players.changed` carries. Reading it needs
    `players:read` in the manifest: names and initials are about people. An account's
    values are this extension's own and need nothing declared.
    """

    def __init__(self, name: str, scopes: Iterable[str], store: ExtensionStore) -> None:
        self._name = name
        self._reads = PLAYERS_READ in frozenset(scopes)
        self._store = store

    def roster(self) -> list[dict]:
        """Every player: the owner, the kept players, then the guests as they joined."""
        self._needs_read()
        from common import players

        return players.get_roster().state()["players"]

    def get(self, player_id: str) -> dict | None:
        wanted = str(player_id or "").strip()
        return next((one for one in self.roster() if one["id"] == wanted), None)

    def up(self) -> list[dict]:
        """Who the next game counts for."""
        return [one for one in self.roster() if one["up"]]

    def record(self, player_id: str, game_id: str) -> dict | None:
        """A player's record of one game, as `GET /api/v1/players/{id}/record` lists it.
        None for the owner and for a player nobody has."""
        self._needs_read()
        from common import players
        from common.games import player_records

        player = players.get_roster().get(player_id)
        if player is None or player.owner:
            return None
        return player_records.get_records().shown(player, str(game_id or "").strip())

    def sharing(self, player_id: str) -> bool:
        """Whether this player's account here is sharing. Off until someone turns it on."""
        from common import players

        return players.get_roster().sharing(player_id, self._name)

    def account(self, player_id: str) -> dict[str, str]:
        """This player's account here, secrets included. Empty when they hold none."""
        return accounts.values(self._name, player_id, self._store)

    def set_account(self, player_id: str, values: dict[str, Any]) -> None:
        """Replace this player's account here. Empty values remove it. A guest's is held
        in memory and never written."""
        accounts.keep(self._name, player_id, values, self._store)

    def holders(self) -> list[str]:
        """The ids of every player holding an account here, in roster order."""
        return accounts.holders(self._name, self._store)

    def _needs_read(self) -> None:
        if not self._reads:
            raise ContractError(f"{self._name} reads the players, which needs "
                                f"{PLAYERS_READ}, and its manifest does not declare it")


class ExtensionEntries:
    """What this extension adds to every entry a theme is handed.

    One key, filled in by core when the player moves to a game. A theme reads
    `entry.ext.<key>` and never learns which extension answered - which is the point: the
    surface a theme sees does not grow a method per connector.
    """

    def __init__(self, name: str) -> None:
        self._name = name

    def contribute(self, key: str, fetch: Callable[[dict], object]) -> None:
        """Answer about one game at a time.

        `fetch` is given a plain description of the game - its ids and what is known
        about the machine - and returns whatever a theme should read, or None where there
        is nothing to say. It is called on core's thread when the wheel stops, so it may
        block; it must not raise for a game it simply has no answer about.
        """
        from . import contributions

        wanted = str(key or "").strip()
        if not wanted:
            raise ContractError(f"{self._name} contributes under no key")
        contributions.register(self._name, wanted, fetch)

    def stale(self, key: str) -> None:
        """What this extension answered under `key` is out of date: core drops what it
        holds, and asks again the next time each game is reached."""
        from . import contributions

        contributions.forget_answers(self._name, str(key or "").strip())

class ExtensionCatalogs:
    """Outside places a game, a table or a file can be reached, which core draws."""

    def __init__(self, name: str) -> None:
        self._name = name

    def contribute(self, key: str, name: str, subject: str,
                   link: Callable[[dict], str]) -> None:
        """`subject` is `game`, `table` or `file`. `link` is given a plain description
        of one and answers its address there, or "" where it has none."""
        from . import catalogs

        wanted = str(key or "").strip()
        if not wanted or not str(name or "").strip():
            raise ContractError(f"{self._name} contributes a link with no key or name")
        try:
            catalogs.register(self._name, wanted, str(name).strip(), str(subject or ""),
                              link)
        except ValueError as exc:
            raise ContractError(str(exc)) from exc


class ExtensionTokens:
    """Names a user may write into a command, brought by this extension.

    Stored as `<extension>.<name>`.
    """

    # The two moments a command runs, so an extension names one without importing core.
    VPINFE = "vpinfe"
    TABLE = "table"

    def __init__(self, name: str) -> None:
        self._name = name

    def offer(self, name: str, contexts: Iterable[str], value: Callable[[dict], str], *,
              says: str = "", after_only: bool = False) -> str:
        """Answer with the full name, which is what a user types. What it stands for is
        `says`, or `token.<name>.says` in the extension's own catalog."""
        from common import tokens

        try:
            return tokens.register(self._name, name, frozenset(contexts), value,
                                   says=says, after_only=after_only)
        except ValueError as exc:
            raise ContractError(str(exc)) from exc


class ExtensionJobs:
    """Slow work, run the way core runs it.

    The kind carries the extension's name, so a job somebody is watching says which
    extension is doing it - the same reason the log namespace does. One at a time per
    kind, which is core's rule and is right here too: two imports of one library at once
    would race each other into the same folders.
    """

    def __init__(self, name: str) -> None:
        self._name = name

    def submit(self, kind: str, work: Callable[[jobs.Job], object]) -> jobs.Job:
        from common import jobs

        return jobs.submit(f"{self._name}.{str(kind or '').strip()}", work)

    def active(self) -> tuple[str, ...]:
        from common import jobs

        return tuple(job.id for job in jobs.active()
                     if job.kind.startswith(f"{self._name}."))


class ExtensionContext:
    """What `register(ctx)` is given."""

    def __init__(self, manifest: Manifest, store: ExtensionStore,
                 on_failure: Callable[..., None], directory: Path | None = None) -> None:
        self.name = manifest.name
        self.manifest = manifest
        self.logger = logger_for(manifest.name)
        self.config = ExtensionConfig(manifest.name, store)
        self.events = ExtensionEvents(manifest.name, manifest.events, on_failure)
        self.files = ExtensionFiles(manifest.name, "fs:read" in manifest.capabilities)
        self.jobs = ExtensionJobs(manifest.name)
        self.ui = ExtensionUI(manifest.name, "ui:mount" in manifest.capabilities)
        self.players = ExtensionPlayers(manifest.name, manifest.scopes, store)
        self.entries = ExtensionEntries(manifest.name)
        self.catalogs = ExtensionCatalogs(manifest.name)
        self.tokens = ExtensionTokens(manifest.name)
        self.games = ExtensionGames(manifest.name, manifest.scopes, self.files)
        self.apps = ExtensionApps(manifest.name, manifest.scopes, directory)
        # Which program this is, for an extension that has to say so to somebody else.
        # Through the context rather than an import: the one module an extension may
        # import is the contract, and that is what makes the boundary checkable.
        from common.vpinfe_version import get_version

        self.host_version = get_version()
        self.routers: list[tuple[Any, str]] = []
        # Registration is a moment, not a phase: routers are mounted once, so one added
        # after `register` returned would never be reachable and silently answer nothing.
        self.open = True

    def t(self, key: str, /, **params: Any) -> str:
        """What this extension's `i18n/<language>.json` says for `key`, in the language
        now set: a wizard's title, a field's label, a sentence a route answers with."""
        return words(self.name)(key, **params)

    def why(self, exc: BaseException, /, at: str | os.PathLike[str] = "") -> str:
        """What core says under a failure of its own: `contract.why`."""
        return worded(exc, at)

    def scope(self, action: str) -> str:
        """The scope for one of this extension's own actions."""
        return f"ext:{self.name}:{str(action or '').strip()}"

    def add_router(self, router: Any, *, scope: str) -> None:
        """Offer routes under `/api/v1/ext/<name>/`, gated on a scope this extension
        declared. Core attaches the gate; the extension cannot choose to have none."""
        if not self.open:
            raise ContractError(f"{self.name} added a router after registering")
        allowed = {self.scope(action) for action in self.manifest.provides}
        if scope not in allowed:
            raise ContractError(
                f"{self.name} gates a router on {scope!r}, which its manifest does not "
                f"provide. Declared: {', '.join(sorted(allowed)) or 'none'}")
        self.routers.append((router, scope))
