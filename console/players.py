"""Players: who plays here, who the next game counts for, and the accounts each one holds.

A grid with a workbench, the shape Launchers uses beside it. The account sections of a
player's rail are built as the panel opens, from what is running then.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from typing import Any

from nicegui import run, ui

from common import icons
from common.failures import why
from common.i18n import t
from console import (
    busy,
    confirm,
    deeplink,
    game_tables,
    grid,
    list_art,
    offload,
    panel,
    verbs,
    views,
)
from console import dialog as frame
from console.data import Library
from console.on_page import on_page

logger = logging.getLogger("vpinfe.console.players")

SCOPE = "console.players.columns"

OWNER, GUEST = "owner", "guest"

KINDS = {OWNER: ("console.players.owner", "console.players.owner.help"),
         GUEST: ("console.players.guest", "console.players.guest.help")}

# The acts core knows by key: the card an extension answers is shown or saved.
SHOW_CARD, SAVE_CARD = "show_card", "save_card"
_ACT_ICONS = {SHOW_CARD: verbs.ENLARGE, SAVE_CARD: verbs.FETCH, "send_now": verbs.SEND,
              "your_page": verbs.OPEN_OUT}

CARD_FILES = (".svg", "image/svg+xml", ".json", ".txt")

_ESCAPE = ("const esc = s => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;')"
           ".replace(/\"/g, '&quot;');")

_CHIPS = {kind: {"label": t(label), "tip": t(tip)} for kind, (label, tip) in KINDS.items()}

_NAME = (
    "params => {" + _ESCAPE +
    f" const kinds = {json.dumps(_CHIPS)};"
    f" const up = esc({json.dumps(t('console.players.up'))});"
    f" const upTip = esc({json.dumps(t('console.players.up.help'))});"
    " const d = params.data || {};"
    " let said = esc(params.value == null ? '' : params.value);"
    " const kind = kinds[d.kind];"
    " if (kind) said += ' <span class=\"console-member-chip console-chip-quiet\" title=\"'"
    " + esc(kind.tip) + '\">' + esc(kind.label) + '</span>';"
    " if (d.up) said += ' <span class=\"console-member-chip console-tier console-tier--on\""
    " title=\"' + upTip + '\">' + up + '</span>';"
    " if (d.session) said += ' <span class=\"console-cell-quiet\">' + esc(d.session)"
    " + '</span>';"
    " return said; }"
)

_INITIALS = (
    "params => {" + _ESCAPE +
    f" const same = esc({json.dumps(t('console.players.same_initials'))});"
    " const d = params.data || {};"
    " const said = esc(params.value == null ? '' : params.value);"
    " return d.shared ? said + ' <span class=\"console-member-chip console-tier"
    " console-tier--warn\" title=\"' + esc(d.shared) + '\">' + same + '</span>' : said; }"
)

# A cell draws more of its row than its own value: without `equals`, a row updated with
# only its Up changed keeps the chips it had.
_REDRAWN: dict[str, Any] = {":equals": "() => false"}

COLUMNS: list[dict[str, Any]] = [
    grid.identifier("name", t("word.name"), 260, pinned="left",
                    **{":cellRenderer": _NAME, **_REDRAWN}),
    grid.column("initials", t("console.players.initials"), 160,
                help=t("console.players.initials.help"),
                **{":cellRenderer": _INITIALS, **_REDRAWN}),
]

PLAYER_VIEWS: dict[str, list[str] | views.Preset] = {
    "console.view.overview": ["name", "initials"],
}


# -- the rows ------------------------------------------------------------------

def shown_name(player: dict[str, Any]) -> str:
    """The name, else the initials: a guest who joined with initials has nothing else."""
    return (str(player.get("name") or "").strip() or str(player.get("initials") or "").strip()
            or t("console.players.no_name"))


def kind_of(player: dict[str, Any]) -> str:
    return OWNER if player.get("owner") else GUEST if player.get("guest") else ""


def kind_word(player: dict[str, Any]) -> str:
    """What the panel's header says the player is."""
    kind = kind_of(player)
    return t(KINDS[kind][0]) if kind else t("console.players.player")


def same_initials(player: dict[str, Any], roster: list[dict[str, Any]]) -> str:
    """The alert for a player sharing initials with another, or "" for one who is not."""
    named = [shown_name(one) for one in roster
             if one.get("id") in (player.get("shares_initials_with") or [])]
    if not named:
        return ""
    return t("console.players.same_initials_as",
             player=t("console.collection_rules.list_join").join(named))


def rows(roster: list[dict[str, Any]],
         played: dict[str, int] | None = None) -> list[dict[str, Any]]:
    """One per player, in the roster's order. `played` counts each guest's games this
    session."""
    alone = len(roster) <= 1
    made = []
    for player in roster:
        games = int((played or {}).get(str(player.get("id") or "")) or 0)
        made.append({
            "id": str(player.get("id") or ""),
            "name": shown_name(player),
            "initials": str(player.get("initials") or ""),
            "kind": kind_of(player),
            "up": bool(player.get("up")) and not alone,
            "shared": same_initials(player, roster),
            "session": (t("console.players.games_this_session", count=games)
                        if player.get("guest") and games else ""),
        })
    return made


def games_played(record: list[dict[str, Any]]) -> int:
    return sum(int(one.get("play_count") or 0) for one in record)


async def _read(library: Library) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """The roster, and how many games each guest has played this session."""
    roster = await offload.io(library.players)
    played: dict[str, int] = {}
    for player in roster:
        if player.get("guest"):
            try:
                played[player["id"]] = games_played(
                    await offload.io(library.player_record, player["id"]))
            except Exception:  # noqa: BLE001 - a count is not worth failing the page for
                logger.debug("Could not read a guest's record", exc_info=True)
    return roster, played


# -- the grid ------------------------------------------------------------------

def build(library: Library, state: dict[str, Any],
          on_select: Callable[[dict | None], Any], redraw: Callable[[], None]) -> None:
    """The grid. Read on every draw: a phone or the frontend can change who is up."""
    body = ui.column().classes("w-full grow min-h-0 gap-0")
    busy.fill(body, lambda: _fill(library, state, on_select, redraw, body))


async def _fill(library: Library, state: dict[str, Any],
                on_select: Callable[[dict | None], Any], redraw: Callable[[], None],
                body: Any) -> None:
    state["show_player"] = on_select
    try:
        roster, played = await _read(library)
    except Exception as exc:  # noqa: BLE001 - this page says why, never 500s
        with body:
            panel.facts(ui, [panel.intro(t("console.players.could_not_read_players"),
                                         hint=why(exc))])
        return

    # Imported here: `workbench` imports this module, and `games` imports `workbench`.
    from console.games import view_control

    built = rows(roster, played)
    guests = [one for one in roster if one.get("guest")]
    fields = [definition["field"] for definition in COLUMNS]

    with body:
        with ui.row().classes("w-full items-center gap-2 px-3 py-2 mb-2 shrink-0 "
                              "console-panel console-grid-bar"):
            bar = panel.grid_bar()
            wire_views, _picker, showing, describe = view_control(
                library, SCOPE, PLAYER_VIEWS, fields, COLUMNS, bar=bar)
            describe()
            with bar.top, panel.bar_end():
                search = panel.search(t("console.players.search_players"))
            with bar.bottom, panel.bar_end():
                ui.label(t("console.players.players_count", count=len(built))) \
                    .classes("text-xs console-label")
                panel.add_action(
                    [(t("console.players.add_player"),
                      lambda: add_player(library, state, redraw)),
                     (t("console.players.add_guest"),
                      lambda: add_guest(library, state, redraw))],
                    empty=False)
                if guests:
                    panel.icon_action(
                        t("console.players.sign_out_guests"),
                        lambda: sign_out_guests(library, state, redraw),
                        icon=verbs.REMOVE, hint=t("console.players.sign_out_guests"))()

        by_id = {row["id"]: row for row in built}
        by_player = {str(one["id"]): one for one in roster}
        grid.on_row_focus(SCOPE,
                          lambda event: on_select(by_id.get(grid.focused_row(event))))

        def fill(row: dict | None) -> None:
            player = by_player.get(str((row or {}).get("id") or ""))
            if player is None:
                menu.clear()
                return
            panel.verb_menu(menu, shown_name(player), acts(library, state, player, redraw))

        with ui.element("div").classes("w-full grow min-h-0 flex flex-col"):
            table = grid.build(COLUMNS, built, SCOPE, on_context=fill, view_of=showing)
            menu = ui.context_menu()
        search.on_value_change(
            lambda: table.run_grid_method("setGridOption", "quickFilterText",
                                          search.value or ""))
        wire_views(table)

        async def refresh_players() -> None:
            fresh, counted = await _read(library)
            by_player.clear()
            by_player.update({str(one["id"]): one for one in fresh})
            grid.replace_rows(table, built, by_id, rows(fresh, counted), lambda _row: True)

        state["refresh_players"] = refresh_players


async def _refresh(state: dict[str, Any]) -> None:
    again = state.get("refresh_players")
    if callable(again):
        await again()


async def _open(state: dict[str, Any], redraw: Callable[[], None], player_id: str) -> None:
    """The grid drawn again with them, and them in the workbench."""
    state["player"] = player_id
    grid.land_on(SCOPE, {"id": player_id})
    redraw()
    show = state.get("show_player")
    if callable(show):
        await show({"id": player_id})


# -- adding --------------------------------------------------------------------

def _initials_field(value: str = "") -> Any:
    control = frame.field(value, placeholder=t("console.players.initials_example"))
    control.props("maxlength=3 bottom-slots")
    return control


def _card_picker(label: str, on_upload: Callable[[Any], Any]) -> None:
    """A hidden uploader for one card file, and the action that opens it."""
    uploader = ui.upload(on_upload=on_upload, auto_upload=True).classes("hidden")
    uploader.props(f'accept="{",".join(CARD_FILES)}"')
    uploader.on("finish", js_handler=f"() => getElement({uploader.id}).$refs.qRef.reset()")
    panel.action(label, None, icon=verbs.FROM_FILE,
                 js=f"() => getElement({uploader.id}).$refs.qRef.pickFiles()")()


def _refused(control: Any, said: str) -> None:
    control.props["error"] = bool(said)
    control.props["error-message"] = said
    control.update()


@on_page
async def add_player(library: Library, state: dict[str, Any],
                     redraw: Callable[[], None]) -> None:
    """A kept player: a name, and the initials a score finds them by."""
    fields: dict[str, Any] = {}

    async def keep() -> None:
        try:
            made = await offload.io(library.add_player,
                                    str(fields["name"].value or "").strip(),
                                    str(fields["initials"].value or "").strip())
        except Exception as exc:  # noqa: BLE001 - the refusal is about the initials
            _refused(fields["initials"], why(exc))
            return
        box.submit(str(made.get("id") or ""))

    def draw(key: str) -> Callable[[], None]:
        def drawn() -> None:
            fields[key] = _initials_field() if key == "initials" else frame.field()
        return drawn

    with frame.opened(t("console.players.add_player"), persistent=True) as box:
        panel.facts(ui, [(t("word.name"), draw("name")),
                         (t("console.players.initials"), draw("initials"))])
        with frame.footer():
            frame.cancel(lambda: box.submit(None))
            go = frame.answer(t("word.add"), keep, icon=verbs.ADD)
    fields["initials"].on_value_change(lambda: _refused(fields["initials"], ""))
    frame.focus(box, fields["name"])
    frame.enter_presses(go)
    made = await box
    if made:
        await _open(state, redraw, str(made))


@on_page
async def add_guest(library: Library, state: dict[str, Any],
                    redraw: Callable[[], None]) -> None:
    """A guest, who is up as they join."""
    held: dict[str, Any] = {}

    async def with_initials() -> None:
        try:
            made = await offload.io(library.add_guest,
                                    str(held["initials"].value or "").strip())
        except Exception as exc:  # noqa: BLE001 - the refusal is about the initials
            _refused(held["initials"], why(exc))
            return
        box.submit(str(made.get("id") or ""))

    @on_page
    async def with_card(event: Any) -> None:
        try:
            text = (await event.file.read()).decode("utf-8", "replace")
            made = await offload.io(library.add_guest_from_card, text)
        except Exception as exc:  # noqa: BLE001 - said, and the dialog stays for a retry
            ui.notify(t("console.players.could_not_add_guest"), caption=why(exc),
                      type="negative")
            return
        box.submit(str(made.get("id") or ""))

    def card_row() -> None:
        with ui.element("div").classes("console-fact-edit"):
            _card_picker(t("console.players.choose_card"), with_card)

    def initials_row() -> None:
        held["initials"] = _initials_field()

    with frame.opened(t("console.players.add_guest"), persistent=True) as box:
        ui.label(t("console.players.guest_forgotten")).classes("console-help px-3")
        panel.facts(ui, [(t("console.players.use_a_card"), card_row),
                         (t("console.players.just_initials"), initials_row)])
        with frame.footer():
            frame.cancel(lambda: box.submit(None))
            go = frame.answer(t("word.add"), with_initials, icon=verbs.ADD)
    held["initials"].on_value_change(lambda: _refused(held["initials"], ""))
    frame.focus(box, held["initials"])
    frame.enter_presses(go)
    made = await box
    if made:
        await _open(state, redraw, str(made))


# -- removing ------------------------------------------------------------------

def acts(library: Library, state: dict[str, Any], player: dict[str, Any],
         redraw: Callable[[], None]) -> list[panel.Verb]:
    """What can be done to one player. The owner stays, and says so."""
    if player.get("guest"):
        return [panel.Verb(t("console.players.sign_out"),
                           lambda: sign_out(library, state, redraw, player), danger=True)]
    return [panel.Verb(t("word.remove"),
                       None if player.get("owner")
                       else (lambda: remove(library, state, redraw, player)),
                       danger=True, hint=t("error.players.owner_not_removable"))]


def removal_detail(carded: dict[str, Any] | None) -> list[str]:
    """What a kept player's removal takes with it, and the account only their card can
    bring back where they hold one."""
    said = [t("console.players.remove_detail")]
    if carded is not None:
        said.append(t("console.players.remove_card_detail",
                      service=str(carded.get("label") or carded.get("extension") or "")))
    return said


@on_page
async def remove(library: Library, state: dict[str, Any], redraw: Callable[[], None],
                 player: dict[str, Any]) -> None:
    """Asked first, with Save Card beside the answer where they hold a card."""
    try:
        held = await offload.io(library.player_accounts, player["id"])
    except Exception:  # noqa: BLE001 - the confirm still asks, without the offer
        logger.debug("Could not read a player's accounts before removing", exc_info=True)
        held = []
    carded = next((one for one in held if one.get("card")), None)
    also = None
    if carded is not None:
        account: dict[str, Any] = carded
        also = (t("console.players.save_card"),
                lambda: save_card(library, player, account), verbs.FETCH)
    if not await confirm.ask(t("console.players.remove", name=shown_name(player)),
                             detail=removal_detail(carded), confirm=t("word.remove"),
                             icon=verbs.REMOVE, also=also):
        return
    await _gone(library, state, redraw, [player])


@on_page
async def sign_out(library: Library, state: dict[str, Any], redraw: Callable[[], None],
                   player: dict[str, Any]) -> None:
    if not await confirm.ask(t("console.players.sign_out_one", name=shown_name(player)),
                             detail=t("console.players.sign_out_detail"),
                             confirm=t("console.players.sign_out"), icon=verbs.REMOVE):
        return
    await _gone(library, state, redraw, [player])


@on_page
async def sign_out_guests(library: Library, state: dict[str, Any],
                          redraw: Callable[[], None]) -> None:
    """Every guest at once: the ones here now, including any who joined from a phone
    after the page was drawn."""
    try:
        guests = [one for one in await offload.io(library.players) if one.get("guest")]
    except Exception as exc:  # noqa: BLE001
        ui.notify(t("console.players.could_not_read_players"), caption=why(exc),
                  type="negative")
        return
    if not guests:
        redraw()
        return
    if not await confirm.ask(t("console.players.sign_out_everyone"),
                             detail=t("console.players.sign_out_detail"),
                             lines=[shown_name(one) for one in guests],
                             confirm=t("console.players.sign_out"), icon=verbs.REMOVE):
        return
    await _gone(library, state, redraw, guests)


@on_page
async def _gone(library: Library, state: dict[str, Any], redraw: Callable[[], None],
                players: list[dict[str, Any]]) -> None:
    for player in players:
        try:
            await run.io_bound(library.remove_player, player["id"])
        except Exception as exc:  # noqa: BLE001
            ui.notify(t("said.could_not_remove_it"), caption=why(exc), type="negative")
            break
    if state.get("player") in {one["id"] for one in players}:
        state["player"] = ""
    redraw()


# -- the panel -----------------------------------------------------------------

def _of(context: dict[str, Any]) -> dict[str, Any]:
    return context["player"]


async def changed(context: dict[str, Any], *, again: bool = True) -> None:
    """The grid's rows, and with `again` this panel, after a write."""
    await _refresh(context["state"])
    if again:
        await context["rebuild"]()


def _alert(line: str) -> tuple[Any, Callable[[], None]]:
    def draw() -> None:
        with ui.element("div").classes("console-attention"):
            ui.icon("error_outline").classes("console-attention-icon")
            ui.label(line).classes("console-attention-line")
    return (panel.FULL, draw)


async def details(context: dict[str, Any]) -> None:
    """Who they are, and whether the next game counts for them."""
    library, player = context["library"], _of(context)
    roster = context["roster"]
    player_id = player["id"]

    async def rename(text: str) -> str:
        wanted = text.strip()
        if wanted == str(player.get("name") or ""):
            return ""
        try:
            await run.io_bound(library.change_player, player_id, name=wanted)
        except Exception as exc:  # noqa: BLE001 - said on the field
            return why(exc)
        player["name"] = wanted
        context["retitle"](shown_name(player))
        await changed(context, again=False)
        return ""

    async def initials(text: str) -> str:
        wanted = text.strip()
        if wanted.upper() == str(player.get("initials") or "").upper():
            return ""
        try:
            now = await offload.io(library.change_player, player_id, initials=wanted)
        except Exception as exc:  # noqa: BLE001 - said on the field
            return why(exc)
        sharing_before = bool(player.get("shares_initials_with"))
        player.update(now)
        # The finding at the top of this section comes or goes with it.
        await changed(context, again=sharing_before != bool(now.get("shares_initials_with")))
        return ""

    @on_page
    async def flip(on: bool) -> None:
        try:
            await run.io_bound(library.set_player_up, player_id, on)
        except Exception as exc:  # noqa: BLE001
            ui.notify(t("said.could_not_save_it"), caption=why(exc), type="negative")
        await changed(context)

    entries: list[tuple[Any, Any]] = []
    if alert := same_initials(player, roster):
        entries.append(_alert(alert))
    entries += [
        (t("word.name"), panel.field(str(player.get("name") or ""), rename, refuses=True)),
        (t("console.players.initials"),
         panel.field(str(player.get("initials") or ""), initials, refuses=True,
                     placeholder=t("console.players.initials_example"))),
    ]
    if len(roster) > 1:
        # Nobody up means the owner is: the owner alone up has nowhere to go.
        stays = bool(player.get("owner") and player.get("up")
                     and sum(1 for one in roster if one.get("up")) == 1)
        entries.append((t("console.players.up"), panel.switch(
            bool(player.get("up")), lambda event: flip(bool(event.value)), disabled=stays,
            hint=t("console.players.owner_up_alone") if stays else "")))
    with ui.column().classes("gap-0 console-form"):
        panel.facts(ui, entries)


# -- accounts ------------------------------------------------------------------

def account_key(extension: str) -> str:
    return f"player_account_{extension}"


def account_section(account: dict[str, Any]) -> tuple[str, Callable[[dict], str],
                                                      Callable[[dict], Any]]:
    """The rail row for one account: its key, its name, and how it draws."""
    label = str(account.get("label") or account["extension"])

    async def build(context: dict[str, Any]) -> None:
        await _account(context, account)

    return account_key(str(account["extension"])), (lambda _context: label), build


def secret_state(field: dict[str, Any]) -> Callable[[], None]:
    """Whether a secret is held, never what it is. No edit: a card is how one arrives."""
    held = bool(field.get("set"))
    return panel.state(t("console.ext_page.secret_set" if held
                         else "console.ext_page.secret_not_set"), "on" if held else "off")


def share_help(account: dict[str, Any]) -> str:
    return (str(account.get("share_help") or "").strip()
            or t("console.players.share.help",
                 service=str(account.get("label") or account.get("extension") or "")))


async def _account(context: dict[str, Any], account: dict[str, Any]) -> None:
    library, player = context["library"], _of(context)
    extension = str(account["extension"])
    if account.get("error"):
        panel.facts(ui, [panel.intro(t("console.players.could_not_read_account"),
                                     hint=str(account["error"]))])
        return

    @on_page
    async def write(key: str, value: Any) -> None:
        try:
            await run.io_bound(library.put_account, player["id"], extension, {key: value})
        except Exception as exc:  # noqa: BLE001
            ui.notify(t("said.could_not_save_it"), caption=why(exc), type="negative")
            return
        await context["rebuild"]()

    @on_page
    async def share(on: bool) -> None:
        try:
            await run.io_bound(library.put_share, player["id"], extension, on)
        except Exception as exc:  # noqa: BLE001
            ui.notify(t("said.could_not_save_it"), caption=why(exc), type="negative")
            await context["rebuild"]()

    entries: list[tuple[Any, Any]] = []
    for field in account.get("fields") or []:
        key = str(field.get("key") or "")
        if not key:
            continue
        entries.append((str(field.get("label") or key), _control(field, key, write)))
        if field.get("help"):
            entries.append(panel.note(str(field["help"])))
    entries += [(t("console.players.share"),
                 panel.switch(bool(account.get("share")), lambda e: share(bool(e.value)))),
                panel.note(share_help(account))]
    if account.get("status"):
        entries.append(panel.intro(str(account["status"])))
    offered = [one for one in account.get("acts") or [] if one.get("key")]

    def strip() -> None:
        with ui.element("div").classes("console-slot-actions"):
            for act in offered:
                panel.action(str(act.get("label") or act["key"]),
                             lambda _e=None, act=act: run_act(context, account, act),
                             icon=_ACT_ICONS.get(str(act["key"]), verbs.RUN),
                             hint=str(act.get("description") or ""))()
            if account.get("reads_cards"):
                _card_picker(t("console.players.use_a_card"),
                             lambda event: use_card(context, account, event))

    if offered or account.get("reads_cards"):
        entries.append((panel.FULL, strip))
    with ui.column().classes("gap-0 console-form"):
        panel.facts(ui, entries)


def holds_a_secret(account: dict[str, Any]) -> bool:
    return any(field.get("type") == "secret" and field.get("set")
               for field in account.get("fields") or [])


@on_page
async def use_card(context: dict[str, Any], account: dict[str, Any], event: Any) -> None:
    """A card made on another install, taken into this account. Asked first where the
    account holds a secret already, since the card's replaces it."""
    library, player = context["library"], _of(context)
    extension = str(account["extension"])
    service = str(account.get("label") or extension)
    text = (await event.file.read()).decode("utf-8", "replace")
    if holds_a_secret(account):
        carded = bool(account.get("card"))
        detail = [t("console.players.use_card_replaces", service=service)] + (
            [t("console.players.remove_card_detail", service=service)] if carded else [])
        also = ((t("console.players.save_card"),
                 lambda: save_card(library, player, account), verbs.FETCH) if carded else None)
        if not await confirm.ask(t("console.players.use_card_for", name=shown_name(player)),
                                 detail=detail, confirm=t("console.players.use_a_card"),
                                 icon=verbs.REPLACE, also=also):
            return
    try:
        await run.io_bound(library.use_card, player["id"], extension, text)
    except Exception as exc:  # noqa: BLE001
        ui.notify(t("console.players.could_not_use_card"), caption=why(exc), type="negative")
        return
    ui.notify(t("console.players.card_used", service=service), type="positive")
    await context["rebuild"]()


def _control(field: dict[str, Any], key: str,
             write: Callable[[str, Any], Any]) -> Callable[[], None]:
    kind = str(field.get("type") or "string")
    value = field.get("value")
    if kind == "secret":
        return secret_state(field)
    if kind == "switch":
        return panel.switch(bool(value), lambda event: write(key, bool(event.value)))
    if kind == "select":
        choices = {str(one[0]): str(one[1]) for one in field.get("choices") or []}
        return panel.select(choices, str(value or ""), lambda event: write(key, event.value))

    def save(text: str) -> Any:
        if text.strip() == str(value or "").strip():
            return None
        return write(key, text.strip())

    return panel.field(str(value or ""), save,
                       placeholder=str(field.get("placeholder") or ""))


@on_page
async def run_act(context: dict[str, Any], account: dict[str, Any],
                  act: dict[str, Any]) -> None:
    """Do it, and follow what it answers."""
    library, player = context["library"], _of(context)
    key = str(act["key"])
    if key == SAVE_CARD:
        await save_card(library, player, account)
        return
    try:
        said = await offload.io(library.account_act, player["id"], account["extension"], key)
    except Exception as exc:  # noqa: BLE001
        ui.notify(t("said.could_not_do_that"), caption=why(exc), type="negative")
        return
    if key == SHOW_CARD:
        await _show_card(library, player, account, str(said.get("message") or ""))
        return
    if said.get("url"):
        ui.navigate.to(str(said["url"]), new_tab=True)
    if said.get("message"):
        ui.notify(str(said["message"]))
    await context["rebuild"]()


@on_page
async def _show_card(library: Library, player: dict[str, Any], account: dict[str, Any],
                     message: str) -> None:
    try:
        drawn = await offload.io(library.player_card, player["id"], account["extension"])
    except Exception as exc:  # noqa: BLE001
        ui.notify(t("said.could_not_do_that"), caption=why(exc), type="negative")
        return
    with frame.opened(t("console.players.card_of", name=shown_name(player))) as box:
        with ui.column().classes("items-center w-full gap-2"):
            ui.html(drawn.decode("utf-8", "replace")).classes("console-qr")
            if message:
                ui.label(message).classes("console-help px-3 text-center")
        with frame.footer():
            frame.answer(t("word.close"), lambda: box.submit(None), icon=verbs.CLOSE)
    await box


def card_filename(said: dict[str, Any], extension: str) -> str:
    """The name the extension gave the card, as an SVG file."""
    stem = str(said.get("filename") or "").strip() or f"{extension}-card"
    return stem if stem.lower().endswith(".svg") else f"{stem}.svg"


@on_page
async def save_card(library: Library, player: dict[str, Any],
                    account: dict[str, Any]) -> None:
    """Downloads core's drawing of the card."""
    extension = str(account["extension"])
    try:
        said = await offload.io(library.account_act, player["id"], extension, SAVE_CARD)
        drawn = await offload.io(library.player_card, player["id"], extension)
    except Exception as exc:  # noqa: BLE001
        ui.notify(t("said.could_not_do_that"), caption=why(exc), type="negative")
        return
    ui.download.content(drawn, card_filename(said, extension), "image/svg+xml")
    ui.notify(t("console.players.card_saved"), caption=str(said.get("message") or ""),
              type="positive")


# -- plays ---------------------------------------------------------------------

def has_plays(player: dict[str, Any]) -> bool:
    """Not the owner, whose plays are the library's."""
    return not player.get("owner")


def played_line(game: dict[str, Any]) -> str:
    """Count, time and when, where they played it; their best score, where they have
    one. Either can stand alone: a score reaches its player whether they were up or not."""
    # Imported here: `workbench` imports this module for its sections.
    from console import workbench

    parts = []
    count = int(game.get("play_count") or 0)
    if count:
        parts.append(t("console.players.played", count=count,
                       time=workbench._played_for(int(game.get("play_time_seconds") or 0)),
                       when=workbench._played_when(game.get("last_played"))))
    best = game.get("best_score") or {}
    if best:
        parts.append(t("console.players.best", score=workbench._score_lines(best)[0]))
    return game_tables.JOIN.join(parts)


async def plays(context: dict[str, Any]) -> None:
    """A row per game they played or scored on, in the record's order."""
    library, player = context["library"], _of(context)
    try:
        record = await offload.io(library.player_record, player["id"])
    except Exception as exc:  # noqa: BLE001
        panel.facts(ui, [panel.intro(t("console.players.could_not_read_plays"),
                                     hint=why(exc))])
        return
    shown = [one for one in record if played_line(one)]
    if library.list_art():
        await offload.io(library.load_tables)
    art = library.game_art()
    look = library.list_art_look()
    games = {str(one.get("id") or ""): one for one in library.games}
    with ui.column().classes("gap-0 console-form w-full min-w-0"):
        if not shown:
            ui.label(t("console.players.no_plays")).classes("console-help px-3")
        for one in shown:
            game_id = str(one.get("game_id") or "")
            game = games.get(game_id)
            to = "/console?" + deeplink.query({"view": "games", "game": game_id})
            with ui.row().classes("items-center gap-2 w-full no-wrap console-member-row"), \
                    list_art.beside(None if art is None else art.get(game_id, ""),
                                    icons.GAMES, to=to, look=look), \
                    ui.column().classes("gap-0 grow min-w-0"):
                if game is None:
                    ui.label(t("console.players.game_gone")).classes("console-help")
                else:
                    panel.link(str(game.get("name") or ""), to=to)()
                    if made := game_tables.made(game):
                        ui.label(made).classes("console-cell-made")
                ui.label(played_line(one)).classes("console-help")
