"""Where a slot's file comes from, in one place.

Three ways in, because there are three: a file on the computer you are looking at this
from, a file already on the machine VPinFE runs on, and the catalog. Anything already
on a disk here is one browser rather than a tab apiece - this game's folder, another
game's, and a folder of downloads are the same act, and splitting them made three
answers to one question.

Every route ends the same way: the file lands under the slot's name at the tier the
lens is on, and whatever it displaced was named before it went.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from nicegui import run, ui

from common import labels
from common.media_specs import media_family, media_label_map
from hubui import candidates, confirm, media_ownership

logger = logging.getLogger("vpinfe.hubui.mediasource")

# Enough of a list to scroll rather than to page. A folder of artwork is tens of files,
# not thousands, and a picker with pages in it is a database browser.
_LIST_MAX = 60


def _size(count: int | None) -> str:
    """A file size someone can read at a glance. Powers of 1024, one decimal."""
    if not count:
        return ""
    size = float(count)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return ""


async def confirm_replace(label: str, going: list[str]) -> bool:
    """Name what a write would replace, and wait for a yes.

    The files are listed rather than counted because the surprising case is the one a
    count hides: a whole family goes at this tier, so a .mp4 arriving over a .png takes
    the .png with it and the user never named that file.
    """
    return await confirm.ask(f"Replace the {label.lower()} that is there?",
                             detail="Replaced files are deleted, not kept.",
                             lines=going, confirm="Replace")


class _Sources:
    """The dialog's state: which slot is being filled, and how to finish."""

    def __init__(self, context: dict[str, Any], kind: str, label: str,
                 done: Callable) -> None:
        self.context = context
        self.kind = kind
        self.label = label
        self.done = done
        self.library = context["library"]
        self.game_id = context["game_id"]
        self.table_id = context["lens"]
        self.dialog: Any = None
        # Where the picked entry's offers are drawn. Set when the online tab builds,
        # and read by a search result, which redraws them for a different game.
        self.online_body: Any = None
        # The sources this hub knows, so an offer can be labeled with a name rather
        # than an id. Read once when the tab opens.
        self._known_sources: list[dict[str, Any]] | None = None
        # Filled when the browser loads; the trail above a listing is written against
        # them, so a folder is named from its start rather than from "/".
        self.browse_roots: list[dict[str, Any]] = []
        # Where a file could land, which of those is chosen, and the extension the
        # chosen file will bring - the three things that decide what it gets called.
        self.placements: list[dict[str, Any]] = []
        self.extensions: list[str] = []
        self.placed_at: dict[str, Any] | None = None
        self.chosen_extension = ""
        self.filename_note: Any = None
        self._marks: dict[str, Any] = {}
        self._own_id = ""

    async def load_placements(self) -> None:
        """Where a file could land here, so it can be chosen rather than inferred."""
        try:
            body = await run.io_bound(self.library.placements, self.game_id, self.kind)
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
        with ui.column().classes("w-full gap-0 hub-destination"):
            ui.label("Save it as").classes("hub-card-title")
            for item in self.placements:
                self._placement_choice(item)
            self.filename_note = ui.label("").classes("hub-help hub-destination-name")
        self._describe_placement()

    def _placement_choice(self, item: dict[str, Any]) -> None:
        """One name the file could be given, under the scope that name carries.

        The chip is the media map's own, so the choice made here is labelled with the
        words the map will use about the file afterwards.
        """
        table = str(item.get("table") or "")
        row = ui.row().classes("items-start gap-2 w-full no-wrap hub-placement")
        with row:
            mark = ui.icon("radio_button_unchecked").classes("hub-placement-mark")
            media_ownership.badge_for(
                media_ownership.TABLE if table else media_ownership.GAME)
            with ui.column().classes("gap-0 min-w-0 grow"):
                ui.label(str(item.get("base") or "")).classes("hub-placement-name")
                going = list(item.get("displaces") or [])
                if going:
                    ui.label(f"Replaces {len(going)} file"
                             f"{'s' if len(going) != 1 else ''} already there") \
                        .classes("hub-destination-conflict")
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
            mark.classes(replace="hub-placement-mark"
                         + (" hub-placement-mark--on" if picked else ""))
        # The extension comes from the file, which on the upload tab is not chosen yet.
        self.filename_note.text = (
            f"Saved as {self.chosen_extension}" if self.chosen_extension
            else "The extension follows the file you choose")

    def note_extension(self, filename: str) -> None:
        """The picked file's extension, so the name shown is the name it will get."""
        suffix = ("." + filename.rsplit(".", 1)[1].lower()) if "." in filename else ""
        if suffix != self.chosen_extension:
            self.chosen_extension = suffix
            if self.filename_note is not None:
                self._describe_placement()

    async def finish(self, message: str) -> None:
        """Close, say what happened, and say where - including when "where" is not
        what the panel behind is showing.

        A file saved for one build while the shared media is in view changes nothing
        on screen. The write worked and the panel is right; without a word about it
        the pair reads as a failure.
        """
        self.dialog.close()
        chosen = self.placed_at or {}
        where = ("for every table in this game" if not self.destination
                 else f"for {_placement_label(chosen).removeprefix('Only ')}")
        unseen = ("" if self.destination == (self.table_id or "") else
                  " - not what this view is showing")
        ui.notify(f"{message} {where}{unseen}", type="positive")
        await self.done()

    async def confirmed(self, filename: str) -> bool:
        """Ask before a write that deletes something, naming what goes.

        Asked again here rather than trusted from the list: the dropdown's count was
        read when the dialog opened, and the answer that matters is the one at the
        moment of the write.
        """
        self.note_extension(filename)
        try:
            going = await run.io_bound(self.library.displaced_by, self.game_id,
                                       self.destination, self.kind, filename)
        except Exception as exc:
            ui.notify(f"Could not check that slot: {exc}", type="negative")
            return False
        return not going or await confirm_replace(self.label, going)

    def candidate(self, src: str, name: str, meta: str, tag: str,
                  take: Callable) -> None:
        """A candidate row carrying what this dialog knows: how to draw a file of the
        kind being replaced."""
        candidates.row(src, name, meta, tag, take,
                       family=media_family(self.kind))

    # --- from the computer you are looking at this from ----------------------

    def upload_tab(self) -> None:
        ui.label("Choose a file on the computer you are looking at this from") \
            .classes("hub-help")

        async def arrived(event: Any) -> None:
            name = event.file.name
            self.note_extension(name)
            if not await self.confirmed(name):
                return
            data = await event.file.read()
            try:
                await run.io_bound(self.library.place_media, self.game_id,
                                   self.destination, self.kind, name, data)
            except Exception as exc:
                ui.notify(f"Could not place it: {exc}", type="negative")
                return
            await self.finish(f"{self.label} saved")

        ui.upload(on_upload=arrived, auto_upload=True, max_files=1,
                  label="Drop a file here, or browse") \
            .props("flat").classes("w-full hub-source-upload")

    # --- from anywhere on the machine VPinFE runs on -------------------------

    async def browse_tab(self, body: ui.column) -> None:
        body.clear()
        try:
            starts = await run.io_bound(self.library.browse_roots, self.game_id)
        except Exception as exc:
            with body:
                ui.label(f"Could not read this machine: {exc}").classes("hub-help")
            return
        self.browse_roots = starts
        with body:
            if not starts:
                ui.label("No folders are browsable. The game library counts as one, and "
                         "more can be listed under Browsable Media Folders in settings.") \
                    .classes("hub-help")
                return
            ui.label("Files already on the machine VPinFE runs on") \
                .classes("hub-help")
            # The control before what it controls: built the other way round, the
            # picker sits under the folder it chose.
            picker = (ui.select({item["path"]: _start_name(item) for item in starts},
                                value=starts[0]["path"], label="Start from")
                      .props("outlined dense").classes("w-full")
                      if len(starts) > 1 else None)
            listing = ui.column().classes("w-full gap-1")
            if picker is not None:
                picker.on_value_change(lambda event: self._show_folder(listing,
                                                                      event.value))
            await self._show_folder(listing, starts[0]["path"])

    async def _show_folder(self, listing: ui.column, path: str) -> None:
        listing.clear()
        try:
            here = await run.io_bound(self.library.browse, path)
        except Exception as exc:
            with listing:
                ui.label(f"Could not read that folder: {exc}").classes("hub-help")
            return
        family = media_family(self.kind)
        with listing:
            # Named from the start it was reached through rather than as an absolute
            # path: the path on a cabinet is long, and the tail is the part that says
            # where you are.
            ui.label(self._trail(here["path"])).classes("hub-help hub-source-trail")
            with ui.column().classes("w-full gap-1 hub-source-list"):
                if here.get("parent"):
                    self._folder_link("..", here["parent"], listing, up=True)
                shown = 0
                for item in here["entries"][:_LIST_MAX]:
                    if item["kind"] == "folder":
                        self._folder_link(item["name"], item["path"], listing)
                    elif item["family"] == family:
                        self._file_row(item)
                    else:
                        continue
                    shown += 1
                if not shown:
                    ui.label(f"Nothing here to use as {self.label.lower()}") \
                        .classes("hub-help")
                elif len(here["entries"]) > _LIST_MAX:
                    ui.label(f"{len(here['entries']) - _LIST_MAX} more not shown") \
                        .classes("hub-help")

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
        row = ui.row().classes("items-center gap-2 w-full no-wrap hub-source-row "
                               "hub-source-row--pick hub-source-row--folder")
        with row:
            ui.icon("arrow_upward" if up else "folder").classes("shrink-0")
            ui.label(label).classes("hub-source-name")
        row.on("click", lambda p=path: self._show_folder(listing, p))

    def _file_row(self, item: dict[str, Any]) -> None:
        async def take() -> None:
            if not await self.confirmed(item["name"]):
                return
            try:
                await run.io_bound(self.library.import_media, self.game_id,
                                   self.destination, self.kind, item["path"])
            except Exception as exc:
                ui.notify(f"Could not bring it in: {exc}", type="negative")
                return
            await self.finish(f"{self.label} saved")

        self.candidate(self.library.browsed_file_url(item["path"]), item["name"],
                       _size(item.get("size_bytes")), self._in_use(item["name"]), take)

    def _in_use(self, name: str) -> str:
        """Whether this file is already serving one of the game's slots.

        In a game's own folder most files are already somebody's, and the interesting
        ones are the strays. Said per row rather than by hiding the rest, so the folder
        still looks like the folder.
        """
        for kind, entry in (self.context.get("media") or {}).items():
            if entry.get("file") == name:
                return f"already the {media_label_map().get(kind, kind).lower()}"
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
            self.online_head = ui.label("").classes("hub-card-title")
            self.online_body = ui.column().classes("w-full gap-1 hub-source-offers")
            ui.label("Search another game").classes("hub-card-title hub-source-under")
            search = ui.input(value=str(game.get("name") or "")) \
                .props("outlined dense clearable").classes("w-full")
            results = ui.column().classes("w-full gap-1 hub-source-found")
        search.on("keydown.enter",
                  lambda: self._search_games(results, search.value or ""))
        # Read for the names, which label the rows. Not announced up front - every row
        # says where it came from, so a list of the same names above it is furniture.
        try:
            self._known_sources = await run.io_bound(self.library.media_sources)
        except Exception:
            self._known_sources = []
        await self._show_offers(self.online_body, self._own_id,
                                game.get("name") or "this game")

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
            found = await run.io_bound(self.library.search_vps, query.strip())
        except Exception as exc:
            with results:
                ui.label(f"Could not search: {exc}").classes("hub-help")
            return
        with results:
            if not found:
                ui.label("No game by that name in VPSdb").classes("hub-help")
                return
            for item in found:
                self._game_choice(item)

    def _game_choice(self, item: dict[str, Any]) -> None:
        """One machine the search found, with its photograph where VPS has one.

        Art rather than a line of text because this list is answering "which machine do
        I mean", and the photograph settles that faster than a name that differs from
        the one you know it by.
        """
        made = " ".join(str(part) for part in
                        (item.get("manufacturer"), item.get("year")) if part)
        candidates.choice(item.get("img_url") or "",
                          str(item.get("name") or ""), made,
                          lambda i=item: self._show_offers(
                              self.online_body, i.get("vps_id") or "",
                              i.get("name") or "that game"),
                          glyph="videogame_asset")

    async def _show_offers(self, body: ui.column, vps_id: str, name: str) -> None:
        """The files one game is offered, under a heading that names that game.

        Named because this list and the search above it drift apart: you search for
        something else, and the files below go on being the ones you were already
        looking at. Nothing said which game they belonged to.
        """
        body.clear()
        # Named only when it is not this game's own: a heading that says the obvious on
        # every visit stops being read by the time it matters.
        found_online = labels.plural(self.label) + " found online"
        self.online_head.text = (found_online if vps_id == self._own_id
                                 else f"{found_online} for {name}")
        if not vps_id:
            with body:
                ui.label("This game has no VPS id, so there is nothing to look up. "
                         "Search above to take art from a game that has one.") \
                    .classes("hub-help")
            return
        try:
            found = await run.io_bound(self.library.media_offers, vps_id, self.kind)
        except Exception as exc:
            with body:
                ui.label(f"Could not reach the catalogs: {exc}").classes("hub-help")
            return
        with body:
            if not found:
                where = self._searched()
                ui.label(f"Nothing in {where}" if where else
                         "No online sources are switched on").classes("hub-help")
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
            fetching = ui.notification(f"Fetching from {source_name}...",
                                       spinner=True, timeout=None)
            try:
                await run.io_bound(self.library.fetch_media, self.game_id,
                                   self.destination, self.kind, offer["source"],
                                   vps_id, size)
            except Exception as exc:
                ui.notify(f"Could not fetch it: {exc}", type="negative")
                return
            finally:
                fetching.dismiss()
            await self.finish(f"{self.label} saved from {source_name}")

        # The source is the first thing on the row, because with several of them the
        # question "where is this from" comes before "is it any good".
        meta = f"{source_name} \u00b7 {size.upper()}" if size else source_name
        self.candidate(offer.get("url") or "", str(offer.get("name") or ""),
                       meta, "", take)


def _placement_label(item: dict[str, Any]) -> str:
    """What to call a destination in the list, in the words the badges use.

    A table is named by its .vpx, trimmed from the front: these names run long and
    share a prefix with the folder, so the tail is the half that tells them apart.
    """
    label = str(item.get("label") or "")
    if not item.get("table"):
        return "All tables in this game"
    stem = label[:-4] if label.lower().endswith(".vpx") else label
    trimmed = stem if len(stem) <= 40 else "\u2026" + stem[-39:]
    return f"Only {trimmed}"


def _start_name(root: dict[str, Any]) -> str:
    """What to call a starting point. The game's own folder is not named after the
    folder, because the folder's name is the one thing already on screen above it."""
    return ("This game's folder" if root.get("source") == "game"
            else str(root.get("name") or root.get("path") or ""))


def open_sources(context: dict[str, Any], kind: str, label: str,
                 done: Callable) -> None:
    """Open the ways to fill this slot. Returns as soon as the dialog is up."""
    sources = _Sources(context, kind, label, done)
    with ui.dialog() as dialog, ui.card().classes("hub-sources-card"):
        sources.dialog = dialog
        with ui.row().classes("items-center gap-2 w-full no-wrap hub-viewer-bar"):
            ui.label(f"{label} for this "
                     f"{'table' if context['lens'] else 'game'}") \
                .classes("hub-card-title grow min-w-0")
            ui.button(icon="close", on_click=dialog.close).props("flat dense round")
        destination = ui.column().classes("w-full gap-0")

        # Ordered by how far the file has to travel: your own computer, this machine,
        # then the internet.
        with ui.tabs().props("dense no-caps align=left").classes("w-full") as tabs:
            ui.tab("upload", label="Upload a file", icon="upload_file")
            ui.tab("browse", label="On this machine", icon="folder_open")
            ui.tab("online", label="Online", icon="cloud_download")
        with ui.tab_panels(tabs, value="upload").classes("w-full hub-sources-panels"):
            with ui.tab_panel("upload"):
                sources.upload_tab()
            with ui.tab_panel("browse"):
                browse_body = ui.column().classes("w-full gap-2")
            with ui.tab_panel("online"):
                online_body = ui.column().classes("w-full gap-2")

    dialog.open()

    async def start() -> None:
        # Read before anything else: the destination is the decision every tab feeds,
        # and a picker that appears after the first file is chosen has come too late.
        await sources.load_placements()
        with destination:
            sources._destination_row()

    ui.timer(0, start, once=True)

    # Each tab reads when it is opened rather than up front: two of the three make a
    # request, and a dialog that fetches everything before showing anything would be
    # slowest at the thing people do most, which is drop a file on the first tab.
    loaded: set[str] = set()

    async def load(event: Any) -> None:
        if event.value in loaded:
            return
        loaded.add(event.value)
        if event.value == "browse":
            await sources.browse_tab(browse_body)
        elif event.value == "online":
            await sources.online_tab(online_body)

    tabs.on_value_change(load)
