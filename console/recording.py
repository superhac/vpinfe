"""Settings > Hardware > Recording: what a settings page cannot say from the schema alone.

What this device can record comes from the device (`GET /capture`), read once per draw
and handed round as `offered[EDITOR_CAPTURE_COMMAND]`; a page drawing another device's
settings has none of it, and draws the settings alone.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from nicegui import run, ui

from common import config_schema
from common.capture import adapters, commands, preflight, trial
from common.failures import why
from common.i18n import size, t
from console import confirm, offload, panel, verbs
from console.on_page import on_page

logger = logging.getLogger("vpinfe.console.recording")

SECTION = "capture"
REPORT = config_schema.EDITOR_CAPTURE_COMMAND
H264 = "h264"

# The names whose meaning differs between the two commands.
PER_COMMAND = frozenset({"input", "fps"})


def report_of(offered: dict[str, Any] | None) -> dict[str, Any]:
    return dict((offered or {}).get(REPORT) or {})


def command_of(option: dict) -> str:
    key = str(option.get("key") or "")
    return next((one for one, setting in commands.SETTINGS.items() if setting == key), "")


def resolved(offered: dict[str, Any]) -> dict[str, str]:
    """What Automatic records on this device, as the line under Video Format."""
    codec = report_of(offered).get("video_codec")
    if not codec:
        return {}
    return {"video_codec": t("console.recording.automatic_h264") if codec == H264
            else t("console.recording.automatic_vp9")}


def command_editor(option: dict, value: Any, save: Callable[[Any], Any], *,
                   writable: bool = True, suggestions: dict[str, Any] | None = None,
                   **_: Any) -> Callable[[], None]:
    """A command line, refused at the field where it cannot run, with VPinFE's own for this
    device as what an empty field stands for."""
    command = command_of(option)
    own = str((report_of(suggestions).get("commands") or {}).get(command) or "")

    async def keep(text: str) -> str:
        wrong = commands.problems(text, command)
        if wrong:
            return commands.words(wrong[0])
        await save(text.strip())
        return ""

    return panel.field(str(value or ""), keep, placeholder=own, disabled=not writable,
                       refuses=True, left_empty=own)


def add_under(entries: list[Any], option: dict, value: Any,
              save: Callable[[Any], Any], rerender: Callable[[], None],
              offered: dict[str, Any] | None) -> None:
    """Under a command's field: Copy VPinFE's Command while it is empty, and the names it
    can use."""
    command = command_of(option)
    own = str((report_of(offered).get("commands") or {}).get(command) or "")
    names = commands.OFFERED[command]

    @on_page
    async def copy() -> None:
        if await save(own):
            rerender()

    def draw() -> None:
        with ui.column().classes("gap-1 min-w-0"):
            if own and not str(value or "").strip():
                panel.action(t("console.recording.copy_vpinfe_command"), copy,
                             icon=verbs.COPY)()
            with panel.disclosure(t("console.commands.names_can_use", count=len(names))) \
                    .classes("console-tokens"):
                with ui.column().classes("gap-1 pt-1"):
                    ui.label(t("console.commands.each_stands_something_command")) \
                        .classes("console-help")
                    with ui.element("div").classes("console-token-list"):
                        for name in names:
                            ui.label(f"[{name}]").classes("console-token")
                            ui.label(says(name, command)).classes("console-help")

    entries.append((panel.ASIDE, draw))


def says(name: str, command: str) -> str:
    """What a name stands for in this command."""
    return t(f"capture.token.{name}.{command}") if name in PER_COMMAND \
        else t(f"capture.token.{name}")


def finding(offered: dict[str, Any], library: Any = None,
            rerender: Callable[[], None] | None = None) -> Callable[[], None] | None:
    """Why this device records nothing, where it does not; or that it could not say.
    With this install's library, Choose Screens beside a desktop that has not been told
    which screens VPinFE may record."""
    found = report_of(offered)
    if found.get("error"):
        failed = str(found["error"])

        def unread() -> None:
            panel.line(t("console.recording.could_not_read"), hint=failed)

        return unread
    if not found or found.get("available") or not found.get("reason"):
        return None
    blocked = found["reason"]
    gettable = bool((blocked.get("remedy") or {}).get("get"))
    choosable = blocked.get("key") == adapters.NOT_CHOSEN and library is not None
    said = preflight.words({**blocked, "remedy": None} if choosable else blocked)

    def draw() -> None:
        from console.settings import TOOLS, address_for

        with ui.element("div").classes("console-attention w-full mt-2"):
            ui.icon("error_outline").classes("console-attention-icon")
            with ui.column().classes("gap-0 min-w-0 grow"):
                ui.label(said).classes("console-attention-line")
                if gettable:
                    panel.link(t("console.settings.page_tools"), to=address_for(TOOLS))()
            if choosable:
                panel.action(t("console.recording.choose_screens"),
                             _chooser(library, rerender or (lambda: None),
                                      str((blocked.get("params") or {}).get("desktop"))),
                             icon=verbs.CHOOSE)()

    return draw


def _chooser(library: Any, rerender: Callable[[], None],
             desktop: str) -> Callable[[], Any]:
    """Choose Screens: asked first, since the desktop asks on the device's own screen."""
    @on_page
    async def choose() -> None:
        if not await confirm.ask(t("console.recording.choose_screens_ask"),
                                 detail=t("console.recording.choose_screens_detail",
                                          desktop=desktop),
                                 confirm=t("console.recording.choose_screens"),
                                 icon=verbs.CHOOSE, danger=False):
            return
        try:
            job = await offload.io(library.choose_capture_screens)
        except Exception as exc:  # noqa: BLE001 - the reason belongs on screen
            ui.notify(t("console.recording.could_not_choose"), caption=why(exc),
                      type="negative")
            return
        from console import record  # record imports this module

        ended = await record.ended_job(library, str(job.get("id") or ""))
        if not ended or ended.get("error"):
            ui.notify(t("console.recording.could_not_choose"),
                      caption=str(ended.get("error") or ""), type="negative")
        elif ended.get("reason"):
            ui.notify(t("console.recording.could_not_choose"),
                      caption=preflight.words(ended["reason"]), type="warning")
        else:
            every = ended.get("shared") == ended.get("screens")
            ui.notify(t("console.recording.chose_screens", desktop=desktop,
                        shared=str(ended.get("shared")), screens=str(ended.get("screens"))),
                      type="positive" if every else "warning")
        rerender()

    return choose


async def foot(library: Any, rerender: Callable[[], None], *,
               offered: dict[str, Any] | None = None) -> list[tuple[Any, Any]]:
    """Test, under the commands; then the recordings waiting for a decision."""
    found = report_of(offered)
    rows: list[tuple[Any, Any]] = []
    if found:
        rows.append((panel.FULL, _tester(library, found)))
    try:
        waiting = await offload.io(library.capture_proposals)
    except Exception as exc:  # noqa: BLE001 - a settings page says why, never 500s
        logger.warning("Could not read the recordings waiting: %s", why(exc))
        return rows
    if int(waiting.get("count") or 0):
        rows.append(_waiting(library, rerender, waiting))
    return rows


def _tester(library: Any, found: dict[str, Any]) -> Callable[[], None]:
    blocked = "" if found.get("available") else preflight.words(found.get("reason") or {})

    def draw() -> None:
        with ui.column().classes("gap-1 w-full min-w-0"):
            with ui.row().classes("items-center gap-2 no-wrap min-w-0"):
                panel.action(t("console.recording.test"), lambda: tried(), icon=verbs.RUN,
                             enabled=not blocked, hint=blocked)()
                ui.label(t("console.recording.test_what", seconds=f"{trial.SECONDS:g}")) \
                    .classes("console-help")
            outcome = ui.column().classes("gap-1 min-w-0")

        @on_page
        async def tried() -> None:
            running = ui.notification(t("console.recording.testing"), spinner=True,
                                      timeout=None)
            try:
                said = await offload.io(library.test_capture)
            except Exception as exc:  # noqa: BLE001 - said, and nothing was kept
                ui.notify(t("console.recording.could_not_test"), caption=why(exc),
                          type="negative")
                return
            finally:
                running.dismiss()
            outcome.clear()
            with outcome:
                came_out(said)

    return draw


def came_out(said: dict[str, Any]) -> None:
    """What a test made: a picture and its size, rate and frames, or what failed."""
    if not said.get("ok"):
        with ui.element("div").classes("console-attention w-full"):
            ui.icon("error_outline").classes("console-attention-icon")
            panel.line(t(str((said.get("reason") or {}).get("key") or "")),
                       hint=str(said.get("detail") or ""), classes="console-attention-line")
        return
    width, height = (list(said.get("size") or []) + [0, 0])[:2]
    with ui.row().classes("items-center gap-3 no-wrap min-w-0"):
        if said.get("picture"):
            with ui.element("div").classes("console-source-thumb"):
                ui.image(str(said["picture"]))
        ui.label(t("console.recording.test_came_out", width=str(width), height=str(height),
                   fps=f"{float(said.get('fps') or 0):g}",
                   frames=str(int(said.get("frames") or 0)))).classes("console-help")


def _waiting(library: Any, rerender: Callable[[], None],
             waiting: dict[str, Any]) -> tuple[Any, Any]:
    count = int(waiting.get("count") or 0)

    @on_page
    async def discard() -> None:
        if not await confirm.ask(t("console.recording.discard_ask", count=count),
                                 detail=t("console.recording.discard_detail"),
                                 confirm=t("console.recording.discard_all"),
                                 icon=verbs.DISCARD):
            return
        try:
            await offload.io(library.discard_proposals)
        except Exception as exc:  # noqa: BLE001 - the reason belongs on screen
            ui.notify(t("console.recording.could_not_discard"), caption=why(exc),
                      type="negative")
            return
        rerender()

    games = {str(row.get("game_id") or "") for row in waiting.get("proposals") or []}

    async def used() -> None:
        await run.io_bound(library.reread_media, games)

    @on_page
    async def review() -> None:
        from console import record  # record imports this module

        await record.review(library, used)
        rerender()

    def draw() -> None:
        with ui.element("div").classes("console-fact-edit"):
            ui.label(t("console.recording.waiting_are", count=count,
                       size=size(int(waiting.get("bytes") or 0)))) \
                .classes("console-fact-value truncate min-w-0")
            panel.action(t("console.record.review"), review, icon=verbs.REVIEW,
                         inline=True)()
            panel.action(t("console.recording.discard_all"), discard, icon=verbs.DISCARD,
                         inline=True)()

    return (t("console.recording.waiting"), draw)
