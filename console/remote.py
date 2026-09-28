"""The remote: VPinFE in one hand.

A fourth posture, and the whole specification. Not the frontend, which is read across a
room; not the Console, which is a workbench at a desk. This is standing beside the
machine or sitting across from it - one thumb, screen lit for twenty seconds at a time.
Anything that does not fit that is not on this surface.

A second shell rather than a stylesheet, because the Console *is* a workbench - a
splitter with a list on one side and an inspector on the other - and a phone cannot hold
two panes. Below its own width the organizing idea is simply absent, so what would ship
is a shell missing the thing it is for. The client, the reads, the tokens and the fact
list are all shared; only the shape is new.

Three screens, and they read as a sequence: what is happening, pick something, drive it.
"""

from __future__ import annotations

import asyncio
import logging
import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from io import BytesIO
from typing import Any

from nicegui import background_tasks, run, ui

from common import device_registry, events, install_identity
from common.config_access import NetworkConfig
from common.failures import why
from common.host.launch_state import SOURCE_CAPTURE
from common.i18n import t
from common.labels import humanize
from console import (
    busy,
    confirm,
    game_tables,
    offload,
    panel,
    remembered,
    remote_record,
    stars,
    theme,
    verbs,
)
from console import dialog as frame
from console.api import ApiClient, ApiError, local_base_url
from console.data import Library
from console.on_page import on_page
from console.players import CARD_FILES, kind_of, save_card, share_help, shown_name

logger = logging.getLogger("vpinfe.console.remote")

NOW, PLAY, CONTROL, JOIN = "now", "play", "control", "join"

SCREENS = (
    (NOW, t("word.now"), "radio_button_checked"),
    (PLAY, t("console.remote.play"), "search"),
    (CONTROL, t("console.remote.control"), "gamepad"),
)


def is_here(device: dict[str, Any], local_device_id: str) -> bool:
    """Whether this row is the install serving the page.

    Two answers, and the second is not a fallback for the first. An install records
    itself with nothing to dial - there is no address it would reach itself on - while
    every other row is written from an address it was heard at, and a phone is refused
    without one. So a row with no address *is* this machine, by construction.

    That matters because the id is not always there to compare: discovery reads the
    identity off the config file each time it is asked, and a read that lands while that
    file is being rewritten answers with no id at all. Keying only on the id made the
    whole surface report that there was nothing to drive.
    """
    if local_device_id and device.get("device_id") == local_device_id:
        return True
    return not str(device.get("address") or "").strip()


def base_url_of(device: dict[str, Any], local_device_id: str) -> str:
    """Where to send this target's requests.

    Loopback for the install serving this page, whatever address it recorded for itself:
    a machine's own entry holds the address other machines reach it on, and dialling
    that from here would leave the network to answer a question we can answer without
    it.
    """
    if is_here(device, local_device_id):
        return local_base_url()
    address = str(device.get("address") or "").strip()
    port = int(device.get("port") or 0)
    return f"http://{address}:{port}" if address and port else ""


def targets(devices: list[dict[str, Any]], local_device_id: str) -> list[dict[str, Any]]:
    """The devices worth aiming at, which is the ones that play.

    A device with no frontend is a real device and belongs in the Console's list; it is
    not something a remote points at, and offering it would make the picker a list of
    machines rather than a list of answers to "where".
    """
    found = [one for one in devices
             if install_identity.FRONTEND in (one.get("features") or ())
             and base_url_of(one, local_device_id)]
    # This install first: it is the one the person is most likely to mean, and it is the
    # only one that is certainly there - it is serving the page.
    return sorted(found, key=lambda one: not is_here(one, local_device_id))


def target_name(device: dict[str, Any]) -> str:
    return str(device.get("display_name") or "").strip() or t("console.remote.this_device")


def _identity_key(device: dict[str, Any]) -> str:
    """Per browser and per target: a phone aimed at two installs can hold a
    different answer to who is holding it on each."""
    return f"remote.who.{str(device.get('device_id') or '').strip() or 'here'}"


def remembered_identity(device: dict[str, Any],
                        roster: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Who this phone said it is for the target it is aimed at now, or None - nobody
    said, which behaves as the owner.

    Checked against the roster on every read rather than trusted: a kept player removed,
    or a guest signed out, elsewhere leaves nothing for a stale id to resolve to.
    """
    wanted = str((remembered.get(_identity_key(device)) or {}).get("player_id") or "").strip()
    if not wanted:
        return None
    return next((one for one in roster if one.get("id") == wanted), None)


def remember_identity(device: dict[str, Any], player_id: str) -> None:
    remembered.put(_identity_key(device), {"player_id": player_id} if player_id else None)


def is_someone_else(identity: dict[str, Any] | None) -> bool:
    """Whether the phone is answering for anyone other than the owner."""
    return identity is not None and not identity.get("owner")


def last_played(games: list[dict[str, Any]]) -> dict[str, Any]:
    """The game played most recently, or nothing where none has been.

    Read off the library rather than from the frontend's own record of what it last
    launched: that one is per install and per window, and the question here is which
    game *this person* last had a game on.
    """
    played = [one for one in games if (one.get("user") or {}).get("last_played")]
    if not played:
        return {}
    return max(played, key=lambda one: str(one["user"]["last_played"]))


def _read_here() -> dict[str, Any]:
    """What this install knows about the network, made off the event loop.

    The Console consumes its own process over HTTP, so a page handler that asks the API
    a question while holding the loop deadlocks - uvicorn cannot answer a request it is
    blocked inside.
    """
    client = ApiClient()
    return {
        "devices": client.devices(),
        "local_device_id": str(client.discovery().get("install_id") or ""),
    }


def _read_target(client: ApiClient) -> dict[str, Any]:
    """What the chosen machine is doing and what it can play, and the collection its
    frontend is showing where it is up, which is the one the phone opens on.

    Asked of the target rather than of this install, because that is the machine the
    launch is going to. Two installs can hold different libraries, and a list read from
    the wrong one offers games whose ids the target has never heard of.
    """
    showing = _frontend_of(client)
    read: dict[str, Any] = {
        "play": client.play_state(),
        "games": offered_games(client.library_entries()),
        "jobs": client.jobs(),
        "collections": client.collections(),
        "frontend": showing,
        "players": client.players(),
        **remote_record.read(client),
    }
    if mirroring(showing):
        read.update(_narrowed_to(client, str((showing or {}).get("collection") or "")))
    return read


def _frontend_of(client: ApiClient) -> dict[str, Any] | None:
    """None where the target cannot say, and the Remote then does without a mirror."""
    try:
        return client.frontend_state()
    except ApiError as exc:
        logger.info("remote: the target did not say what its frontend shows: %s", exc)
        return None


def _narrowed_to(client: ApiClient, collection: str) -> dict[str, Any]:
    """The phone's collection and the ids of the games in it; None for the whole library."""
    ids = ({one["id"] for one in offered_games(client.collection_entries(collection))}
           if collection else None)
    return {"collection": collection, "collection_ids": ids}


# The first three carry the whole state, so a phone that missed one is right after the
# next. `table.play_recorded` does not - it says what one play came to, and a phone that
# missed it finds out on the next one instead, which is a fact about that play, not
# something to resync.
FOLLOWED = (events.FRONTEND_STATE_CHANGED, events.PLAY_STATE_CHANGED,
            events.CAPTURE_RUN_CHANGED, events.PLAYERS_CHANGED, events.TABLE_PLAY_RECORDED)

RECONNECT_SECONDS = 5.0


def _follow(base_url: str, stop: threading.Event,
            heard: Callable[[str, dict], None]) -> None:
    """Hand the target's changes to `heard` until `stop` is set.

    Every connection opens with the target's current state, so reconnecting after a drop
    also repairs whatever was missed while it was down.
    """
    while not stop.is_set():
        try:
            for name, payload in ApiClient(base_url or None).follow(FOLLOWED, stop):
                heard(name, payload)
        except Exception as exc:
            logger.info("remote: stopped hearing from %s: %s", base_url, exc)
        stop.wait(RECONNECT_SECONDS)


def mirroring(showing: dict[str, Any] | None) -> bool:
    return bool((showing or {}).get("running"))


def frontend_closed(showing: dict[str, Any] | None) -> bool:
    """Closed, as against unknown: a target too old to say is not a closed frontend."""
    return showing is not None and not showing.get("running")


def wheel_id(showing: dict[str, Any] | None) -> str:
    return str(((showing or {}).get("game") or {}).get("id") or "")


def on_the_wheel(showing: dict[str, Any] | None,
                 games: list[dict[str, Any]]) -> dict[str, Any]:
    """The game on the wheel as the list holds it, or as the frontend named it where the
    list does not; nothing where the wheel is empty."""
    game_id = wheel_id(showing)
    if not game_id:
        return {}
    for game in games:
        if game.get("id") == game_id:
            return game
    return {"id": game_id, "name": str(((showing or {}).get("game") or {}).get("name") or "")}


@ui.page("/remote", title=t("console.remote.vpinfe_remote"), reconnect_timeout=300)
async def remote_page(screen: str = "") -> None:
    """The remote. `screen` names which of the three, so a place can be linked to."""
    # The same setting the desk surface reads. One install, one appearance - a phone
    # showing a different palette from the workbench it is beside reads as a different
    # product.
    chosen = theme.configured_mode()
    ui.dark_mode(theme.QUASAR_DARK[chosen])
    theme.apply_colors(chosen)
    theme.apply_flair(chosen)
    theme.apply_surface("remote")
    # The shell takes the viewport once and everything below it is flex, the same way
    # the Console's does - a pane that subtracts a fixed header height collapses the
    # moment that header changes.
    ui.query(".nicegui-content").classes("p-0 gap-0 h-screen")
    # A phone locking its screen is the most common disconnect there is, far more common
    # than anything a desk session sees, so the meta viewport matters as much as the
    # reconnect timeout above.
    ui.add_head_html(
        '<meta name="viewport" content="width=device-width, initial-scale=1, '
        'viewport-fit=cover">')

    # Before the client connects, which is the only time a page can add to its own body.
    # Adding it from inside the screen that uses it looked right and installed nothing:
    # by then the page has been sent, and the pad had no behavior at all.
    ui.add_body_html(f"<script>{_HOLD_SCRIPT % {'renew': RENEW_MS}}</script>")

    # Once per page, not once per draw. Registered inside the screen that uses them, a
    # handler would be added again on every redraw and one thumb would send N presses.
    async def held(event: Any) -> None:
        await _say(client_for_target, str((event.args or {}).get("action") or ""),
                   "press")

    async def let_go(event: Any) -> None:
        await _say(client_for_target, str((event.args or {}).get("action") or ""),
                   "release")

    ui.on("remote_press", held)
    ui.on("remote_release", let_go)

    with ui.column().classes("w-full h-full items-center justify-center gap-3") as loading:
        ui.label(t("console.remote.loading")).classes("text-sm opacity-60")
    busy.until_gone(loading)

    await ui.context.client.connected()
    loaded = await offload.io(_read_here)
    if ui.context.client.is_deleted:
        # Reading takes long enough that somebody can close the tab inside it, and there
        # is then nothing to draw on. Building anyway raises out of the page function and
        # logs a stack trace for somebody having changed their mind.
        return

    local_device_id = loaded["local_device_id"]
    aimable = targets(loaded["devices"], local_device_id)
    state: dict[str, Any] = {
        "screen": screen if screen in {key for key, *_ in SCREENS} | {JOIN} else NOW,
        "target": aimable[0] if aimable else {},
        "play": {}, "games": [], "jobs": [], "collections": [],
        "find": "", "collection": "", "collection_ids": None,
        "frontend": None, "rows": {}, "relist": None,
        "capture": None, "run": {}, "waiting": [], "reviewing": None,
        "players": [], "identity": None, "record": {}, "accounts": [], "result": None,
    }

    def client_for_target() -> ApiClient:
        """A client aimed at whichever target is chosen. The picker is a base URL."""
        return ApiClient(base_url_of(state["target"], local_device_id) or None)

    async def reread_identity() -> None:
        """Who this phone is for the target now, and what goes with that: their own
        record, so a rating shown while browsing is theirs, and their accounts, for the
        identity sheet's Share and Save Card. Cleared, not failed, when there is nobody -
        that is the ordinary case, not an error."""
        state["identity"] = remembered_identity(state["target"], state["players"] or [])
        identity = state["identity"]
        if identity is None:
            state["record"], state["accounts"] = {}, []
            return
        try:
            state["record"] = {row["game_id"]: row for row in
                               await offload.io(client_for_target().player_record,
                                                identity["id"])}
            if identity.get("guest"):
                state["accounts"] = await offload.io(
                    client_for_target().player_accounts, identity["id"])
            else:
                state["accounts"] = []
        except Exception as exc:
            logger.info("remote: could not read %s's record: %s",
                        shown_name(identity), exc)
            state["record"], state["accounts"] = {}, []

    async def reread() -> None:
        """Ask the chosen machine again. Failure is a state, not a crash: a target that
        has gone away is the ordinary case for a page held in a hand."""
        if not state["target"]:
            return
        try:
            state.update(await offload.io(_read_target, client_for_target()))
            state["reachable"] = True
        except Exception as exc:
            logger.info("remote: %s did not answer: %s",
                        target_name(state["target"]), exc)
            state.update({"play": {}, "games": [], "jobs": [], "collections": [],
                          "frontend": None, "reachable": False, "capture": None,
                          "run": {}, "waiting": [], "reviewing": None,
                          "players": [], "identity": None, "record": {}, "accounts": []})
            follow()
            return
        await reread_identity()
        follow()

    def draw_strip() -> None:
        strip.clear()
        with strip:
            _strip(state, client_for_target, redraw)

    def redraw() -> None:
        """All of it, always. The bar says which screen you are on, so a redraw that
        rebuilt only the screen left the mark behind on the one you came from - and the
        header's identity can change from something other than the header itself (This
        Is Me on its own sheet, a roster change heard from the target), so it is rebuilt
        here too rather than trusted to still be right."""
        header.clear()
        with header:
            _header(state, aimable, aim, client_for_target, redraw)
        body.clear()
        tabs.clear()
        state["relist"] = None
        draw_strip()
        with body:
            _screen(state, client_for_target, redraw)
        with tabs:
            _tabs(state, redraw)

    # The target's changes arrive on a thread of the follower's own and are applied here,
    # on the loop, in the order they were sent. Each carries the follower that heard it,
    # so a change still in flight from a target the phone has moved off is dropped.
    loop = asyncio.get_running_loop()
    page = ui.context.client
    arriving: asyncio.Queue[tuple[threading.Event, str, dict]] = asyncio.Queue()
    following: list[threading.Event] = []

    def unfollow() -> None:
        while following:
            following.pop().set()

    def follow() -> None:
        """Hear the chosen target, where it said what its frontend shows. One that could
        not say is too old to stream the event either, and refuses the subscription."""
        unfollow()
        # A read can outlast the page: a thread started for a closed tab is never stopped.
        if state.get("frontend") is None or page.is_deleted:
            return
        stop = threading.Event()
        following.append(stop)

        def heard(name: str, payload: dict) -> None:
            loop.call_soon_threadsafe(arriving.put_nowait, (stop, name, payload))

        threading.Thread(target=_follow, name="remote-follow", daemon=True,
                         args=(base_url_of(state["target"], local_device_id), stop,
                               heard)).start()

    async def adopt(showing: dict[str, Any]) -> bool:
        """Take the frontend's collection as the phone's, where it has moved."""
        name = str(showing.get("collection") or "")
        if not mirroring(showing) or name == state["collection"]:
            return False
        try:
            state.update(await offload.io(_narrowed_to, client_for_target(), name))
        except Exception as exc:
            logger.info("remote: could not read %s from %s: %s", name,
                        target_name(state["target"]), exc)
            return False
        return True

    @on_page
    async def changed(name: str, payload: dict) -> None:
        if name == events.PLAYERS_CHANGED:
            state["players"] = list((payload.get("state") or {}).get("players") or [])
            await reread_identity()
            redraw()
            return
        if name == events.TABLE_PLAY_RECORDED:
            await _play_recorded(state, payload, client_for_target, redraw)
            return
        if name == events.CAPTURE_RUN_CHANGED:
            was, now = state.get("run") or {}, dict(payload.get("run") or {})
            state["run"] = now
            state["run_heard"] = int(state.get("run_heard") or 0) + 1
            if was and not now:
                try:
                    state["waiting"] = await offload.io(remote_record.waiting_of,
                                                        client_for_target())
                except Exception as exc:
                    logger.info("remote: could not read what waits: %s", exc)
            if was != now and state["screen"] != PLAY:
                redraw()
            return
        said = payload.get("state")
        if not isinstance(said, dict):
            return
        if name == events.PLAY_STATE_CHANGED:
            was = state.get("play") or {}
            state["play"] = said
            if said.get("launching"):
                state["reviewing"] = None
            if bool(was.get("launching")) != bool(said.get("launching")) \
                    or (bool(was.get("paused")) != bool(said.get("paused"))
                        and state["screen"] != PLAY):
                redraw()
            return
        was = state.get("frontend")
        state["frontend"] = said
        await remote_record.heard(state, said, client_for_target, redraw)
        switched = await adopt(said)
        if mirroring(was) != mirroring(said):
            redraw()
            return
        if switched and state.get("relist"):
            state["relist"]()
        else:
            _mark_here(state["rows"], wheel_id(was), wheel_id(said))
        draw_strip()

    async def listen() -> None:
        with page:
            while True:
                stop, name, payload = await arriving.get()
                if stop not in following:
                    continue
                try:
                    await changed(name, payload)
                except Exception:
                    logger.exception("remote: could not apply %s", name)

    listening = background_tasks.create(listen(), name="remote-listen")

    def gone() -> None:
        unfollow()
        listening.cancel()

    page.on_delete(gone)

    state["reread"] = reread

    async def aim(device: dict[str, Any]) -> None:
        """A different machine is a different library, a different state and a different
        base URL, so everything below the header is read again."""
        state.update({"target": device, "find": "", "collection": "",
                      "collection_ids": None})
        await reread()
        redraw()

    # `listen`, which draws what the target says, cannot run before this function next
    # waits, so nothing reaches `redraw` before the shell below exists.
    await reread()
    if page.is_deleted:
        return
    # Header, then the screen, then the tabs, in that order and inside the shell: the
    # body has to be built here rather than earlier and reparented, because a NiceGUI
    # element belongs to whatever slot was open when it was made.
    with ui.column().classes("w-full h-full gap-0 remote-shell no-wrap"):
        header = ui.column().classes("w-full gap-0")
        strip = ui.column().classes("w-full gap-0")
        body = ui.column().classes(
            "w-full grow min-h-0 gap-0 overflow-auto remote-body")
        tabs = ui.row().classes("w-full items-stretch gap-0 remote-tabs no-wrap")
    redraw()
    loading.delete()


def _header(state: dict[str, Any], aimable: list[dict[str, Any]], aim: Any,
            client_for_target: Callable[[], Any], redraw: Callable[[], None]) -> None:
    """The target, on every screen, because every action's meaning depends on it - and
    beside it, who this phone is answering for: the target alone for nobody said
    or a guest, the target and their initials for a kept player.

    Drawn as a picker only when there is a choice to make. With one target it is the
    name alone - a select with one option is furniture, which is the same rule that
    keeps a chip off every row.
    """
    identity = state.get("identity")
    with ui.row().classes("w-full items-center gap-2 remote-header no-wrap"):
        ui.icon("sports_esports").classes("remote-mark")
        if len(aimable) > 1:
            names = {one["device_id"]: target_name(one) for one in aimable}
            by_id = {one["device_id"]: one for one in aimable}

            async def chosen(event: Any) -> None:
                await aim(by_id.get(event.value, {}))

            ui.select(names, value=state["target"].get("device_id"),
                      on_change=chosen) \
                .props("dense borderless options-dense") \
                .classes("remote-target grow min-w-0")
        elif aimable:
            ui.label(target_name(state["target"])).classes("remote-target-name truncate")
        else:
            # Not an error: an install with no frontend feature is a library somebody
            # administers, and there is nothing here for a remote to drive.
            ui.label(t("console.remote.nothing_drive")) \
                .classes("remote-target-name truncate")
        if state.get("target"):

            def open_sheet() -> None:
                _identity_sheet(state, client_for_target, redraw)

            with ui.row().classes("items-center gap-1 cursor-pointer remote-identity") \
                    .on("click", open_sheet):
                if identity is not None and kind_of(identity) == "":
                    ui.label(str(identity.get("initials") or "")) \
                        .classes("remote-identity-initials")
                ui.icon("person").classes("remote-identity-icon")


def _strip(state: dict[str, Any], client_for_target: Callable[[], Any],
           redraw: Callable[[], None]) -> None:
    """The game on the frontend's wheel, with Launch, above every screen.

    Drawn only while the frontend is up and no table is: during a game the screen is
    showing the game, and Now already says so.
    """
    if not mirroring(state.get("frontend")) or state.get("reachable") is False \
            or (state.get("play") or {}).get("launching"):
        return
    game = on_the_wheel(state.get("frontend"), state.get("games") or [])

    def open_sheet(_event: Any = None) -> None:
        _game_sheet(game, state, client_for_target, redraw)

    with ui.row().classes("w-full items-center gap-3 no-wrap remote-strip"):
        with ui.column().classes("grow min-w-0 gap-0") as said:
            ui.label(t("console.remote.on_the_wheel")).classes("console-card-title")
            if not game:
                ui.label(t("console.remote.nothing_on_the_wheel")).classes("remote-empty")
                return
            ui.label(str(game.get("name") or "")).classes("remote-headline")
            made = game_tables.made(game)
            if made:
                ui.label(made).classes("remote-note truncate")
        said.on("click", open_sheet).classes("cursor-pointer")
        _launch_button(game, state, client_for_target, redraw,
                       cls="remote-action remote-action--primary remote-action--beside")


def _tabs(state: dict[str, Any], redraw: Callable[[], None]) -> None:
    """The three screens, at the bottom, where a thumb is.

    Not a nav rail and not a drawer: with three destinations and one hand, the whole map
    is worth the space it takes, and hiding it behind a button charges a tap to find out
    what the page can do.
    """
    for key, label, icon in SCREENS:
        def go(_event: Any=None, key: Any=key) -> None:
            state["screen"] = key
            redraw()

        here = state["screen"] == key
        with ui.column().on("click", go) \
                .classes("remote-tab" + (" remote-tab--here" if here else "")):
            ui.icon(icon).classes("remote-tab-icon")
            ui.label(label).classes("remote-tab-label")


@contextmanager
def _asked(title: str) -> Iterator[Any]:
    """`console.dialog.opened`'s own shape, without calling it."""
    with frame.made() as box, ui.card().classes("console-dialog"):
        ui.label(title).classes("console-dialog-title")
        yield box


def _identity_sheet(state: dict[str, Any], client_for_target: Callable[[], Any],
                    redraw: Callable[[], None]) -> None:
    """Who this phone is answering for: a kept player chosen with This Is Me, a
    guest signed out, or nobody, in which case the sheet's own way into Join is the one
    a phone that never scanned the cabinet's QR still has."""
    identity = state.get("identity")
    players = state.get("players") or []

    @on_page
    async def become(player_id: str) -> None:
        remember_identity(state["target"], player_id)
        sheet.close()
        await state["reread"]()
        redraw()

    @on_page
    async def leave() -> None:
        remember_identity(state["target"], "")
        sheet.close()
        await state["reread"]()
        redraw()

    @on_page
    async def sign_out() -> None:
        if identity is None:
            return
        if not await confirm.ask(
                t("console.players.sign_out_one", name=shown_name(identity)),
                detail=t("console.players.sign_out_detail"),
                confirm=t("console.players.sign_out"), icon=verbs.SIGN_OUT):
            return
        sheet.close()
        try:
            await run.io_bound(client_for_target().remove_player, identity["id"])
        except Exception as exc:
            ui.notify(t("said.could_not_do_that"), caption=why(exc), type="negative")
            return
        remember_identity(state["target"], "")
        await state["reread"]()
        redraw()

    def go_join() -> None:
        sheet.close()
        state["screen"] = JOIN
        redraw()

    with frame.made().props("position=bottom") as sheet, \
            ui.card().classes("w-full remote-sheet"):
        if identity is None:
            ui.label(t("console.remote.who_is_this")).classes("remote-headline")
            for player in (one for one in players if kind_of(one) == ""):
                panel.remote_action(shown_name(player),
                                    lambda _e=None, pid=player["id"]: become(pid),
                                    icon=verbs.THIS_IS_ME,
                                    hint=t("console.remote.this_is_me.help"))
            panel.remote_action(t("console.remote.join_as_guest"), go_join, icon=verbs.JOIN,
                                hint=t("console.remote.join_as_guest.help"))
        else:
            ui.label(t("console.remote.youre", name=shown_name(identity))) \
                .classes("remote-headline")
            if identity.get("guest"):
                panel.remote_action(t("console.players.sign_out"), sign_out,
                                    icon=verbs.SIGN_OUT,
                                    hint=t("console.players.sign_out.help"))
                _guest_accounts(state, identity, client_for_target, redraw, sheet)
            else:
                panel.remote_action(t("console.remote.not_me"), leave, icon=verbs.NOT_ME,
                                    hint=t("console.remote.not_me.help"))
    sheet.open()


def _guest_accounts(state: dict[str, Any], identity: dict[str, Any],
                    client_for_target: Callable[[], Any], redraw: Callable[[], None],
                    sheet: Any) -> None:
    """Where a visitor who joined with Just Initials gets a card: typing a user id makes
    one, and once it is made, Save Card is how it leaves this phone. A guest who joined
    with a card already shares and already has one on their phone, so neither is offered
    - `account.share` alone decides, with no memory of how they joined."""
    @on_page
    async def share(account: dict[str, Any]) -> None:
        if await _share_with(state, identity, account, client_for_target, redraw):
            sheet.close()

    for account in state.get("accounts") or []:
        if account.get("share"):
            if account.get("card"):
                panel.remote_action(
                    t("console.players.save_card"),
                    lambda _e=None, account=account:
                        save_card(Library(client_for_target()), identity, account),
                    icon=verbs.FETCH,
                    hint=t("console.players.save_card.help"))
            continue
        service = str(account.get("label") or account["extension"])
        panel.remote_action(t("console.remote.share_with", service=service),
                            lambda _e=None, account=account: share(account),
                            icon=verbs.SHARE,
                            hint=t("console.remote.share_with.help"))


async def _share_with(state: dict[str, Any], identity: dict[str, Any],
                      account: dict[str, Any], client_for_target: Callable[[], Any],
                      redraw: Callable[[], None]) -> bool:
    """A user id, and VPinPlay makes a key for it the same way it does from the Console
    (`extensions/vpinplay/accounts.py`'s `write_account`) - core does not mint one.
    Answers whether it went through, so the identity sheet behind it knows to close."""
    extension = str(account["extension"])
    service = str(account.get("label") or extension)
    about: dict[str, Any] = next(
        (one for one in account.get("fields") or [] if one.get("key") == "user_id"), {})

    @on_page
    async def go() -> None:
        typed = str(control.value or "").strip()
        if not typed:
            return
        library = Library(client_for_target())
        try:
            await run.io_bound(library.put_account, identity["id"], extension,
                               {"user_id": typed})
            await run.io_bound(library.put_share, identity["id"], extension, True)
        except Exception as exc:
            ui.notify(t("said.could_not_save_it"), caption=why(exc), type="negative")
            return
        box.submit(True)

    with _asked(t("console.remote.share_with_title", service=service)) as box:
        ui.label(share_help(account)).classes("console-help px-3")
        if about.get("help"):
            ui.label(str(about["help"])).classes("console-help px-3")
        control = frame.field(placeholder=str(about.get("label") or ""))
        with frame.footer():
            frame.cancel(lambda: box.submit(False))
            answered = frame.answer(t("console.remote.share"), go, icon=verbs.SHARE)
    frame.focus(box, control)
    frame.enter_presses(answered)
    went = bool(await box)
    if went:
        await state["reread"]()
        redraw()
    return went


def _screen(state: dict[str, Any],
            client_for_target: Callable[[], Any],
            redraw: Callable[[], None]) -> None:
    if not state["target"]:
        return _nothing(t("console.remote.nothing_drive"))
    if state.get("reachable") is False:
        # Said before anything is pressed rather than as the answer to a press: a target
        # that is not there is a fact about the screen, not a failed request.
        return _unreachable(state, redraw)
    if state["screen"] == NOW:
        _now(state, client_for_target, redraw)
    elif state["screen"] == PLAY:
        _play(state, client_for_target, redraw)
    elif state["screen"] == JOIN:
        _join(state, client_for_target, redraw)
    else:
        _control(state, client_for_target, redraw)


def _nothing(said: str) -> None:
    with ui.column().classes("w-full items-center justify-center grow gap-2 p-6"):
        ui.label(said).classes("remote-empty text-center")


def _unreachable(state: dict[str, Any], redraw: Callable[[], None]) -> None:
    """The target is not there, and the way out is to ask it again.

    Nothing here says *why*: this end cannot tell a machine that is switched off from
    one whose network dropped, and a guess dressed as a diagnosis is worse than the
    plain fact. What it can offer is the thing somebody does next, which is switch the
    machine on and ask again.

    The picker upstream does not mark a dead target, and deliberately. `last_reachable`
    says when a device last answered, and a device recorded a moment ago has a fresh
    timestamp whether or not it is on - so a mark drawn from it would call this one
    alive. Asking is the only thing that knows.
    """
    async def again() -> None:
        await state["reread"]()
        redraw()

    with ui.column().classes("w-full items-center justify-center grow gap-3 p-6"):
        ui.label(t("console.remote.not_answering", target_name=(target_name(state['target'])))) \
            .classes("remote-empty text-center")
        ui.button(t("console.remote.try"), icon=verbs.REFRESH, on_click=again) \
            .props("no-caps flat").classes("remote-action")


def _now(state: dict[str, Any],
         client_for_target: Callable[[], Any],
         redraw: Callable[[], None]) -> None:
    """What this machine is doing, and the one thing worth doing about it.

    What is playing, what work is running and anything wanting attention are three
    answers to one question - what is this machine doing - so they are one screen. Split
    apart, this one has nothing to say most of the time.
    """
    play = state.get("play") or {}
    run_now = state.get("run") or {}
    with ui.column().classes("w-full gap-3 p-3"):
        if state.get("reviewing"):
            remote_record.controller(state, client_for_target, redraw)
        elif remote_record.going(run_now):
            remote_record.run_card(state, client_for_target, redraw)
        else:
            if play.get("launching"):
                _playing(play, state, client_for_target, redraw)
            elif frontend_closed(state.get("frontend")):
                with ui.column().classes("w-full gap-1 console-card"):
                    ui.label(t("console.remote.frontend_closed")).classes("remote-empty")
            if run_now:
                remote_record.run_card(state, client_for_target, redraw)
            elif state.get("waiting"):
                remote_record.waiting_card(
                    state, client_for_target, redraw,
                    reviewable=mirroring(state.get("frontend")) and not play.get("launching"))
            if not play.get("launching"):
                _up_section(state, client_for_target, redraw)
                if state.get("result"):
                    _result_card(state, client_for_target, redraw)
                else:
                    _idle(state, client_for_target, redraw)
        _running_jobs(state)


def takes_pictures(play: dict[str, Any], showing: dict[str, Any] | None) -> bool:
    """Whether a table is up that a player can take a picture of from here."""
    return (bool(play.get("launching")) and play.get("source") != SOURCE_CAPTURE
            and not frontend_closed(showing))


def _playing(play: dict[str, Any], state: dict[str, Any], client_for_target: Callable[[], Any],
             redraw: Callable[[], None], note: str = "") -> None:
    if play.get("source") == SOURCE_CAPTURE and remote_record.going(state.get("run") or {}):
        remote_record.run_card(state, client_for_target, redraw)
        return

    @on_page
    async def quit_table() -> None:
        try:
            await run.io_bound(client_for_target().stop_play)
        except Exception as exc:
            ui.notify(t("console.remote.could_not_quit"), caption=why(exc), type="negative")
            return
        state["play"] = await offload.io(client_for_target().play_state)
        redraw()

    paused = bool(play.get("paused"))
    with ui.column().classes("w-full gap-1 console-card"):
        ui.label(t("console.remote.paused" if paused else "console.remote.playing")) \
            .classes("console-card-title")
        ui.label(str(play.get("game_name") or t("console.remote.table"))) \
            .classes("remote-headline")
        if note:
            ui.label(note).classes("remote-note")
    if takes_pictures(play, state.get("frontend")):
        _tap_button("take_picture", client_for_target, icon=verbs.TAKE_PICTURE, primary=True)
        if paused:
            _tap_button("back", client_for_target, icon=verbs.BACK)
    ui.button(t("console.remote.quit_table"), icon=verbs.STOP, on_click=quit_table) \
        .props("no-caps flat").classes("remote-action remote-action--danger")


def _rating_of(game_id: str, game: dict[str, Any], identity: dict[str, Any] | None,
               record: dict[str, dict[str, Any]]) -> int:
    """The stars to show."""
    if is_someone_else(identity):
        return int((record.get(game_id) or {}).get("rating") or 0)
    return int((game.get("user") or {}).get("rating") or 0)


async def _rate(client: ApiClient, identity: dict[str, Any] | None,
                game_id: str, value: int) -> None:
    """Writes the rating `_rating_of` reads back."""
    if identity is not None and is_someone_else(identity):
        await run.io_bound(client.player_rating, str(identity["id"]), game_id, value)
    else:
        await run.io_bound(client.rate, game_id, value)


def _up_section(state: dict[str, Any], client_for_target: Callable[[], Any],
                redraw: Callable[[], None]) -> None:
    """Who the next game counts for. Nothing to toggle with one player in the roster."""
    players = state.get("players") or []
    if len(players) <= 1:
        return
    identity = state.get("identity")

    @on_page
    async def toggle(player_id: str, up: bool) -> None:
        try:
            state["players"] = await run.io_bound(
                client_for_target().set_player_up, player_id, up)
        except Exception as exc:
            ui.notify(t("said.could_not_save_it"), caption=why(exc), type="negative")
            return
        redraw()

    def flip(player_id: str) -> Callable[[Any], Any]:
        return lambda e: toggle(player_id, bool(e.value))

    if identity is not None:
        mine = next((one for one in players if one.get("id") == identity.get("id")),
                    identity)
        if not mine.get("up"):
            with ui.column().classes("w-full gap-2 console-card"):
                panel.remote_action(t("console.remote.im_up"),
                                    lambda: toggle(str(mine["id"]), True),
                                    icon=verbs.ACCEPT, primary=True,
                                    hint=t("console.remote.im_up.help"))
            return
        if identity.get("guest"):
            with ui.row().classes("w-full items-center justify-between console-card"):
                ui.label(shown_name(mine)).classes("remote-headline")
                panel.switch(True, flip(str(mine["id"])))()
            return

    with ui.column().classes("w-full gap-0 console-card"):
        ui.label(t("console.players.up")).classes("console-card-title")
        for player in players:
            with ui.row().classes("w-full items-center justify-between remote-up-row"):
                ui.label(shown_name(player)).classes("remote-row-name")
                panel.switch(bool(player.get("up")), flip(str(player["id"])))()


def _idle(state: dict[str, Any], client_for_target: Callable[[], Any],
          redraw: Callable[[], None]) -> None:
    """Nothing is playing, so this offers the one thing worth doing about that.

    The last game played, with its rating. That is the moment somebody has an opinion
    about a table and the phone is already in their hand, and it is the only reason this
    screen has anything to say when the machine is quiet. Superseded by the result card
    the moment a play is recorded this session - this is what is left to say before that
    has happened even once.
    """
    game = last_played(state.get("games") or [])
    if not game:
        with ui.column().classes("w-full gap-1 console-card"):
            ui.label(t("console.remote.nothing_playing")).classes("remote-headline")
        return
    identity = state.get("identity")

    @on_page
    async def rate(value: int) -> None:
        try:
            await _rate(client_for_target(), identity, str(game["id"]), value)
        except Exception as exc:
            ui.notify(t("console.stars.could_not_save_rating"), caption=why(exc),
                      type="negative")
            return
        if is_someone_else(identity):
            state.setdefault("record", {}).setdefault(str(game["id"]), {})["rating"] = value
        else:
            game.setdefault("user", {})["rating"] = value
        redraw()

    with ui.column().classes("w-full gap-2 console-card"):
        ui.label(t("word.last_played")).classes("console-card-title")
        ui.label(str(game.get("name") or "")).classes("remote-headline")
        stars.draw(_rating_of(str(game["id"]), game, identity, state.get("record") or {}),
                  rate)()


def _visible_up(identity: dict[str, Any] | None,
                up: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Which of who was up belongs on this phone's result card: everyone for
    nobody said or the owner, theirs first for a kept player, theirs alone for a guest -
    and nothing for a kept player who was not part of this play, the same reason a guest
    sees nothing of somebody else's."""
    if identity is None:
        return list(up)
    player_id = str(identity.get("id") or "")
    mine = next((one for one in up if str(one.get("id") or "") == player_id), None)
    if mine is None:
        return []
    if identity.get("guest"):
        return [mine]
    return [mine, *(one for one in up if str(one.get("id") or "") != player_id)]


def _send_status(account: dict[str, Any], *, credited: bool, several_up: bool) -> str:
    """Empty for an account that is not sharing."""
    if not account.get("share"):
        return ""
    service = str(account.get("label") or account.get("extension") or "")
    if several_up and not credited:
        return t("console.remote.not_sent_one_per_game", service=service)
    if account.get("waiting"):
        return t("console.remote.waiting_to_send")
    return t("console.remote.sent_to", service=service)


async def _play_recorded(state: dict[str, Any], payload: dict[str, Any],
                         client_for_target: Callable[[], Any],
                         redraw: Callable[[], None]) -> None:
    """`table.play_recorded`: build the result card for whichever of who was up belongs
    on this phone, and show it the moment Now is open - or the moment it is next opened,
    since it replaces the idle card until superseded by the next one."""
    up = list(payload.get("up") or [])
    visible = _visible_up(state.get("identity"), up)
    if not visible:
        return
    credited = {str((one.get("player") or {}).get("id") or "")
               for one in payload.get("new_entries") or []}
    entries_of = {str((one.get("player") or {}).get("id") or ""): one.get("entries") or []
                 for one in payload.get("new_entries") or []}
    private = bool(payload.get("private"))
    several = len(up) > 1
    rows = []
    for player in visible:
        player_id = str(player.get("id") or "")
        got = player_id in credited
        line = ""
        if got and entries_of.get(player_id):
            from console import workbench
            line = workbench._score_lines(entries_of[player_id][0])[0]
        statuses: list[str] = []
        if not private:
            try:
                accounts = await offload.io(client_for_target().player_accounts, player_id)
            except Exception as exc:
                logger.info("remote: could not read %s's accounts: %s", player_id, exc)
                accounts = []
            statuses = [said for said in
                       (_send_status(one, credited=got, several_up=several)
                        for one in accounts) if said]
        rows.append({"player": player, "entry": line, "statuses": statuses})
    game = payload.get("game") or {}
    state["result"] = {"game_id": str(game.get("id") or ""),
                       "game_name": str(game.get("name") or ""), "players": rows}
    if state["screen"] == NOW:
        redraw()


def _result_card(state: dict[str, Any], client_for_target: Callable[[], Any],
                 redraw: Callable[[], None]) -> None:
    """What became of the play just recorded, for each player the result card is
    showing - their new entry where they made one, and what each of their sharing
    accounts did with it. The phone's own row carries the rating control the idle card
    used to; nobody else's does; stars are always about the one screen they are on."""
    result = state.get("result") or {}
    rows = result.get("players") or []
    if not rows:
        return
    identity = state.get("identity")
    game_id = str(result.get("game_id") or "")
    if identity is None:
        mine = next((row for row in rows if row["player"].get("owner")), None)
    else:
        mine = next((row for row in rows
                    if str(row["player"].get("id") or "") == str(identity.get("id") or "")),
                    None)

    @on_page
    async def rate(value: int) -> None:
        try:
            await _rate(client_for_target(), identity, game_id, value)
        except Exception as exc:
            ui.notify(t("console.stars.could_not_save_rating"), caption=why(exc),
                      type="negative")
            return
        if is_someone_else(identity):
            state.setdefault("record", {}).setdefault(game_id, {})["rating"] = value
        else:
            for game in state.get("games") or []:
                if str(game.get("id") or "") == game_id:
                    game.setdefault("user", {})["rating"] = value
        redraw()

    with ui.column().classes("w-full gap-2 console-card"):
        ui.label(str(result.get("game_name") or "")).classes("console-card-title")
        for row in rows:
            with ui.column().classes("w-full gap-0"):
                ui.label(shown_name(row["player"])).classes("remote-headline")
                if row.get("entry"):
                    ui.label(row["entry"]).classes("remote-note")
                for said in row.get("statuses") or []:
                    ui.label(said).classes("remote-note")
        if mine is not None:
            stars.draw(_rating_of(game_id, mine["player"], identity,
                                  state.get("record") or {}), rate)()


def _running_jobs(state: dict[str, Any]) -> None:
    """Only what is still going. A finished job is not news on a screen this size, and
    a list that keeps yesterday's work is a list nobody reads."""
    for job in state.get("jobs") or []:
        if str(job.get("state") or "") != "running" or job.get("kind") == remote_record.KIND:
            continue
        with ui.column().classes("w-full gap-2 console-card"):
            ui.label(t("word.running")).classes("console-card-title")
            # The kind is a wire word - `library.scan` - and nothing on this surface
            # shows one. A percentage says more than the name does anyway, so the name
            # is the label and the bar is the answer.
            ui.label(humanize(str(job.get("kind") or "").replace(".", " "))) \
                .classes("remote-headline")
            ui.linear_progress(value=float(job.get("pct") or 0) / 100,
                               show_value=False).props("rounded")
            if job.get("message"):
                ui.label(str(job["message"])).classes("remote-note")


# What the list will draw before it asks you to narrow it. A phone renders every row it
# is given, and a library is longer than a screen by design - the answer to a long list
# is typing into it, not scrolling it.
SHOWN_AT_ONCE = 40


def matching(games: list[dict[str, Any]], said: str) -> list[dict[str, Any]]:
    """The games a typed word finds.

    Name, maker and year, because those are the three things somebody standing at a
    machine knows about it. Every word has to land somewhere, so "bally 1991" narrows
    rather than widening - which is what a person means by typing a second word.
    """
    words = said.lower().split()
    if not words:
        return games
    found = []
    for game in games:
        against = " ".join(str(game.get(key) or "")
                           for key in ("name", "manufacturer", "year")).lower()
        if all(word in against for word in words):
            found.append(game)
    return found


def offered_games(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    found = []
    for entry in entries:
        game = entry.get("game") or {}
        game_id = str(game.get("id") or "")
        if game_id and game_id not in seen:
            seen.add(game_id)
            found.append(game)
    return found


def frontend_collections(collections: list[dict[str, Any]], chosen: str = "") -> list[str]:
    return [str(one.get("name") or "") for one in collections
            if one.get("name") and (one.get("in_frontend", True) or one.get("name") == chosen)]


def in_collection(games: list[dict[str, Any]],
                  ids: set[str] | None) -> list[dict[str, Any]]:
    """Narrowed to one collection, or left alone where none is chosen."""
    return games if ids is None else [one for one in games if one.get("id") in ids]


def manual_collections(collections: list[dict[str, Any]]) -> list[str]:
    """The ones a game can simply be put in.

    A filter collection is a rule, and pinning a game against a rule is a curator's
    decision made with the rule in view. That is desk work, and the posture line falls
    where it falls everywhere else here.
    """
    return [str(one.get("name") or "") for one in collections
            if str(one.get("type") or "") == "manual" and one.get("name")]


def _play(state: dict[str, Any],
          client_for_target: Callable[[], Any],
          redraw: Callable[[], None]) -> None:
    """Find a game and start it.

    The search field is first because the library is longer than a screen, and a list
    longer than a screen is typed into rather than scrolled.

    Where the frontend is up, the collection is the one it is showing, both ways.
    """
    # Not redraw(): a field rebuilt under the cursor drops the focus mid-word.
    async def typed(event: Any) -> None:
        state["find"] = str(event.value or "")
        listed()

    @on_page
    async def narrow(event: Any) -> None:
        name = str(event.value or "")
        # Taken before anything is awaited, so the frontend's own report of this switch
        # finds the phone already on it rather than switching it a second time.
        state["collection"] = name
        showing = state.get("frontend")
        if mirroring(showing) and name != str((showing or {}).get("collection") or ""):
            try:
                await run.io_bound(client_for_target().show_on_frontend, name)
            except Exception as exc:
                ui.notify(t("console.remote.could_not_show"), caption=why(exc),
                          type="negative")
        try:
            state.update(await offload.io(_narrowed_to, client_for_target(), name))
        except Exception as exc:
            state["collection_ids"] = None
            ui.notify(t("console.remote.could_not_read_collection"), caption=why(exc),
                      type="negative")
        listed()

    def picked() -> None:
        picker.clear()
        named = frontend_collections(state.get("collections") or [],
                                    state.get("collection") or "")
        if not named:
            return
        with picker:
            ui.select({"": t("console.remote.all_games")} | {name: name for name in named},
                      value=state.get("collection") or "", on_change=narrow) \
                .props("dense outlined options-dense").classes("w-full")

    def listed() -> None:
        listing.clear()
        with listing:
            _game_list(in_collection(matching(state.get("games") or [],
                                              state.get("find") or ""),
                                     state.get("collection_ids")),
                       state, client_for_target, redraw)

    def relist() -> None:
        picked()
        listed()

    with ui.column().classes("w-full gap-2 p-3"):
        ui.input(placeholder=t("console.remote.find_game"), value=state.get("find") or "",
                 on_change=typed) \
            .props("dense outlined clearable inputmode=search").classes("w-full")
        picker = ui.column().classes("w-full gap-0")
    listing = ui.column().classes("w-full gap-0")
    state["relist"] = relist
    relist()


def _game_list(found: list[dict[str, Any]], state: dict[str, Any],
               client_for_target: Callable[[], Any], redraw: Callable[[], None]) -> None:
    state["rows"] = {}
    if not found:
        return _nothing(t("console.remote.nothing_name") if state.get("find")
                        else t("console.remote.nothing_in_collection"))
    with ui.column().classes("w-full gap-0"):
        for game in found[:SHOWN_AT_ONCE]:
            _game_row(game, state, client_for_target, redraw)
        left = len(found) - SHOWN_AT_ONCE
        if left > 0:
            # The count, not a "load more": what is wanted is one game, and typing two
            # more letters reaches it faster than paging to it does.
            ui.label(t("console.remote.more_keep_typing", left=(left))).classes("remote-note p-3")


def _game_row(game: dict[str, Any], state: dict[str, Any], client_for_target: Callable[[], Any],
              redraw: Callable[[], None]) -> None:
    """One game. Where the frontend is up, a tap moves the wheel to it; a tap on the one
    already there, or one the wheel refuses, opens it instead.

    Never tap-to-launch. A mis-tap that opens a sheet costs a tap to undo; a mis-tap
    that starts a table takes the machine away from whoever is on it.
    """
    game_id = str(game.get("id") or "")

    @on_page
    async def tapped(_event: Any = None) -> None:
        showing = state.get("frontend")
        if mirroring(showing) and game_id != wheel_id(showing):
            try:
                await run.io_bound(client_for_target().move_wheel, game_id)
                return
            except Exception as exc:
                logger.info("remote: the wheel did not move to %s: %s", game_id, exc)
        _game_sheet(game, state, client_for_target, redraw)

    here = game_id == wheel_id(state.get("frontend"))
    with ui.row().on("click", tapped) \
            .classes("w-full items-center gap-2 no-wrap remote-row"
                     + (" remote-row--here" if here else "")) as row:
        with ui.column().classes("grow min-w-0 gap-0"):
            ui.label(str(game.get("name") or "")).classes("remote-row-name truncate")
            made = game_tables.made(game)
            if made:
                ui.label(made).classes("remote-note truncate")
        if (game.get("user") or {}).get("favorite"):
            ui.icon("favorite").classes("remote-row-mark")
    state["rows"][game_id] = row


def _mark_here(rows: dict[str, Any], was: str, now: str) -> None:
    """Move the wheel's mark between rows without rebuilding the list under a thumb."""
    if was != now and was in rows:
        rows[was].classes(remove="remote-row--here")
    if now in rows:
        rows[now].classes(add="remote-row--here")


def _game_sheet(game: dict[str, Any], state: dict[str, Any], client_for_target: Callable[[], Any],
                redraw: Callable[[], None]) -> None:
    """One game, everything that can be done to it from here, and Launch at the foot.

    A sheet from the bottom rather than a screen of its own: what is being decided is
    about the row you just touched, and pushing a screen would take the list away to
    answer a question about one line of it.
    """
    with frame.made().props("position=bottom") as sheet, \
            ui.card().classes("w-full remote-sheet"):
        ui.label(str(game.get("name") or "")).classes("remote-headline")
        made = game_tables.made(game)
        if made:
            ui.label(made).classes("remote-note")
        lacks = ui.label("").classes("remote-note")
        lacks.set_visibility(False)
        identity = state.get("identity")
        someone_else = is_someone_else(identity)

        @on_page
        async def write(call: Any, *args: Any) -> bool:
            try:
                await run.io_bound(call, *args)
            except Exception as exc:
                ui.notify(t("said.could_not_save_it"), caption=why(exc), type="negative")
                return False
            return True

        @on_page
        async def rate(value: int) -> None:
            try:
                await _rate(client_for_target(), identity, str(game["id"]), value)
            except Exception as exc:
                ui.notify(t("said.could_not_save_it"), caption=why(exc), type="negative")
                return
            if someone_else:
                state.setdefault("record", {}).setdefault(str(game["id"]), {})["rating"] = value
            else:
                game.setdefault("user", {})["rating"] = value
            sheet.close()
            redraw()

        stars.draw(_rating_of(str(game["id"]), game, identity, state.get("record") or {}),
                  rate)()

        if not someone_else:
            held = bool((game.get("user") or {}).get("favorite"))

            async def favor() -> None:
                if await write(client_for_target().set_favorite, game["id"], not held):
                    game.setdefault("user", {})["favorite"] = not held
                    sheet.close()
                    redraw()

            ui.button(t("word.favorite") if not held else t("console.remote.remove_favorite"),
                      icon="favorite" if not held else "favorite_border",
                      on_click=favor) \
                .props("no-caps flat").classes("remote-action")

        if not (identity is not None and identity.get("guest")):
            _add_to_collection(game, state, sheet, write, client_for_target)

        async def started() -> None:
            sheet.close()
            state["screen"] = NOW
            state["run"] = await offload.io(client_for_target().capture_run)
            redraw()

        remote_record.sheet_entry(game, state, client_for_target, lacks, started)
        _launch_button(game, state, client_for_target, redraw,
                       cls="remote-action remote-action--primary", then=sheet.close)
    sheet.open()


def _launch_button(game: dict[str, Any], state: dict[str, Any],
                   client_for_target: Callable[[], Any], redraw: Callable[[], None], *,
                   cls: str, then: Callable[[], Any] = lambda: None) -> None:
    """Launch, at the foot of the sheet and beside the game on the wheel alike. Once it
    has started, Now is where the table is quit from."""
    @on_page
    async def launch() -> None:
        try:
            await run.io_bound(client_for_target().launch, game["id"])
        except Exception as exc:
            ui.notify(t("console.remote.could_not_launch"), caption=why(exc), type="negative")
            return
        then()
        state["screen"] = NOW
        state["play"] = await offload.io(client_for_target().play_state)
        redraw()

    ui.button(t("console.remote.launch"), icon="play_arrow", on_click=launch) \
        .props("no-caps unelevated color=primary").classes(cls)


def _add_to_collection(game: dict[str, Any], state: dict[str, Any], sheet: Any,
                       write: Any, client_for_target: Callable[[], Any]) -> None:
    """Put it in a list you keep.

    Shown disabled with the reason rather than hidden when there is nowhere to put it:
    an action that vanishes leaves somebody wondering whether this surface can do it at
    all, and the answer is that it can once there is a list to add to.
    """
    named = manual_collections(state.get("collections") or [])
    if not named:
        ui.button(t("console.remote.add_collection"), icon=verbs.ADD_TO_LIST) \
            .props("no-caps flat disable").classes("remote-action") \
            .tooltip(t("console.remote.no_hand_picked_yet"))
        return

    @on_page
    async def add(name: str) -> None:
        if await write(client_for_target().add_to_collection, name, game["id"]):
            ui.notify(t("console.remote.added", name=(name)), type="positive")
            sheet.close()

    with ui.button(t("console.remote.add_collection"), icon=verbs.ADD_TO_LIST) \
            .props("no-caps flat").classes("remote-action"):
        with ui.menu():
            for name in named:
                ui.menu_item(name, on_click=lambda _e=None, name=name: add(name)) \
                    .classes("console-menu-item")


# What each button asks for, in the words a person would use rather than the vocabulary
# the wire carries. `collection_menu` is the wheel's list of collections; on screen it is
# what that list is called.
BUTTON_WORDS = {
    "select": t("console.remote.select"),
    "back": t("word.back"),
    "take_picture": t("input.take_picture.label"),
    "menu": t("console.remote.menu"),
    "collection_menu": t("console.remote.collections"),
    "tutorial": t("word.tutorial"),
    "exit": t("console.remote.quit_vpinfe"),
}

# The four that keep going while a thumb is down. The same four core repeats, and for
# the same reason: a hold means "keep going", and going is something only these do.
HELD_ACTIONS = ("previous", "next", "page_previous", "page_next")

# How often a held button says it is still held. A third of the time to live, so a
# renewal has to be lost twice running before the install lets go.
RENEW_MS = 500

# Press and release from a thumb, and the renewal in between.
#
# Client-side because a hold is a gesture, not a request: the browser is what knows the
# thumb is still down, and a server that had to infer it from the last message would be
# guessing at exactly the moment a wheel is moving. What it sends is what the seam
# expects - one press, renewed, then one release.
_HOLD_SCRIPT = """
if (!window.__vpinRemoteHold) {
  window.__vpinRemoteHold = true;
  const held = new Map();
  const letGo = (action) => {
    const timer = held.get(action);
    if (timer === undefined) return;
    clearInterval(timer);
    held.delete(action);
    emitEvent('remote_release', {action});
  };
  const takeHold = (action) => {
    if (held.has(action)) return;
    emitEvent('remote_press', {action});
    held.set(action, setInterval(() => emitEvent('remote_press', {action}), %(renew)d));
  };
  const actionAt = (target) => {
    const el = target && target.closest ? target.closest('[data-hold-action]') : null;
    return el ? el.dataset.holdAction : '';
  };
  document.addEventListener('pointerdown', (e) => {
    const action = actionAt(e.target);
    if (action) { e.preventDefault(); takeHold(action); }
  });
  // Every way a thumb can stop being on the button, including sliding off it and the
  // browser taking the pointer away for a scroll. A release that is never sent is the
  // failure the install's own expiry exists to catch, and this is the half that keeps
  // it from happening in the first place.
  for (const name of ['pointerup', 'pointercancel', 'pointerleave']) {
    document.addEventListener(name, (e) => {
      const action = actionAt(e.target);
      if (action) letGo(action);
    });
  }
  // The page going away with a thumb down: a phone locking its screen is the common
  // one, and it is why the press expires at the other end as well.
  document.addEventListener('visibilitychange', () => {
    if (document.hidden) [...held.keys()].forEach(letGo);
  });
  window.addEventListener('blur', () => [...held.keys()].forEach(letGo));
}
"""


def _control(state: dict[str, Any],
             client_for_target: Callable[[], Any],
             redraw: Callable[[], None]) -> None:
    """Drive the frontend from here.

    Not the table. In-game input is VPX's own and reaches it as keystrokes; what these
    buttons produce is an action on the install's bus, addressed at the machine the
    header names. Keeping the two apart is what stops a press meaning one thing on the
    wheel and another inside a game.
    """
    target = state["target"]
    if str(target.get("kind") or "") == device_registry.KIND_VPX_MOBILE:
        # Said rather than shown as dead buttons: this is a real target and it really
        # can be played on, which is a different thing from being driveable.
        return _nothing(t("console.remote.plays_tables_not_run",
                target_name=(target_name(target))))

    play = state.get("play") or {}
    if play.get("launching"):
        # Honest, and not a guess: the frontend stops listening for the length of a
        # launch, so every button here would do nothing and report success.
        return _playing_instead(play, state, client_for_target, redraw)
    if frontend_closed(state.get("frontend")):
        # The same reason: a press goes to the windows alone, so with none up every
        # button here reports success and nothing hears it.
        return _nothing(t("console.remote.frontend_closed"))

    with ui.column().classes("w-full items-center gap-4 p-3"):
        _pad(client_for_target)
        with ui.column().classes("w-full gap-2"):
            for action in ("back", "menu", "collection_menu", "tutorial"):
                _tap_button(action, client_for_target)
        # Apart from the rest and in the danger color: it ends the thing every other
        # button on this screen is for.
        _tap_button("exit", client_for_target, danger=True)


def _playing_instead(play: dict[str, Any], state: dict[str, Any],
                     client_for_target: Callable[[], Any],
                     redraw: Callable[[], None]) -> None:
    with ui.column().classes("w-full gap-3 p-3"):
        _playing(play, state, client_for_target, redraw,
                 note=t("console.remote.wheel_not_listening_while"))


def _pad(client_for_target: Callable[[], Any]) -> None:
    """The four directions and select, laid out as they move.

    A cross rather than a list, because what these do is spatial - left and right step
    the wheel, up and down jump it a page - and a list of five words makes the reader
    translate a direction into a name every time.
    """
    with ui.element("div").classes("remote-pad"):
        _held_button("page_previous", "keyboard_arrow_up", "remote-pad-up")
        _held_button("previous", "keyboard_arrow_left", "remote-pad-left")
        _tap_button("select", client_for_target, cls="remote-pad-mid", icon_only=True)
        _held_button("next", "keyboard_arrow_right", "remote-pad-right")
        _held_button("page_next", "keyboard_arrow_down", "remote-pad-down")


def _held_button(action: str, icon: str, cls: str) -> None:
    """A direction. Held down, it keeps going - the curve for that lives in the install,
    so it feels the same from a thumb as it does from a flipper or a key."""
    ui.button(icon=icon).props("flat round") \
        .classes(f"remote-pad-key {cls}") \
        .props(f'data-hold-action={action}')


def _tap_button(action: str, client_for_target: Callable[[], Any], *, danger: bool = False,
                cls: str = "", icon_only: bool = False, icon: str = "",
                primary: bool = False) -> None:
    async def tap() -> None:
        await _say(client_for_target, action, "tap")

    said = BUTTON_WORDS.get(action, action)
    button = ui.button(on_click=tap, icon=icon or None)
    if icon_only:
        button.props("flat round").classes(f"remote-pad-key {cls}").tooltip(said)
        with button:
            ui.icon("radio_button_checked")
        return
    if primary:
        button.props("no-caps unelevated color=primary") \
            .classes("remote-action remote-action--primary").set_text(said)
        return
    # Flat either way: filled is what the one action a screen is *for* wears, and on
    # Control that is the pad. A destructive button drawn louder than everything
    # around it is the one a thumb finds by accident.
    button.props("no-caps flat") \
        .classes("remote-action" + (" remote-action--danger" if danger else "")) \
        .set_text(said)


async def _say(client_for_target: Callable[[], Any], action: str, phase: str) -> None:
    """One press, one renewal or one release, at whichever machine is aimed at.

    A failure is reported once and the gesture is abandoned rather than retried: a
    renewal that cannot be delivered means the target has gone, and the install lets go
    on its own the moment the renewals stop.
    """
    if not action:
        return
    try:
        await run.io_bound(client_for_target().press_input, action, phase,
                           ttl_ms=RENEW_MS * 3)
    except Exception as exc:
        logger.info("remote: %s %s did not reach the target: %s", action, phase, exc)


def _join(state: dict[str, Any], client_for_target: Callable[[], Any],
         redraw: Callable[[], None]) -> None:
    """The Join screen: Use My Card, read as 2.x reads it, or Just Initials."""

    @on_page
    async def joined(said: dict[str, Any]) -> None:
        player = dict(said or {})
        remember_identity(state["target"], str(player.get("id") or ""))
        ui.notify(t("console.remote.youre_up", initials=str(player.get("initials") or "")),
                  type="positive")
        state["screen"] = NOW
        await state["reread"]()
        redraw()

    @on_page
    async def with_card(event: Any) -> None:
        text = (await event.file.read()).decode("utf-8", "replace")
        try:
            said = await run.io_bound(client_for_target().add_guest_from_card, text)
        except Exception as exc:
            ui.notify(t("console.remote.could_not_join"), caption=why(exc), type="negative")
            return
        await joined(said or {})

    @on_page
    async def just_initials() -> None:
        with _asked(t("console.players.just_initials")) as box:
            control = frame.field(placeholder=t("console.players.initials_example"))
            control.props("maxlength=3 bottom-slots")

            @on_page
            async def go() -> None:
                try:
                    said = await run.io_bound(client_for_target().add_guest,
                                              str(control.value or "").strip())
                except Exception as exc:
                    control.props["error"] = True
                    control.props["error-message"] = why(exc)
                    control.update()
                    return
                box.submit(said)

            with frame.footer():
                frame.cancel(lambda: box.submit(None))
                answered = frame.answer(t("console.remote.join"), go, icon=verbs.ACCEPT)
        frame.focus(box, control)
        frame.enter_presses(answered)
        said: dict[str, Any] | None = await box
        if said is not None:
            await joined(said)

    with ui.column().classes("w-full gap-4 p-4 items-center text-center"):
        ui.label(t("console.remote.play_as_you",
                   target=target_name(state["target"]))).classes("remote-headline")
        uploader = ui.upload(on_upload=with_card, auto_upload=True).classes("hidden")
        uploader.props(f'accept="{",".join(CARD_FILES)}"')
        uploader.on("finish",
                   js_handler=f"() => getElement({uploader.id}).$refs.qRef.reset()")
        card_button = panel.remote_action(t("console.remote.use_my_card"), icon=verbs.FROM_FILE,
                                          primary=True,
                                          hint=t("console.remote.use_my_card.help"))
        card_button.on("click",
                       js_handler=f"() => getElement({uploader.id}).$refs.qRef.pickFiles()")
        panel.remote_action(t("console.players.just_initials"), just_initials,
                            icon=verbs.INITIALS_ONLY,
                            hint=t("console.players.just_initials.help"))
        ui.label(t("console.remote.guest_until_close")).classes("remote-note")


def where_to_find_it() -> str:
    """The address to hand somebody holding a phone.

    Not the one the Console was reached on: an install is usually administered from the
    machine itself, so that address is loopback and loopback is the one address certain
    not to work from anywhere else.
    """
    from common.host.addresses import best
    from common.paths import get_ini_config

    return best(NetworkConfig.from_config(get_ini_config()).http_port, "/remote")


def _qr_svg(url: str) -> str:
    """The same address as something a camera can read. Empty where it cannot be drawn,
    which the caller shows the plain address for instead."""
    try:
        import qrcode
        from qrcode.image.svg import SvgPathImage
    except Exception:
        return ""
    try:
        code = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M,
                             box_size=8, border=2)
        code.add_data(url)
        code.make(fit=True)
        held = BytesIO()
        code.make_image(image_factory=SvgPathImage).save(held)
        return held.getvalue().decode("utf-8")
    except Exception:
        logger.warning("console: could not draw the remote's address", exc_info=True)
        return ""


def invite(labels: list) -> None:
    """The way somebody finds this surface at all.

    In the Console, because that is where a person configuring an install already is -
    and a phone is exactly the device that will not have found `/remote` by typing. It
    does not reach somebody who never opens the Console on any device; that half is the
    frontend's, and is not built.

    The label joins `labels` so it collapses with the rail and leaves the icon, which is
    the rule every other entry in this drawer follows.
    """
    said = where_to_find_it()
    if not said:
        return

    def show() -> None:
        with frame.made() as sheet, ui.card().classes("console-confirm items-center"):
            ui.label(t("console.remote.vpinfe_phone")).classes("console-confirm-title")
            art = _qr_svg(said)
            if art:
                ui.html(art).classes("console-qr")
            # Always, not only when the drawing failed: a camera is not the only way
            # somebody gets this, and an address nobody can read out is one they cannot
            # type either.
            ui.label(said).classes("console-help text-center")
            ui.button(t("word.close"), icon=verbs.CLOSE, on_click=sheet.close) \
                .props("flat no-caps").classes("console-action")
        sheet.open()

    with ui.row().classes("items-center justify-center gap-2 w-full no-wrap "
                          "console-invite").on("click", show):
        ui.icon("qr_code_2").classes("shrink-0")
        labels.append(ui.label(t("console.remote.phone")).classes("text-xs"))
