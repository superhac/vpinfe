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

import logging
from io import BytesIO
from typing import Any

from nicegui import run, ui

from common import device_registry, install_identity
from common.config_access import NetworkConfig
from common.i18n import t
from common.labels import humanize
from console import stars, theme
from console.api import ApiClient, local_base_url

logger = logging.getLogger("vpinfe.console.remote")

NOW, PLAY, CONTROL = "now", "play", "control"

SCREENS = (
    (NOW, "Now", "radio_button_checked"),
    (PLAY, "Play", "search"),
    (CONTROL, "Control", "gamepad"),
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
    return str(device.get("display_name") or "").strip() or "This machine"


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
    """What the chosen machine is doing and what it can play.

    Asked of the target rather than of this install, because that is the machine the
    launch is going to. Two installs can hold different libraries, and a list read from
    the wrong one offers games whose ids the target has never heard of.
    """
    return {
        "play": client.play_state(),
        "games": client.games(),
        "jobs": client.jobs(),
        "collections": client.collections(),
    }


@ui.page("/remote", title=t("console.remote.vpinfe_remote"), reconnect_timeout=300)
async def remote_page(screen: str = "") -> None:
    """The remote. `screen` names which of the three, so a place can be linked to."""
    ui.dark_mode(True)
    theme.apply_colors(dark=True)
    theme.apply_flair()
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
    # by then the page has been sent, and the pad had no behaviour at all.
    ui.add_body_html(f"<script>{_HOLD_SCRIPT % {'renew': RENEW_MS}}</script>")

    with ui.column().classes("w-full h-full items-center justify-center gap-3") as loading:
        ui.spinner(size="lg").classes("text-primary")
        ui.label(t("console.remote.loading")).classes("text-sm opacity-60")

    await ui.context.client.connected()
    loaded = await run.io_bound(_read_here)
    if ui.context.client.is_deleted:
        # Reading takes long enough that somebody can close the tab inside it, and there
        # is then nothing to draw on. Building anyway raises out of the page function and
        # logs a stack trace for somebody having changed their mind.
        return
    loading.delete()

    local_device_id = loaded["local_device_id"]
    aimable = targets(loaded["devices"], local_device_id)
    state: dict[str, Any] = {
        "screen": screen if screen in {key for key, *_ in SCREENS} else NOW,
        "target": aimable[0] if aimable else {},
        "play": {}, "games": [], "jobs": [], "collections": [],
        "find": "", "collection": "",
    }

    def client_for_target() -> ApiClient:
        """A client aimed at whichever target is chosen. The picker is a base URL."""
        return ApiClient(base_url_of(state["target"], local_device_id) or None)

    async def reread() -> None:
        """Ask the chosen machine again. Failure is a state, not a crash: a target that
        has gone away is the ordinary case for a page held in a hand."""
        if not state["target"]:
            return
        try:
            state.update(await run.io_bound(_read_target, client_for_target()))
            state["reachable"] = True
        except Exception as exc:
            logger.info("remote: %s did not answer: %s",
                        target_name(state["target"]), exc)
            state.update({"play": {}, "games": [], "jobs": [], "collections": [],
                          "reachable": False})

    def redraw() -> None:
        """Both, always. The bar says which screen you are on, so a redraw that rebuilt
        only the screen left the mark behind on the one you came from."""
        body.clear()
        tabs.clear()
        with body:
            _screen(state, client_for_target, redraw)
        with tabs:
            _tabs(state, redraw)

    # Once per page, not once per draw. Registered inside the screen that uses them, a
    # handler would be added again on every redraw and one thumb would send N presses.
    async def held(event) -> None:
        await _say(client_for_target, str((event.args or {}).get("action") or ""),
                   "press")

    async def let_go(event) -> None:
        await _say(client_for_target, str((event.args or {}).get("action") or ""),
                   "release")

    ui.on("remote_press", held)
    ui.on("remote_release", let_go)

    state["reread"] = reread

    async def aim(device: dict[str, Any]) -> None:
        """A different machine is a different library, a different state and a different
        base URL, so everything below the header is read again."""
        state.update({"target": device, "find": "", "collection": ""})
        await reread()
        redraw()

    # Header, then the screen, then the tabs, in that order and inside the shell: the
    # body has to be built here rather than earlier and reparented, because a NiceGUI
    # element belongs to whatever slot was open when it was made.
    with ui.column().classes("w-full h-full gap-0 remote-shell no-wrap"):
        _header(state, aimable, aim)
        body = ui.column().classes(
            "w-full grow min-h-0 gap-0 overflow-auto remote-body")
        tabs = ui.row().classes("w-full items-stretch gap-0 remote-tabs no-wrap")
    await reread()
    redraw()


def _header(state: dict[str, Any], aimable: list[dict[str, Any]],
            aim) -> None:
    """The target, on every screen, because every action's meaning depends on it.

    Drawn as a picker only when there is a choice to make. With one target it is the
    name alone - a select with one option is furniture, which is the same rule that
    keeps a chip off every row.
    """
    with ui.row().classes("w-full items-center gap-2 remote-header no-wrap"):
        ui.icon("sports_esports").classes("remote-mark")
        if len(aimable) > 1:
            names = {one["device_id"]: target_name(one) for one in aimable}
            by_id = {one["device_id"]: one for one in aimable}

            async def chosen(event) -> None:
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
            ui.label(t("console.remote.nothing_to_drive_from_here")) \
                .classes("remote-target-name truncate")


def _tabs(state: dict[str, Any], redraw) -> None:
    """The three screens, at the bottom, where a thumb is.

    Not a nav rail and not a drawer: with three destinations and one hand, the whole map
    is worth the space it takes, and hiding it behind a button charges a tap to find out
    what the page can do.
    """
    for key, label, icon in SCREENS:
        def go(_event=None, key=key) -> None:
            state["screen"] = key
            redraw()

        here = state["screen"] == key
        with ui.column().on("click", go) \
                .classes("remote-tab" + (" remote-tab--here" if here else "")):
            ui.icon(icon).classes("remote-tab-icon")
            ui.label(label).classes("remote-tab-label")


def _screen(state: dict[str, Any], client_for_target, redraw) -> None:
    if not state["target"]:
        return _nothing("Nothing to drive from here")
    if state.get("reachable") is False:
        # Said before anything is pressed rather than as the answer to a press: a target
        # that is not there is a fact about the screen, not a failed request.
        return _unreachable(state, redraw)
    if state["screen"] == NOW:
        _now(state, client_for_target, redraw)
    elif state["screen"] == PLAY:
        _play(state, client_for_target, redraw)
    else:
        _control(state, client_for_target, redraw)


def _nothing(said: str) -> None:
    with ui.column().classes("w-full items-center justify-center grow gap-2 p-6"):
        ui.label(said).classes("remote-empty text-center")


def _unreachable(state: dict[str, Any], redraw) -> None:
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
        ui.label(t("console.remote.is_not_answering", target_name=(target_name(state['target'])))) \
            .classes("remote-empty text-center")
        ui.button(t("console.remote.try_again"), icon="refresh", on_click=again) \
            .props("no-caps flat").classes("remote-action")


def _now(state: dict[str, Any], client_for_target, redraw) -> None:
    """What this machine is doing, and the one thing worth doing about it.

    What is playing, what work is running and anything wanting attention are three
    answers to one question - what is this machine doing - so they are one screen. Split
    apart, this one has nothing to say most of the time.
    """
    play = state.get("play") or {}
    with ui.column().classes("w-full gap-3 p-3"):
        if play.get("launching"):
            _playing(play, state, client_for_target, redraw)
        else:
            _idle(state, redraw)
        _running_jobs(state)


def _playing(play: dict[str, Any], state: dict[str, Any], client_for_target,
             redraw) -> None:
    async def quit_table() -> None:
        try:
            await run.io_bound(client_for_target().stop_play)
        except Exception as exc:
            ui.notify(str(exc), type="negative")
            return
        state["play"] = await run.io_bound(client_for_target().play_state)
        redraw()

    with ui.column().classes("w-full gap-1 console-card"):
        ui.label(t("console.remote.playing")).classes("console-card-title")
        ui.label(str(play.get("game_name") or "A table")).classes("remote-headline")
    ui.button(t("console.remote.quit_table"), on_click=quit_table) \
        .props("no-caps flat").classes("remote-action remote-action--danger")


def _idle(state: dict[str, Any], redraw) -> None:
    """Nothing is playing, so this offers the one thing worth doing about that.

    The last game played, with its rating. That is the moment somebody has an opinion
    about a table and the phone is already in their hand, and it is the only reason this
    screen has anything to say when the machine is quiet.
    """
    game = last_played(state.get("games") or [])
    if not game:
        with ui.column().classes("w-full gap-1 console-card"):
            ui.label(t("console.remote.nothing_playing")).classes("remote-headline")
        return

    async def rate(value: int) -> None:
        try:
            await run.io_bound(ApiClient().rate, game["id"], value)
        except Exception as exc:
            ui.notify(str(exc), type="negative")
            return
        game.setdefault("user", {})["rating"] = value
        redraw()

    with ui.column().classes("w-full gap-2 console-card"):
        ui.label(t("console.remote.last_played")).classes("console-card-title")
        ui.label(str(game.get("name") or "")).classes("remote-headline")
        stars.draw(int((game.get("user") or {}).get("rating") or 0), rate)()


def _running_jobs(state: dict[str, Any]) -> None:
    """Only what is still going. A finished job is not news on a screen this size, and
    a list that keeps yesterday's work is a list nobody reads."""
    for job in state.get("jobs") or []:
        if str(job.get("state") or "") != "running":
            continue
        with ui.column().classes("w-full gap-2 console-card"):
            ui.label(t("console.remote.running")).classes("console-card-title")
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


def _play(state: dict[str, Any], client_for_target, redraw) -> None:
    """Find a game and start it.

    The search field is first because the library is longer than a screen, and a list
    longer than a screen is typed into rather than scrolled.
    """
    async def typed(event) -> None:
        state["find"] = str(event.value or "")
        redraw()

    async def narrow(event) -> None:
        state["collection"] = str(event.value or "")
        state["collection_ids"] = None
        if state["collection"]:
            try:
                found = await run.io_bound(client_for_target().collection_games,
                                           state["collection"])
                state["collection_ids"] = {str(one.get("id") or "") for one in found}
            except Exception as exc:
                ui.notify(str(exc), type="negative")
        redraw()

    with ui.column().classes("w-full gap-2 p-3"):
        ui.input(placeholder=t("console.remote.find_a_game"), value=state.get("find") or "",
                 on_change=typed) \
            .props("dense outlined clearable inputmode=search").classes("w-full")
        named = [one.get("name") for one in state.get("collections") or []
                 if one.get("name")]
        if named:
            ui.select({"": "Whole library"} | {name: name for name in named},
                      value=state.get("collection") or "", on_change=narrow) \
                .props("dense outlined options-dense").classes("w-full")

    found = in_collection(matching(state.get("games") or [],
                                   state.get("find") or ""),
                          state.get("collection_ids"))
    _game_list(found, state, client_for_target, redraw)


def _game_list(found: list[dict[str, Any]], state: dict[str, Any],
               client_for_target, redraw) -> None:
    if not found:
        return _nothing("Nothing by that name")
    with ui.column().classes("w-full gap-0"):
        for game in found[:SHOWN_AT_ONCE]:
            _game_row(game, state, client_for_target, redraw)
        left = len(found) - SHOWN_AT_ONCE
        if left > 0:
            # The count, not a "load more": what is wanted is one game, and typing two
            # more letters reaches it faster than paging to it does.
            ui.label(t("console.remote.more_keep_typing", left=(left))).classes("remote-note p-3")


def _game_row(game: dict[str, Any], state: dict[str, Any], client_for_target,
              redraw) -> None:
    """One game, and a tap opens it rather than starting it.

    Never tap-to-launch. A mis-tap that opens a sheet costs a tap to undo; a mis-tap
    that starts a table takes the machine away from whoever is on it.
    """
    def open_sheet(_event=None) -> None:
        _game_sheet(game, state, client_for_target, redraw)

    with ui.row().on("click", open_sheet) \
            .classes("w-full items-center gap-2 no-wrap remote-row"):
        with ui.column().classes("grow min-w-0 gap-0"):
            ui.label(str(game.get("name") or "")).classes("remote-row-name truncate")
            made = " ".join(str(game.get(key) or "")
                            for key in ("manufacturer", "year")).strip()
            if made:
                ui.label(made).classes("remote-note truncate")
        if (game.get("user") or {}).get("favorite"):
            ui.icon("favorite").classes("remote-row-mark")


def _game_sheet(game: dict[str, Any], state: dict[str, Any], client_for_target,
                redraw) -> None:
    """One game, everything that can be done to it from here, and Launch at the foot.

    A sheet from the bottom rather than a screen of its own: what is being decided is
    about the row you just touched, and pushing a screen would take the list away to
    answer a question about one line of it.
    """
    with ui.dialog().props("position=bottom") as sheet, \
            ui.card().classes("w-full remote-sheet"):
        ui.label(str(game.get("name") or "")).classes("remote-headline")
        made = " ".join(str(game.get(key) or "")
                        for key in ("manufacturer", "year")).strip()
        if made:
            ui.label(made).classes("remote-note")

        async def write(call, *args) -> None:
            try:
                await run.io_bound(call, *args)
            except Exception as exc:
                ui.notify(str(exc), type="negative")
                return False
            return True

        async def rate(value: int) -> None:
            if await write(ApiClient().rate, game["id"], value):
                game.setdefault("user", {})["rating"] = value
                sheet.close()
                redraw()

        stars.draw(int((game.get("user") or {}).get("rating") or 0), rate)()

        held = bool((game.get("user") or {}).get("favorite"))

        async def favor() -> None:
            if await write(ApiClient().set_favorite, game["id"], not held):
                game.setdefault("user", {})["favorite"] = not held
                sheet.close()
                redraw()

        ui.button(t("console.remote.favorite") if not held else t("console.remote.remove_favorite"),
                  icon="favorite" if not held else "favorite_border",
                  on_click=favor) \
            .props("no-caps flat").classes("remote-action")

        _add_to_collection(game, state, sheet, write)

        async def launch() -> None:
            if await write(client_for_target().launch, game["id"]):
                sheet.close()
                state["screen"] = NOW
                state["play"] = await run.io_bound(client_for_target().play_state)
                redraw()

        ui.button(t("console.remote.launch"), icon="play_arrow", on_click=launch) \
            .props("no-caps unelevated color=primary") \
            .classes("remote-action remote-action--primary")
    sheet.open()


def _add_to_collection(game: dict[str, Any], state: dict[str, Any], sheet,
                       write) -> None:
    """Put it in a list you keep.

    Shown disabled with the reason rather than hidden when there is nowhere to put it:
    an action that vanishes leaves somebody wondering whether this surface can do it at
    all, and the answer is that it can once there is a list to add to.
    """
    named = manual_collections(state.get("collections") or [])
    if not named:
        ui.button(t("console.remote.add_to_collection"), icon="playlist_add") \
            .props("no-caps flat disable").classes("remote-action") \
            .tooltip(t("console.remote.no_lists_of_your_own_yet_a"))
        return

    async def add(name: str) -> None:
        if await write(ApiClient().add_to_collection, name, game["id"]):
            ui.notify(t("console.remote.added_to", name=(name)), type="positive")
            sheet.close()

    with ui.button(t("console.remote.add_to_collection"), icon="playlist_add") \
            .props("no-caps flat").classes("remote-action"):
        with ui.menu():
            for name in named:
                ui.menu_item(name, on_click=lambda _e=None, name=name: add(name))


# What each button asks for, in the words a person would use rather than the vocabulary
# the wire carries. `collection_menu` is the wheel's list of collections; on screen it is
# what that list is called.
BUTTON_WORDS = {
    "select": "Select",
    "back": "Back",
    "menu": "Menu",
    "collection_menu": "Collections",
    "tutorial": "Tutorial",
    "exit": "Quit VPinFE",
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


def _control(state: dict[str, Any], client_for_target, redraw) -> None:
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
        return _nothing(f"{target_name(target)} plays tables but does not run VPinFE, "
                        "so there is nothing here to drive")

    play = state.get("play") or {}
    if play.get("launching"):
        # Honest, and not a guess: the frontend stops listening for the length of a
        # launch, so every button here would do nothing and report success.
        return _playing_instead(play, state, client_for_target, redraw)

    with ui.column().classes("w-full items-center gap-4 p-3"):
        _pad(client_for_target)
        with ui.column().classes("w-full gap-2"):
            for action in ("back", "menu", "collection_menu", "tutorial"):
                _tap_button(action, client_for_target)
        # Apart from the rest and in the danger colour: it ends the thing every other
        # button on this screen is for.
        _tap_button("exit", client_for_target, danger=True)


def _playing_instead(play: dict[str, Any], state: dict[str, Any], client_for_target,
                     redraw) -> None:
    with ui.column().classes("w-full gap-3 p-3"):
        with ui.column().classes("w-full gap-1 console-card"):
            ui.label(t("console.remote.playing")).classes("console-card-title")
            ui.label(str(play.get("game_name") or "A table")).classes("remote-headline")
            ui.label(t("console.remote.the_wheel_is_not_listening")) \
                .classes("remote-note")
        _playing(play, state, client_for_target, redraw)


def _pad(client_for_target) -> None:
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


def _tap_button(action: str, client_for_target, *, danger: bool = False,
                cls: str = "", icon_only: bool = False) -> None:
    async def tap() -> None:
        await _say(client_for_target, action, "tap")

    said = BUTTON_WORDS.get(action, action)
    button = ui.button(on_click=tap)
    if icon_only:
        button.props("flat round").classes(f"remote-pad-key {cls}").tooltip(said)
        with button:
            ui.icon("radio_button_checked")
        return
    # Flat either way: filled is what the one action a screen is *for* wears, and on
    # this screen that is the pad. A destructive button drawn louder than everything
    # around it is the one a thumb finds by accident.
    button.props("no-caps flat") \
        .classes("remote-action" + (" remote-action--danger" if danger else "")) \
        .set_text(said)


async def _say(client_for_target, action: str, phase: str) -> None:
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
        with ui.dialog() as sheet, ui.card().classes("console-confirm items-center"):
            ui.label(t("console.remote.vpinfe_on_your_phone")).classes("console-confirm-title")
            art = _qr_svg(said)
            if art:
                ui.html(art).classes("console-qr")
            # Always, not only when the drawing failed: a camera is not the only way
            # somebody gets this, and an address nobody can read out is one they cannot
            # type either.
            ui.label(said).classes("console-help text-center")
            ui.button(t("console.remote.close"), on_click=sheet.close) \
                .props("flat no-caps").classes("console-action")
        sheet.open()

    with ui.row().classes("items-center justify-center gap-2 w-full no-wrap "
                          "console-invite").on("click", show):
        ui.icon("qr_code_2").classes("shrink-0")
        labels.append(ui.label(t("console.remote.on_your_phone")).classes("text-xs"))
