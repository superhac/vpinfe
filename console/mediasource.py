"""Where a file comes from, in one place.

Three ways in, because there are three: the computer you are looking at this from, the
machine VPinFE runs on, and the catalogs. A collection's picture has a fourth, the art its
games already have, and a table has one with no file at all. Anything already on a disk
is one browser rather than a tab apiece - this game's folder, another game's, and a folder
of downloads are the same act, and splitting them made three answers to one question.

A slot's file lands under the slot's name at the tier the lens is on, and whatever it
displaced was named before it went.
"""

from __future__ import annotations

import logging
import mimetypes
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any

from nicegui import run, ui

from common import i18n, icons
from common.failures import why
from common.games.asset_registry import ARCHIVE_EXTENSIONS, spec_for, specs_named
from common.i18n import t
from common.media_specs import (
    IMAGE_FAMILY,
    MEDIA_SPECS,
    canonical_kind,
    media_family,
    media_label_map,
)
from console import (
    art,
    candidates,
    confirm,
    deeplink,
    game_tables,
    media_ownership,
    offload,
    panel,
    uploads,
    verbs,
)
from console import dialog as frame

logger = logging.getLogger("vpinfe.console.mediasource")

# Enough of a list to scroll rather than to page. A folder of artwork is tens of files,
# not thousands, and a picker with pages in it is a database browser.
_LIST_MAX = 60

# Where `.console-source-host` cuts the tab's label, at 20ch.
_HOST_NAME_MAX = 20
_FIND_FROM = 8

SIZE_NAMES = {"4k": "config.media.playfield_resolution.choice.4k",
              "1k": "config.media.playfield_resolution.choice.1k"}

# Only a drag carrying files belongs to the dialog: text dragged within a field is left
# to the field.
_FILES = "Array.from(e.dataTransfer.types || []).includes('Files')"
_TAKE = (f"if (!{_FILES}) return; e.preventDefault(); e.stopPropagation(); ")
_LIGHT = ("(e) => { " + _TAKE + "e.dataTransfer.dropEffect = 'copy'; "
          "e.currentTarget.classList.add('console-drop-hot'); }")
_DIM = ("(e) => { if (!e.currentTarget.contains(e.relatedTarget)) "
        "e.currentTarget.classList.remove('console-drop-hot'); }")
_MANY = ("(e) => { " + _TAKE + "e.currentTarget.classList.remove('console-drop-hot'); "
         "window.__consoleDrop(e.dataTransfer, emit); }")


def _one(uploader_id: int) -> str:
    """A single file goes to the uploader; anything else comes back as a count."""
    return ("(e) => { " + _TAKE + "e.currentTarget.classList.remove('console-drop-hot'); "
            "const folder = Array.from(e.dataTransfer.items || []).some(item => "
            "((item.webkitGetAsEntry && item.webkitGetAsEntry()) || {}).isDirectory); "
            "const files = Array.from(e.dataTransfer.files || []); "
            "if (folder || files.length !== 1) { emit({count: files.length, folder}); return; } "
            f"getElement({uploader_id}).$refs.qRef.addFiles(files); }}")


def _size(count: int | None) -> str:
    """Nothing for a file whose size is not known."""
    return i18n.size(count) if count else ""


def _suffix(item: dict[str, Any]) -> str:
    return PurePosixPath(str(item.get("name") or "")).suffix.lower()


async def confirm_replace(label: str, going: list[str]) -> bool:
    """Name what a write would replace, and wait for a yes.

    The files are listed rather than counted because the surprising case is the one a
    count hides: a whole family goes at this tier, so a .mp4 arriving over a .png takes
    the .png with it and the user never named that file.
    """
    return await confirm.ask(t("console.mediasource.replace", kind=label),
                             detail=t("console.mediasource.replaced_files_deleted_not"),
                             lines=going, confirm=t("word.replace"), icon=verbs.REPLACE)


@dataclass(frozen=True)
class _Target:
    """What the dialog fills: the calls that fill it, and which files on disk can."""

    placements: Callable[..., dict]
    displaced: Callable[..., list[str]]
    place: Callable[..., dict]
    bring: Callable[..., dict]
    fits: Callable[[dict[str, Any]], bool]
    family: str
    online: bool
    accept: tuple[str, ...] = ()
    lists: str = ""


def _media(library: Any, kind: str) -> _Target:
    family = media_family(kind)
    spec = next((item for item in MEDIA_SPECS if item.kind == canonical_kind(kind)), None)
    return _Target(library.placements, library.displaced_by, library.place_media,
                   library.import_media, lambda item: item.get("family") == family,
                   family, online=True, accept=spec.family if spec else ())


def _asset(library: Any, kind: str) -> _Target:
    wanted = spec_for(kind).extensions
    return _Target(library.asset_placements, library.asset_displaced_by,
                   library.place_asset, library.import_asset,
                   lambda item: _suffix(item) in wanted, "", online=False,
                   accept=wanted, lists=kind)


def _host_name(library: Any) -> str:
    return str(library.discovery().get("display_name") or "")


class _Sources:
    """One Add dialog: its tabs, its drop, and the host's folders.

    A subclass says what is being filled - the title, where the host tab starts, which
    files there can fill it, and what happens to a file once it arrives.
    """

    uploads = True
    online = False
    games = False
    keyed = False

    def __init__(self, library: Any, label: str, done: Callable, current: str = "") -> None:
        self.library = library
        self.label = label
        self.done = done
        # The path on the host of what fills this now, which the host tab marks rather
        # than offers.
        self.current = current
        self.dialog: Any = None
        # Filled when the browser loads; the trail above a listing is written against
        # them, so a folder is named from its start rather than from "/".
        self.browse_roots: list[dict[str, Any]] = []

    def title(self) -> str:
        raise NotImplementedError

    def starts(self) -> list[dict[str, Any]]:
        """Where the host tab may begin. Blocking."""
        raise NotImplementedError

    def listing(self, path: str) -> dict[str, Any]:
        """One folder on the host. Blocking."""
        return self.library.browse(path)

    def fits(self, item: dict[str, Any]) -> bool:
        raise NotImplementedError

    def file_row(self, item: dict[str, Any]) -> None:
        raise NotImplementedError

    def folder_use(self, path: str) -> Callable | None:
        """What Use does on a folder row, or None where a folder is only a way down."""
        return None

    def before(self) -> None:
        """Drawn ahead of the tabs, so it is there whichever tab is open."""

    def zone(self, card: Any) -> None:
        """The Upload tab's words and pickers, and what a drop on the card does."""
        raise NotImplementedError

    def opened(self, above: ui.column) -> None:
        """Called once the dialog is up, with the space over the tabs."""

    async def online_tab(self, body: ui.column) -> None:
        return None

    async def games_tab(self, body: ui.column) -> None:
        return None

    async def keyed_tab(self, body: ui.column) -> None:
        return None

    def open(self) -> None:
        with frame.opened(self.title(), classes="console-sources-card") as box:
            self.dialog = box
            card = ui.context.slot.parent
            self.before()
            above = ui.column().classes("w-full gap-0 px-3")

            # Ordered by how far the file has to travel: your own computer, this library,
            # the machine VPinFE runs on, then the internet.
            host = _host_name(self.library)
            with ui.tabs().props("dense no-caps align=left").classes("w-full px-3") as tabs:
                if self.uploads:
                    ui.tab("upload", label=t("console.mediasource.upload"),
                           icon=verbs.FROM_FILE)
                if self.games:
                    ui.tab("games", label=t("console.mediasource.its_games"),
                           icon=icons.GAMES)
                named = ui.tab("host", label=host, icon=verbs.FROM_HOST) \
                    .classes("console-source-host")
                if len(host) > _HOST_NAME_MAX:
                    named.tooltip(host)
                if self.online:
                    ui.tab("online", label=t("console.mediasource.online"),
                           icon=verbs.FROM_ONLINE)
                if self.keyed:
                    ui.tab("keyed", label=t("console.mediasource.without_file"),
                           icon=verbs.WITHOUT_FILE)
            online_body: ui.column | None = None
            games_body: ui.column | None = None
            keyed_body: ui.column | None = None
            first = "upload" if self.uploads else "host"
            with ui.tab_panels(tabs, value=first).classes("w-full console-sources-panels"):
                if self.uploads:
                    with ui.tab_panel("upload"), \
                            ui.column().classes("console-slot-blank console-source-zone "
                                                "items-center gap-2"):
                        ui.icon(verbs.FROM_FILE).classes("console-slot-blank-icon")
                        self.zone(card)
                if self.games:
                    with ui.tab_panel("games"):
                        games_body = ui.column().classes("w-full gap-2 console-source-fill")
                with ui.tab_panel("host"):
                    host_body = ui.column().classes("w-full gap-2 console-source-fill")
                if self.online:
                    with ui.tab_panel("online"):
                        online_body = ui.column().classes("w-full gap-2 console-source-fill")
                if self.keyed:
                    with ui.tab_panel("keyed"):
                        keyed_body = ui.column().classes("w-full gap-2 console-source-fill")
            with frame.footer():
                frame.cancel(box.close)
        if self.uploads:
            card.on("dragover", js_handler=_LIGHT)
            card.on("dragleave", js_handler=_DIM)

        box.open()
        self.opened(above)

        # Each tab reads when it is opened rather than up front: two of the three make a
        # request, and a dialog that fetches everything before showing anything would be
        # slowest at the thing people do most, which is drop a file on the first tab.
        loaded: set[str] = set()

        async def load(event: Any) -> None:
            if event.value in loaded:
                return
            loaded.add(event.value)
            if event.value == "host":
                await self.host_tab(host_body)
            elif event.value == "online" and online_body is not None:
                await self.online_tab(online_body)
            elif event.value == "games" and games_body is not None:
                await self.games_tab(games_body)
            elif event.value == "keyed" and keyed_body is not None:
                await self.keyed_tab(keyed_body)

        tabs.on_value_change(load)
        if first == "host":
            loaded.add("host")
            with box:
                ui.timer(0, lambda: self.host_tab(host_body), once=True)

    async def finish(self, message: str) -> None:
        self.dialog.close()
        ui.notify(message, type="positive")
        await self.done()

    # --- from anywhere on the machine VPinFE runs on -------------------------

    async def host_tab(self, body: ui.column) -> None:
        body.clear()
        try:
            starts = await offload.io(self.starts)
        except Exception as exc:
            with body:
                panel.line(t("console.mediasource.could_not_read_host",
                             host=_host_name(self.library)), hint=why(exc))
            return
        self.browse_roots = starts
        with body:
            if not starts:
                ui.label(t("console.mediasource.no_folders_browsable_game")) \
                    .classes("console-help")
                return
            # The control before what it controls: built the other way round, the
            # picker sits under the folder it chose.
            picker = (ui.select({item["path"]: _start_name(item) for item in starts},
                                value=starts[0]["path"], label=t("console.mediasource.start"))
                      .props("outlined dense").classes("w-full")
                      if len(starts) > 1 else None)
            listing = ui.column().classes("w-full gap-1 console-source-fill")
            if picker is not None:
                picker.on_value_change(lambda event: self._show_folder(listing,
                                                                      event.value))
            await self._show_folder(listing, starts[0]["path"])

    async def _show_folder(self, listing: ui.column, path: str) -> None:
        listing.clear()
        try:
            here = await offload.io(self.listing, path)
        except Exception as exc:
            with listing:
                panel.line(t("console.mediasource.could_not_read_folder"), hint=why(exc))
            return
        with listing:
            # Named from the start it was reached through rather than as an absolute
            # path: the path on a cabinet is long, and the tail is the part that says
            # where you are.
            ui.label(self._trail(here["path"])).classes("console-help console-source-trail")
            with ui.column().classes("w-full gap-1 console-source-list"):
                if here.get("parent"):
                    self._folder_link("..", here["parent"], listing, up=True)
                shown = 0
                for item in here["entries"][:_LIST_MAX]:
                    if item["kind"] == "folder":
                        self._folder_link(item["name"], item["path"], listing)
                    elif self.fits(item):
                        self.file_row(item)
                    else:
                        continue
                    shown += 1
                if not shown:
                    ui.label(t("console.mediasource.nothing_use", kind=self.label)) \
                        .classes("console-help")
                elif len(here["entries"]) > _LIST_MAX:
                    ui.label(t("console.mediasource.more_not_shown",
                            count=len(here["entries"]) - _LIST_MAX)) \
                        .classes("console-help")

    def _trail(self, path: str) -> str:
        """Where this folder sits, counted from the start it was reached through."""
        for root in self.browse_roots:
            base = str(root.get("path") or "").rstrip("/")
            if not base:
                continue
            if path == base:
                return _start_name(root)
            if path.startswith(base + "/"):
                rest = path[len(base) + 1:].split("/")
                return " / ".join([_start_name(root), *rest])
        return path

    def _folder_link(self, label: str, path: str, listing: ui.column,
                     up: bool = False) -> None:
        row = ui.row().classes("items-center gap-2 w-full no-wrap console-source-row "
                               "console-source-row--pick console-source-row--line")
        with row:
            ui.icon("arrow_upward" if up else "folder").classes("shrink-0")
            ui.label(label).classes("console-source-name grow")
            use = None if up else self.folder_use(path)
            if use is not None and path == self.current:
                panel.state(t("word.current"), "on")()
            elif use is not None:
                # Use takes the folder; anywhere else on the row opens it.
                with ui.element("div").classes("shrink-0") \
                        .on("click", js_handler="(e) => e.stopPropagation()"):
                    panel.action(t("console.candidates.use"), use, icon=verbs.ACCEPT)()
        row.on("click", lambda p=path: self._show_folder(listing, p))


class _OneFile(_Sources):
    """A dialog that takes one file, through an uploader held to `accept`."""

    def __init__(self, library: Any, label: str, done: Callable,
                 accept: tuple[str, ...], current: str = "") -> None:
        super().__init__(library, label, done, current)
        self.accept = accept
        self.uploader: Any = None
        self._reading_note: Any = None

    async def took(self, name: str, data: bytes) -> None:
        raise NotImplementedError

    def before(self) -> None:
        self.uploader = ui.upload(on_upload=self._arrived, on_begin_upload=self._reading,
                                  on_rejected=self._refused, auto_upload=True) \
            .classes("hidden")
        if self.accept:
            self.uploader.props(f'accept="{",".join(self.accept)}"')
        self.uploader.on("failed", self._failed, [])
        # Reset by the browser on its own finish. Sent from here, a reset can arrive
        # before the upload's answer and fail an upload that worked.
        self.uploader.on("finish", js_handler=f"() => getElement({self.uploader.id})"
                                              ".$refs.qRef.reset()")

    def zone(self, card: Any) -> None:
        ui.label(t("console.mediasource.drop_file")).classes("console-help")
        panel.action(t("console.mediasource.choose_file"), None, icon=verbs.FROM_FILE,
                     js=f"() => getElement({self.uploader.id}).$refs.qRef.pickFiles()")()
        card.on("drop", self._dropped_wrong, js_handler=_one(self.uploader.id))

    def _takes(self) -> str:
        return t("console.mediasource.takes", label=self.label,
                 extensions=", ".join(self.accept))

    def _reading(self) -> None:
        self._reading_note = ui.notification(t("console.uploads.reading"), spinner=True,
                                             timeout=None)

    def _read(self) -> None:
        if self._reading_note is not None:
            self._reading_note.dismiss()
            self._reading_note = None

    def _failed(self) -> None:
        self._read()
        ui.notify(t("console.uploads.not_work"), type="negative")

    def _refused(self) -> None:
        ui.notify(self._takes(), type="warning")

    def _dropped_wrong(self, event: Any) -> None:
        said = event.args or {}
        if said.get("folder") and self.accept:
            ui.notify(self._takes(), type="warning")
        elif int(said.get("count") or 0) == 0:
            ui.notify(t("console.uploads.nothing_to_upload"), type="warning")
        else:
            ui.notify(t("console.mediasource.one_file"), type="warning")

    async def _arrived(self, event: Any) -> None:
        try:
            data = await event.file.read()
        finally:
            self._read()
        await self.took(event.file.name, data)


class _Slot(_OneFile):
    """A media or asset slot: one file, under the slot's own name."""

    def __init__(self, context: dict[str, Any], kind: str, label: str,
                 done: Callable, target: _Target, current: str = "") -> None:
        super().__init__(context["library"], label, done, target.accept,
                         _on_host(context, current))
        self.target = target
        self.online = target.online
        self.context = context
        self.kind = kind
        self.game_id = context["game_id"]
        self.table_id = context["lens"]
        # Where the picked entry's offers are drawn. Set when the online tab builds,
        # and read by a search result, which redraws them for a different game.
        self.online_body: Any = None
        # The sources this install knows, so an offer can be labeled with a name rather
        # than an id. Read once when the tab opens.
        self._known_sources: list[dict[str, Any]] | None = None
        # Where a file could land, which of those is chosen, and the extension the
        # chosen file will bring - the three things that decide what it gets called.
        self.placements: list[dict[str, Any]] = []
        self.extensions: list[str] = []
        self.placed_at: dict[str, Any] | None = None
        self.chosen_extension = ""
        self.filename_note: Any = None
        self._marks: dict[str, Any] = {}
        self._own_id = ""

    def title(self) -> str:
        return t("console.mediasource.for_this_table" if self.table_id
                 else "console.mediasource.for_this_game", kind=self.label)

    def starts(self) -> list[dict[str, Any]]:
        return self.library.browse_roots(self.game_id)

    def listing(self, path: str) -> dict[str, Any]:
        return self.library.browse(path, self.target.lists)

    def fits(self, item: dict[str, Any]) -> bool:
        return self.target.fits(item)

    def opened(self, above: ui.column) -> None:
        async def start() -> None:
            # Read before anything else: the destination is the decision every tab
            # feeds, and a picker that appears after the first file is chosen has come
            # too late.
            await self.load_placements()
            with above:
                self._destination_row()

        ui.timer(0, start, once=True)

    async def load_placements(self) -> None:
        """Where a file could land here, so it can be chosen rather than inferred."""
        try:
            body = await offload.io(self.target.placements, self.game_id, self.kind)
        except Exception:
            logger.debug("No placements for %s", self.kind, exc_info=True)
            return
        self.placements = list(body.get("placements") or [])
        self.extensions = list(body.get("extensions") or [])
        # The lens preselects rather than decides. Looking at one build is a good guess
        # that art is for that build, and a guess is all it should be.
        wanted = next((item for item in self.placements
                       if item.get("table") == (self.table_id or "")), None)
        self.placed_at = wanted or (self.placements[0] if self.placements else None)

    @property
    def destination(self) -> str:
        """The table id whatever arrives should be named for, "" for the shared name."""
        return str((self.placed_at or {}).get("table") or "")

    def _destination_row(self) -> None:
        """The one decision every way in shares, so it is made once and above them.

        Every option on screen rather than behind a select: there are rarely more than
        a few, and what they differ by is the name the file gets - which a closed
        control shows one of at a time.
        """
        if not self.placements:
            return
        with ui.column().classes("w-full gap-0 console-destination"):
            ui.label(t("console.mediasource.save")).classes("console-card-title")
            for item in self.placements:
                self._placement_choice(item)
            self.filename_note = ui.label("").classes("console-help console-destination-name")
        self._describe_placement()

    def _placement_choice(self, item: dict[str, Any]) -> None:
        """One name the file could be given, under the scope that name carries.

        The chip is the media map's own, so the choice made here is labelled with the
        words the map will use about the file afterwards.
        """
        table = str(item.get("table") or "")
        row = ui.row().classes("items-start gap-2 w-full no-wrap console-placement")
        with row:
            mark = ui.icon("radio_button_unchecked").classes("console-placement-mark")
            media_ownership.badge_for(
                media_ownership.TABLE if table else media_ownership.GAME)
            with ui.column().classes("gap-0 min-w-0 grow"):
                ui.label(str(item.get("base") or "")).classes("console-placement-name")
                going = list(item.get("displaces") or [])
                if going:
                    ui.label(t("console.mediasource.replaces_file_already",
                               count=len(going))) \
                        .classes("console-destination-conflict")
        self._marks[table] = mark
        row.on("click", lambda t=table: self._choose_placement(t))

    def _choose_placement(self, table: str) -> None:
        self.placed_at = next((item for item in self.placements
                               if item.get("table") == (table or "")), self.placed_at)
        self._describe_placement()

    def _describe_placement(self) -> None:
        """Which name is taken, and the one thing the name on screen cannot say."""
        for table, mark in self._marks.items():
            picked = table == self.destination
            mark.props(f'name={"radio_button_checked" if picked else
                                "radio_button_unchecked"}')
            mark.classes(replace="console-placement-mark"
                         + (" console-placement-mark--on" if picked else ""))
        # The extension comes from the file, which on the upload tab is not chosen yet.
        self.filename_note.text = (
            t("console.mediasource.saved",
                    chosen_extension=(self.chosen_extension)) if self.chosen_extension
            else t("console.mediasource.extension_follows_file_choose"))

    def note_extension(self, filename: str) -> None:
        """The picked file's extension, so the name shown is the name it will get."""
        suffix = ("." + filename.rsplit(".", 1)[1].lower()) if "." in filename else ""
        if suffix != self.chosen_extension:
            self.chosen_extension = suffix
            if self.filename_note is not None:
                self._describe_placement()

    async def finish(self, message: str) -> None:
        await super().finish(self.said_where(message))

    def said_where(self, message: str) -> str:
        """Say where, including when "where" is not what the panel behind is showing.

        A file saved for one table while the shared media is in view changes nothing
        on screen. The write worked and the panel is right; without a word about it
        the pair reads as a failure.
        """
        chosen = self.placed_at or {}
        where = (t("console.mediasource.for",
                   table=_trimmed_stem(str(chosen.get("label") or "")))
                 if self.destination else t("console.mediasource.every_table_game"))
        if not self._in_view():
            where = t("console.mediasource.not_what_view_showing", where=where)
        return t("console.mediasource.saved_where", message=message, where=where)

    def _in_view(self) -> bool:
        """Whether the panel behind shows what was just saved. A table missing from the
        placements has no name apart from the folder's."""
        if self.destination == (self.table_id or ""):
            return True
        own = next((item for item in self.placements
                    if item.get("table") == self.table_id), None)
        return not self.destination and not (own or {}).get("displaces")

    async def confirmed(self, filename: str) -> bool:
        """Ask before a write that deletes something, naming what goes.

        Asked again here rather than trusted from the list: the dropdown's count was
        read when the dialog opened, and the answer that matters is the one at the
        moment of the write.
        """
        self.note_extension(filename)
        try:
            going = await offload.io(self.target.displaced, self.game_id,
                                       self.destination, self.kind, filename)
        except Exception as exc:
            ui.notify(t("console.mediasource.could_not_check_slot"), caption=why(exc),
                      type="negative")
            return False
        return not going or await confirm_replace(self.label, going)

    def candidate(self, src: str, name: str, meta: str, tag: str,
                  take: Callable, current: bool = False) -> None:
        """A candidate row carrying what this dialog knows: how to draw a file of the
        kind being replaced."""
        candidates.row(src, name, meta, tag, take, family=self.target.family,
                       line=not self.target.family, current=current)

    async def took(self, name: str, data: bytes) -> None:
        if not await self.confirmed(name):
            return
        try:
            await run.io_bound(self.target.place, self.game_id,
                               self.destination, self.kind, name, data)
        except Exception as exc:
            ui.notify(t("console.mediasource.could_not_place"), caption=why(exc),
                      type="negative")
            return
        await self.finish(t("console.mediasource.label_saved", label=self.label))

    def file_row(self, item: dict[str, Any]) -> None:
        async def take() -> None:
            if not await self.confirmed(item["name"]):
                return
            try:
                await run.io_bound(self.target.bring, self.game_id,
                                   self.destination, self.kind, item["path"])
            except Exception as exc:
                ui.notify(t("console.mediasource.could_not_bring"), caption=why(exc),
                          type="negative")
                return
            await self.finish(t("console.mediasource.label_saved", label=self.label))

        current = item["path"] == self.current
        self.candidate(self.library.browsed_file_url(item["path"]), item["name"],
                       _size(item.get("size_bytes")),
                       "" if current else self._in_use(item["name"]), take, current)

    def _in_use(self, name: str) -> str:
        """Whether this file is already serving one of the game's slots.

        In a game's own folder most files are already somebody's, and the interesting
        ones are the strays. Said per row rather than by hiding the rest, so the folder
        still looks like the folder.
        """
        for kind, entry in (self.context.get("media") or {}).items():
            if entry.get("file") == name:
                return t("console.mediasource.already", kind=media_label_map().get(kind, kind))
        return ""

    # --- from the online catalogs --------------------------------------------

    async def online_tab(self, body: ui.column) -> None:
        """What every enabled catalog has, for this game or for any other entry.

        Any other entry because the match is not always right and not always there: a
        mod, a table the identifier missed, or a game whose art someone simply prefers.
        Locking this to the game's own id would make the common repair impossible.

        What is on offer comes first and the search under it, because borrowing another
        game's art is the rare errand and the files are what the tab is for. The search
        opens holding this game's name, which is both a starting point to edit and the
        answer to what the list above is showing.
        """
        body.clear()
        game = self.context["game"]
        self._own_id = str(game.get("vps_id") or "")
        with body:
            self.online_head = ui.label("").classes("console-card-title")
            self.online_body = ui.column().classes("w-full gap-1 console-source-offers")
            ui.label(t("console.mediasource.search_another_game")) \
                .classes("console-card-title console-source-under")
            search = ui.input(value=str(game.get("name") or "")) \
                .props("outlined dense clearable").classes("w-full")
            results = ui.column().classes("w-full gap-1 console-source-found")
        search.on("keydown.enter",
                  lambda: self._search_games(results, search.value or ""))
        # Read for the names, which label the rows. Not announced up front - every row
        # says where it came from, so a list of the same names above it is furniture.
        try:
            self._known_sources = await offload.io(self.library.media_sources)
        except Exception:
            self._known_sources = []
        await self._show_offers(self.online_body, self._own_id,
                                game.get("name") or t("console.mediasource.game_2"))

    def _searched(self) -> str:
        """Where we looked, for the one case that needs it: nothing came back.

        An empty result with no "where" reads as the feature being broken rather than
        as the catalogs not having it.
        """
        asked = [item["name"] for item in (self._known_sources or [])
                 if item.get("enabled")]
        return ", ".join(asked)

    async def _search_games(self, results: ui.column, query: str) -> None:
        results.clear()
        if not query.strip():
            return
        try:
            found = await offload.io(self.library.search_vps, query.strip())
        except Exception as exc:
            with results:
                panel.line(t("console.mediasource.could_not_search"), hint=why(exc))
            return
        with results:
            if not found:
                ui.label(t("console.mediasource.no_game_name_vpsdb")).classes("console-help")
                return
            for item in found:
                self._game_choice(item)

    def _game_choice(self, item: dict[str, Any]) -> None:
        """One machine the search found, with its photograph where VPS has one.

        Art rather than a line of text because this list is answering "which machine do
        I mean", and the photograph settles that faster than a name that differs from
        the one you know it by.
        """
        made = game_tables.made(item)
        candidates.choice(item.get("img_url") or "",
                          str(item.get("name") or ""), made,
                          lambda i=item: self._show_offers(
                              self.online_body, i.get("vps_id") or "",
                              i.get("name") or t("console.mediasource.game")),
                          glyph="videogame_asset")

    async def _show_offers(self, body: ui.column, vps_id: str, name: str) -> None:
        """The files one game is offered, under a heading that names that game.

        Named because this list and the search above it drift apart: you search for
        something else, and the files below go on being the ones you were already
        looking at, with nothing to say which game they belong to.
        """
        body.clear()
        # Named only when it is not this game's own: a heading that says the obvious on
        # every visit stops being read by the time it matters.
        self.online_head.text = (t("console.mediasource.found_online")
                                 if vps_id == self._own_id
                                 else t("console.mediasource.found_online_for", name=name))
        if not vps_id:
            with body:
                ui.label(t("console.mediasource.game_no_vps_id")) \
                    .classes("console-help")
            return
        try:
            found = await offload.io(self.library.media_offers, vps_id, self.kind)
        except Exception as exc:
            with body:
                panel.line(t("console.mediasource.could_not_reach_catalogs"), hint=why(exc))
            return
        with body:
            if not found:
                where = self._searched()
                ui.label(t("console.mediasource.nothing", where=(where)) if where else
                         t("console.mediasource.no_online_sources_switched")).classes("console-help")
                return
            named = {item["id"]: item["name"]
                     for item in (self._known_sources or [])}
            for offer in found:
                self._offer_row(offer, named.get(offer["source"], offer["source"]),
                                vps_id)

    def _offer_row(self, offer: dict[str, Any], source_name: str,
                   vps_id: str) -> None:
        size = str(offer.get("size") or "")

        async def take() -> None:
            if not await self.confirmed(str(offer.get("name") or "")):
                return
            # Held: an ongoing notification never times out, so one nothing dismisses
            # outlives the answer it was waiting for.
            fetching = ui.notification(t("console.mediasource.fetching",
                    source_name=(source_name)),
                                       spinner=True, timeout=None)
            try:
                await run.io_bound(self.library.fetch_media, self.game_id,
                                   self.destination, self.kind, offer["source"],
                                   vps_id, size)
            except Exception as exc:
                ui.notify(t("console.mediasource.could_not_fetch"), caption=why(exc),
                          type="negative")
                return
            finally:
                fetching.dismiss()
            await self.finish(t("console.mediasource.saved_2", label=(self.label),
                    source_name=(source_name)))

        # The source is the first thing on the row, because with several of them the
        # question "where is this from" comes before "is it any good".
        meta = (t("console.mediasource.source_and_size", source_name=source_name,
                  size=t(SIZE_NAMES[size]) if size in SIZE_NAMES else size)
                if size else source_name)
        self.candidate(offer.get("url") or "", str(offer.get("name") or ""),
                       meta, "", take)


class _Folder(_Sources):
    """A kind that arrives as many files - a PUP pack, a color set, a sound bank, music."""

    def __init__(self, context: dict[str, Any], kind: str, label: str,
                 done: Callable, current: str = "") -> None:
        super().__init__(context["library"], label, done, _on_host(context, current))
        self.kind = kind
        self.game_id = context["game_id"]
        self.game_dir = str(context["game"].get("folder") or "")
        specs = specs_named(kind)
        self.extensions = {extension for spec in specs for extension in spec.extensions}
        self.glyph = specs[0].icon
        # The kind an import is held to, or "" for whatever the drop brought.
        self.narrows_to = kind
        self.adds_table = False
        self._busy = False

    def title(self) -> str:
        return t("console.mediasource.for_this_game", kind=self.label)

    def starts(self) -> list[dict[str, Any]]:
        return self.library.browse_roots(self.game_id)

    def listing(self, path: str) -> dict[str, Any]:
        return self.library.browse(path, self.kind, True)

    def fits(self, item: dict[str, Any]) -> bool:
        return _suffix(item) in ARCHIVE_EXTENSIONS or _suffix(item) in self.extensions

    def folder_use(self, path: str) -> Callable | None:
        return lambda: self._take(path)

    def file_row(self, item: dict[str, Any]) -> None:
        archive = _suffix(item) in ARCHIVE_EXTENSIONS
        candidates.row("", item["name"], _size(item.get("size_bytes")), "",
                       lambda: self._take(item["path"]), family="",
                       glyph="folder_zip" if archive else self.glyph, line=True,
                       current=item["path"] == self.current)

    def zone(self, card: Any) -> None:
        heard = uploads.listener(self.arrived)
        ui.label(t("console.mediasource.drop_files")).classes("console-help")
        with ui.row().classes("items-center justify-center gap-2"):
            panel.action(t("console.mediasource.choose_files"), heard,
                         icon=verbs.FROM_FILE,
                         js="() => window.__consoleChoose(false, emit)")()
            panel.action(t("console.mediasource.choose_folder"), heard,
                         icon=verbs.FROM_FOLDER,
                         js="() => window.__consoleChoose(true, emit)")()
        card.on("drop", heard, js_handler=_MANY)

    async def arrived(self, drop: uploads.Drop) -> None:
        await self._import(drop.upload_id, drop.name, drop.count)

    async def _take(self, path: str) -> None:
        try:
            upload_id = await offload.io(self.library.upload_from_path, path)
        except Exception as exc:  # noqa: BLE001
            ui.notify(t("console.uploads.could_not_read"), caption=why(exc), type="negative")
            return
        await self._import(upload_id, PurePosixPath(path).name)

    async def _import(self, upload_id: str, source: str, file_count: int = 0) -> None:
        if self._busy:
            ui.notify(t("console.uploads.finish_one_already_open"), type="warning")
            await run.io_bound(self.library.abort_upload, upload_id)
            return
        self._busy = True
        try:
            analysis = await self.analysis(upload_id)
            if analysis is not None:
                await uploads.confirmed_import(
                    self.library, upload_id, analysis, source=source,
                    file_count=file_count, on_done=self._imported, game_id=self.game_id,
                    game_dir=self.game_dir, asset_kind=self.narrows_to,
                    add_table=self.adds_table)
        finally:
            self._busy = False

    async def analysis(self, upload_id: str) -> dict[str, Any] | None:
        return await uploads.analyzed(self.library, upload_id)

    async def _imported(self) -> None:
        if self.dialog is not None:
            self.dialog.close()
        await self.done()


class _Notes(_Folder):
    def __init__(self, context: dict[str, Any], label: str, done: Callable) -> None:
        super().__init__(context, "readme", label, done)

    def listing(self, path: str) -> dict[str, Any]:
        return self.library.browse(path)

    def fits(self, item: dict[str, Any]) -> bool:
        return item.get("family") == "doc"

    def folder_use(self, path: str) -> Callable | None:
        return None

    async def analysis(self, upload_id: str) -> dict[str, Any] | None:
        return {}

    def zone(self, card: Any) -> None:
        heard = uploads.listener(self.arrived)
        ui.label(t("console.mediasource.drop_file")).classes("console-help")
        panel.action(t("console.mediasource.choose_file"), heard, icon=verbs.FROM_FILE,
                     js="() => window.__consoleChoose(false, emit)")()
        card.on("drop", heard, js_handler=_MANY)


class _Table(_Folder):
    """A table for a game: taken from the device as a copy or where it is, or an ID its
    launcher starts it from."""

    keyed = True

    def __init__(self, context: dict[str, Any], done: Callable) -> None:
        super().__init__(context, "table", t("asset.kind.table.label"), done)
        self.game_name = str(context["game"].get("name") or "")
        self.narrows_to = ""
        self.adds_table = True
        self.copies = True

    def title(self) -> str:
        return t("console.mediasource.add_table_to", name=self.game_name)

    def starts(self) -> list[dict[str, Any]]:
        return [root for root in self.library.browse_roots(self.game_id)
                if root.get("source") != "game"]

    def listing(self, path: str) -> dict[str, Any]:
        return self.library.browse(path, self.kind)

    def fits(self, item: dict[str, Any]) -> bool:
        inside = self.game_dir and str(item.get("path") or "").startswith(
            self.game_dir.rstrip("/") + "/")
        return _suffix(item) in self.extensions and not inside

    def folder_use(self, path: str) -> Callable | None:
        return None

    def file_row(self, item: dict[str, Any]) -> None:
        candidates.row("", item["name"], _size(item.get("size_bytes")), "",
                       lambda: self._chosen(item["path"]), family="", glyph=self.glyph,
                       line=True)

    def zone(self, card: Any) -> None:
        heard = uploads.listener(self.arrived)
        ui.label(t("console.mediasource.drop_table")).classes("console-help")
        ui.label(t("console.mediasource.drop_table.help")).classes("console-help")
        with ui.row().classes("items-center justify-center gap-2"):
            panel.action(t("console.mediasource.choose_files"), heard,
                         icon=verbs.FROM_FILE,
                         js="() => window.__consoleChoose(false, emit)")()
            panel.action(t("console.mediasource.choose_folder"), heard,
                         icon=verbs.FROM_FOLDER,
                         js="() => window.__consoleChoose(true, emit)")()
        card.on("drop", heard, js_handler=_MANY)

    def takes_drops(self, element: Any) -> None:
        """Make `element` a place a table is dropped on to join this game."""
        element._props[uploads.OWN_DROP] = ""
        element.on("dragover", js_handler=_LIGHT)
        element.on("dragleave", js_handler=_DIM)
        element.on("drop", uploads.listener(self.arrived), js_handler=_MANY)

    async def host_tab(self, body: ui.column) -> None:
        body.clear()
        with body:
            self._ways()
            listed = ui.column().classes("w-full gap-2")
            with ui.row().classes("items-start gap-2 w-full no-wrap"):
                typed = panel.path_field(placeholder=t("console.workbench.path_table_file"),
                                         wants="file", width="grow min-w-0")
                panel.action(t("word.add"), lambda: self._typed(typed), icon=verbs.ADD)()
            typed.on("keydown.enter", lambda: self._typed(typed))
        await super().host_tab(listed)

    def _ways(self) -> None:
        """Copy or reference, as radios with their descriptions: the descriptions are
        what the choice is made on."""
        marks: dict[bool, Any] = {}

        def pick(copies: bool) -> None:
            self.copies = copies
            for key, mark in marks.items():
                mark.props(f'name={"radio_button_checked" if key == copies else
                                    "radio_button_unchecked"}')
                mark.classes(replace="console-placement-mark"
                             + (" console-placement-mark--on" if key == copies else ""))

        with ui.column().classes("w-full gap-0 console-destination"):
            for copies, name, help_ in (
                    (True, t("console.mediasource.copy_in"),
                     t("console.mediasource.copy_in.help")),
                    (False, t("console.mediasource.use_where"),
                     t("console.mediasource.use_where.help"))):
                row = ui.row().classes("items-start gap-2 w-full no-wrap console-placement")
                with row:
                    marks[copies] = ui.icon("radio_button_unchecked") \
                        .classes("console-placement-mark")
                    with ui.column().classes("gap-0 min-w-0 grow"):
                        ui.label(name).classes("console-placement-name")
                        ui.label(help_).classes("console-help")
                row.on("click", lambda c=copies: pick(c))
        pick(self.copies)

    async def _typed(self, typed: Any) -> None:
        said = str(typed.value or "").strip()
        if said:
            await self._chosen(said)

    async def _chosen(self, path: str) -> None:
        adds = (self.library.import_table_file if self.copies
                else self.library.add_referenced_table)
        try:
            await offload.io(adds, self.game_id, path)
        except Exception as exc:  # noqa: BLE001
            ui.notify(t("said.could_not_add_it"), caption=why(exc), type="negative")
            return
        await self._imported()

    async def keyed_tab(self, body: ui.column) -> None:
        body.clear()
        try:
            found = await offload.io(self.library.launchers)
            apps = await offload.io(self.library.launch_apps)
        except Exception as exc:  # noqa: BLE001
            with body:
                panel.line(t("console.launchers.could_not_read_launchers"), hint=why(exc))
            return
        takes_ids = {str(app.get("id") or "") for app in apps if app.get("accepts_keys")}
        offered = [one for one in found.get("launchers") or []
                   if str(one.get("app") or "") in takes_ids and one.get("enabled", True)]
        defaults = dict(found.get("defaults") or {})
        with body:
            ui.label(t("console.mediasource.without_file.help")).classes("console-help")
            if not offered:
                ui.label(t("console.mediasource.no_launcher_takes_id")) \
                    .classes("console-help")
                with ui.row().classes("items-center gap-2 w-full console-slot-actions"):
                    panel.action(t("console.mediasource.add_launcher"),
                                 lambda: self._add_launcher(sorted(takes_ids)),
                                 icon=verbs.ADD)()
                return
            first = next((one for one in offered
                          if defaults.get(one.get("app")) == one.get("launcher_id")),
                         offered[0])
            chosen = {"launcher": first}
            by_id = {str(one["launcher_id"]): one for one in offered}
            held: dict[str, Any] = {}

            def draw_id() -> None:
                held["typed"] = frame.field(placeholder=t("console.mediasource.id_example"))

            rows: list[tuple[Any, Any]] = []
            if len(offered) > 1:
                rows.append((t("console.workbench.launcher_2"), panel.select(
                    {key: str(one.get("display_name") or key) for key, one in by_id.items()},
                    str(first["launcher_id"]),
                    lambda event: chosen.update(launcher=by_id[str(event.value)]))))
            rows.append((t("word.id"), draw_id))
            panel.facts(ui, rows)

            async def add() -> None:
                said = str(held["typed"].value or "").strip()
                if not said:
                    held["typed"].props["error"] = True
                    held["typed"].props["error-message"] = \
                        t("console.mediasource.give_it_an_id")
                    held["typed"].update()
                    return
                launcher = chosen["launcher"]
                app = str(launcher.get("app") or "")
                try:
                    made = await offload.io(self.library.add_keyed_table, self.game_id,
                                            app, said)
                    if defaults.get(app) != launcher.get("launcher_id"):
                        await offload.io(self.library.assign_launcher,
                                         str(made.get("id") or ""),
                                         str(launcher["launcher_id"]))
                except Exception as exc:  # noqa: BLE001
                    ui.notify(t("said.could_not_add_it"), caption=why(exc), type="negative")
                    return
                await self._imported()

            with ui.row().classes("items-center gap-2 w-full console-slot-actions"):
                panel.action(t("word.add"), add, icon=verbs.ADD)()
            held["typed"].on("keydown.enter", add)

    async def _add_launcher(self, apps: list[str]) -> None:
        """A launcher for the program that takes an ID, opened on the Launchers page to
        be named and pointed at its program."""
        from common.games import launchers as model

        wanted = "/console?" + deeplink.query({"view": "launchers"})
        if len(apps) == 1:
            made = model.mint_launcher_id()
            name = next((str(one.get("name") or "") for one in
                         await offload.io(self.library.launch_apps)
                         if one.get("id") == apps[0]), apps[0])
            try:
                await offload.io(self.library.put_launcher, made,
                                 {"app": apps[0], "display_name": name, "enabled": True,
                                  "settings": {}})
            except Exception as exc:  # noqa: BLE001
                ui.notify(t("said.could_not_add_it"), caption=why(exc), type="negative")
                return
            wanted = "/console?" + deeplink.query({"view": "launchers", "launcher": made})
        self.dialog.close()
        ui.navigate.to(wanted)


class _Image(_OneFile):
    """A collection's picture."""

    games = True

    def __init__(self, library: Any, name: str, label: str, done: Callable) -> None:
        super().__init__(library, label, done, IMAGE_FAMILY)
        self.name = name

    def title(self) -> str:
        return t("console.mediasource.for_this_collection", kind=self.label)

    def starts(self) -> list[dict[str, Any]]:
        return self.library.browse_roots()

    def fits(self, item: dict[str, Any]) -> bool:
        return item.get("family") == "image"

    def file_row(self, item: dict[str, Any]) -> None:
        async def take() -> None:
            try:
                data = await offload.io(self.library.browsed_file, item["path"])
            except Exception as exc:  # noqa: BLE001
                ui.notify(t("console.mediasource.could_not_use_image"), caption=why(exc),
                          type="negative")
                return
            await self.took(item["name"], data)

        candidates.row(self.library.browsed_file_url(item["path"]), item["name"],
                       _size(item.get("size_bytes")), "", take)

    async def games_tab(self, body: ui.column) -> None:
        body.clear()
        try:
            entries = await offload.io(self.library.collection_entries, self.name)
        except Exception as exc:  # noqa: BLE001
            with body:
                panel.line(t("console.mediasource.could_not_read_its_games"), hint=why(exc))
            return
        wheeled = [entry for entry in entries if "wheel" in (entry.get("media") or [])]
        with body:
            if not wheeled:
                ui.label(t("console.mediasource.no_game_wheels")).classes("console-help")
                return
            find = None
            if len(wheeled) > _FIND_FROM:
                with ui.element("div").classes("w-full"):
                    find = frame.field(placeholder=t("console.mediasource.find_game"))
            listing = ui.column().classes("w-full gap-1 console-source-list")

        def draw() -> None:
            typed = str(find.value or "").strip().casefold() if find is not None else ""
            found = [entry for entry in wheeled
                     if typed in str((entry.get("game") or {}).get("name") or "").casefold()]
            listing.clear()
            with listing:
                if not found:
                    ui.label(t("console.mediasource.no_game_by_name")).classes("console-help")
                for entry in found:
                    self._wheel_row(entry)

        if find is not None:
            find.on_value_change(draw)
        draw()

    def _wheel_row(self, entry: dict[str, Any]) -> None:
        game = entry.get("game") or {}
        game_id = str(game.get("id") or "")
        table_id = str((entry.get("table") or {}).get("id") or "")
        name = str(game.get("name") or "")

        async def take() -> None:
            try:
                data, served = await offload.io(self.library.media_file, game_id, table_id,
                                                "wheel")
            except Exception as exc:  # noqa: BLE001
                ui.notify(t("console.mediasource.could_not_use_image"), caption=why(exc),
                          type="negative")
                return
            await self.took(_named_for(name, served), data)

        candidates.row(art.media(game_id, "wheel", table_id, size=art.CELL), name,
                       game_tables.made(game), "", take,
                       peek=art.media(game_id, "wheel", table_id, size=art.PANEL))

    async def took(self, name: str, data: bytes) -> None:
        try:
            await offload.io(self.library.set_collection_image, self.name, name, data)
        except Exception as exc:  # noqa: BLE001
            ui.notify(t("console.mediasource.could_not_use_image"), caption=why(exc),
                      type="negative")
            return
        await self.finish(t("console.mediasource.label_saved", label=self.label))


def _on_host(context: dict[str, Any], path: str) -> str:
    """A path in the game's folder, as the host tab lists it."""
    folder = str(context["game"].get("folder") or "")
    return str(PurePosixPath(folder) / path) if folder and path else ""


def _named_for(name: str, served: str) -> str:
    return name + (mimetypes.guess_extension(served.split(";")[0].strip()) or "")


def _trimmed_stem(label: str) -> str:
    """The file's name without its extension, short enough to read."""
    stem = label[:-4] if label.lower().endswith(".vpx") else label
    return stem if len(stem) <= 40 else "\u2026" + stem[-39:]


def _start_name(root: dict[str, Any]) -> str:
    """What to call a starting point. The game's own folder is not named after the
    folder, because the folder's name is the one thing already on screen above it."""
    return (t("console.mediasource.game_s_folder") if root.get("source") == "game"
            else str(root.get("name") or root.get("path") or ""))


def open_sources(context: dict[str, Any], kind: str, label: str,
                 done: Callable, current: str = "") -> None:
    """Open the ways to fill this slot. Returns as soon as the dialog is up.

    `current` is what fills it now, as a path in the game's folder.
    """
    _Slot(context, kind, label, done, _media(context["library"], kind), current).open()


def open_asset_sources(context: dict[str, Any], kind: str, label: str,
                       done: Callable, current: str = "") -> None:
    _Slot(context, kind, label, done, _asset(context["library"], kind), current).open()


def open_folder_sources(context: dict[str, Any], kind: str, label: str,
                        done: Callable, current: str = "") -> None:
    _Folder(context, kind, label, done, current).open()


def open_notes_sources(context: dict[str, Any], label: str, done: Callable) -> None:
    _Notes(context, label, done).open()


def open_table_sources(context: dict[str, Any], done: Callable) -> None:
    """The ways a table joins this game. `done` runs after any of them adds one."""
    _Table(context, done).open()


def take_table_drops(element: Any, context: dict[str, Any], done: Callable) -> None:
    """A drop on `element` goes to this game the way the Upload tab's does."""
    _Table(context, done).takes_drops(element)


def open_image_sources(library: Any, name: str, label: str, done: Callable) -> None:
    _Image(library, name, label, done).open()
