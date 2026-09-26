"""The line above the Games and Tables grids, over a library written to disk and read by
the scan."""

from __future__ import annotations

import asyncio
import unittest
from collections.abc import Awaitable, Callable
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any
from unittest import mock
from unittest.mock import Mock

from nicegui import core, ui

from common.games import game_identity, game_repository, unwritten
from common.games.game_parser import GameParser
from common.games.info_maintenance import upgrade_library
from common.i18n import t
from console import games, sections
from console.data import Library
from tests.support.library import game_info, write_game
from tests.support.skips import needs_posix_permissions

KEPT = "Kept Game (Original 2024)"
BROKEN = "Malformed Info (Original 2024)"
OLDER = "Older Game (Original 2024)"
LOCKED = "Locked Game (Original 2024)"
GAME = {"id": "g-1", "name": KEPT, "folder": f"/games/{KEPT}"}
LEGACY = {"Info": {"Title": "Older Game", "Rom": "older"},
          "VPXFile": {"filename": f"{OLDER}.vpx", "filehash": "abc", "rom": "older"}}


def _dialogs(holder: ui.element) -> list[ui.dialog]:
    """A dialog is drawn in the page's layout, whatever it was opened from."""
    return [one for one in holder.client.layout.descendants() if isinstance(one, ui.dialog)]


def _press(within: ui.element, label: str) -> None:
    button = next(one for one in within.descendants()
                  if isinstance(one, ui.button) and one.text == label)
    for listener in button._event_listeners.values():
        assert listener.handler is not None
        listener.handler(None)


async def _now(callback: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    return callback(*args, **kwargs)


class TheLineAboveTheGrid(unittest.TestCase):
    def setUp(self) -> None:
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.locked: set[str] = set()
        write_game(self.root, KEPT, info=game_info(KEPT))
        client = Mock()
        client.games.return_value = [GAME]
        client.library_game_collections.return_value = {}
        client.all_media.return_value = []
        client.preferences.return_value = {}
        client.library_policy.return_value = {}
        client.info_maintenance.side_effect = self._metadata
        self.library = Library(client)
        self.library.games = [GAME]
        self.library.media = self.library._shared_media()
        self.library.load_game_collections()
        self.library.load_kept_kinds()
        for patcher in (mock.patch.object(ui, "run_javascript"),
                        mock.patch.object(ui, "notify"),
                        mock.patch.dict(unwritten._HELD, clear=True),
                        mock.patch.object(unwritten, "logger")):
            patcher.start()
            self.addCleanup(patcher.stop)

    def _metadata(self) -> dict[str, Any]:
        parser = GameParser(self.root)
        parsed = parser.get_all_games()
        # Only the locked ones: an id written to a writable 2.x `.info` upgrades it.
        game_identity.ensure_unique_ids(
            [one for one in parsed if one.game_dir_name in self.locked], order=[])
        with mock.patch.object(game_repository, "all_games", return_value=parsed):
            unwritten = game_repository.unwritten_games()
        pending = [one.game_dir_name for one in parsed if one.info_pending_upgrade]
        return {"pending_upgrade": len(pending), "pending_games": pending,
                "unreadable": parser.get_unreadable_games(),
                "unwritten": unwritten}

    def _lock(self, name: str, info: dict[str, Any]) -> Path:
        folder = write_game(self.root, name, info=info)
        folder.chmod(0o555)
        self.addCleanup(folder.chmod, 0o755)
        self.locked.add(name)
        return folder

    def _plant_broken(self) -> None:
        (write_game(self.root, BROKEN) / f"{BROKEN}.info").write_text(
            '{"Info": {"Title": "broken",,,}', encoding="utf-8")

    def _build(self) -> None:
        games.build(self.library.game_rows(), self.library.kinds_present(),
                    self.library, lambda _row: None, {"view": "games"})

    def _drawn(self, then: Callable[[ui.element], Awaitable[None]] | None = None
               ) -> ui.element:
        """The page as the Console draws it, after the library is read."""
        self.library.read_metadata_state()
        holder = ui.card()

        async def inside() -> None:
            was = core.loop
            core.loop = asyncio.get_running_loop()
            try:
                with holder:
                    self._build()
                if then is not None:
                    await then(holder)
            finally:
                core.loop = was
        asyncio.run(inside())
        return holder

    def _line(self, holder: ui.element) -> list[str]:
        return [one.text for one in holder.descendants()
                if isinstance(one, ui.label) and "console-attention-line" in one.classes]

    def _show(self, holder: ui.element) -> ui.dialog:
        before = set(_dialogs(holder))
        _press(holder, t("console.sections.show"))
        return next(one for one in _dialogs(holder) if one not in before and one.value)

    def test_a_folder_it_could_not_read_is_said_above_the_grid(self) -> None:
        self._plant_broken()

        self.assertEqual([t("console.sections.not_in_library", count=1)],
                         self._line(self._drawn()))

    def test_a_game_on_an_older_format_is_said_above_the_grid(self) -> None:
        write_game(self.root, OLDER, info=LEGACY)

        self.assertEqual([t("console.sections.older_format", count=1)],
                         self._line(self._drawn()))

    def test_a_library_with_nothing_wrong_draws_no_line(self) -> None:
        holder = self._drawn()

        self.assertEqual([], [one for one in holder.descendants()
                              if "console-attention" in one.classes])

    def test_show_names_the_folder_and_why(self) -> None:
        self._plant_broken()
        opened: dict[str, str] = {}

        async def show(holder: ui.element) -> None:
            box = self._show(holder)
            tips = {one.props["target"]: one.text
                    for one in box.descendants() if isinstance(one, ui.tooltip)}
            opened.update({one.text: tips.get(f"#{one.html_id}", "")
                           for one in box.descendants() if isinstance(one, ui.label)})

        self._drawn(show)

        self.assertEqual(t("error.games.info_wrong_at_line", line=1), opened.get(BROKEN),
                         list(opened))

    def test_an_upgrade_that_leaves_nothing_takes_the_line_away(self) -> None:
        write_game(self.root, OLDER, info=LEGACY)
        api = Mock()
        api.upgrade_info.return_value = {"id": "u-1"}
        seen: list[list[str]] = []

        async def ended(_client: Any, _job_id: str) -> dict[str, Any]:
            return {"state": "done", "result": upgrade_library(self.root)}

        async def upgrade(holder: ui.element) -> None:
            seen.append(self._line(holder))
            _press(self._show(holder), t("word.upgrade"))
            for _ in range(50):
                await asyncio.sleep(0)
            seen.append(self._line(holder))

        with mock.patch("console.confirm.ask", mock.AsyncMock(return_value=True)), \
                mock.patch("console.api.ApiClient", return_value=api), \
                mock.patch("nicegui.run.io_bound", new=_now), \
                mock.patch.object(sections, "_ended", ended):
            self._drawn(upgrade)

        self.assertEqual([[t("console.sections.older_format", count=1)], []], seen)

    @needs_posix_permissions
    def test_a_game_whose_folder_could_not_be_written_is_said_above_the_grid(self) -> None:
        self._lock(LOCKED, game_info(LOCKED))

        self.assertEqual([t("console.sections.not_written", count=1)],
                         self._line(self._drawn()))

    @needs_posix_permissions
    def test_show_names_the_folder_it_could_not_write_and_why(self) -> None:
        folder = self._lock(LOCKED, game_info(LOCKED))
        opened: dict[str, str] = {}

        async def show(holder: ui.element) -> None:
            box = self._show(holder)
            tips = {one.props["target"]: one.text
                    for one in box.descendants() if isinstance(one, ui.tooltip)}
            opened.update({one.text: tips.get(f"#{one.html_id}", "")
                           for one in box.descendants() if isinstance(one, ui.label)})

        self._drawn(show)

        self.assertEqual(t("said.why.no_permission_at", path=str(folder)),
                         opened.get(LOCKED), list(opened))

    @needs_posix_permissions
    def test_a_folder_upgrade_could_not_write_is_named_once(self) -> None:
        self._lock(OLDER, LEGACY)
        api = Mock()
        api.upgrade_info.return_value = {"id": "u-1"}
        seen: list[int] = []

        def named(box: ui.dialog) -> int:
            return sum(1 for one in box.descendants()
                       if isinstance(one, ui.label) and one.text == OLDER)

        async def ended(_client: Any, _job_id: str) -> dict[str, Any]:
            return {"state": "done", "result": upgrade_library(self.root)}

        async def upgrade(holder: ui.element) -> None:
            box = self._show(holder)
            seen.append(named(box))
            _press(box, t("word.upgrade"))
            for _ in range(50):
                await asyncio.sleep(0)
            seen.append(named(box))

        with mock.patch("console.confirm.ask", mock.AsyncMock(return_value=True)), \
                mock.patch("console.api.ApiClient", return_value=api), \
                mock.patch("nicegui.run.io_bound", new=_now), \
                mock.patch.object(sections, "_ended", ended):
            self._drawn(upgrade)

        self.assertEqual([1, 1], seen)


class TheLineAboveTheTablesGrid(TheLineAboveTheGrid):
    def _build(self) -> None:
        games.build_tables(self.library.table_rows(), self.library, lambda _row: None,
                           {"view": "tables"})


if __name__ == "__main__":
    unittest.main()
