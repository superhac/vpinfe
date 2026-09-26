"""The library's own metadata files, over the wire.

Two operations that rewrite a file in every game folder, so the things worth pinning are
that they take the scan's job kind, that they refuse rather than overlap, and that the
caller is handed something to watch.
"""

from __future__ import annotations

import asyncio
import json
import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from nicegui import ui

import httpapi
from common import jobs as job_registry
from common.games.game_parser import GameParser
from common.games.info_maintenance import restore_library, upgrade_library
from common.i18n import t
from console import sections
from console.data import Library
from tests.support import lines
from tests.support.library import game_info, write_game
from tests.support.skips import needs_posix_permissions

try:
    from starlette.testclient import TestClient
except ImportError:  # pragma: no cover
    TestClient = None


@unittest.skipIf(TestClient is None, "starlette test client unavailable")
class InfoRouteTests(unittest.TestCase):
    def setUp(self) -> None:
        job_registry.reset_for_tests()
        self.client = TestClient(httpapi.create_api_app(), raise_server_exceptions=False)
        self.addCleanup(job_registry.reset_for_tests)

    def test_it_reports_the_three_states_apart(self) -> None:
        """`newer_than_us` is the one that has to stay separate: a file written by a
        later build is not one this build can upgrade, and counting it with the pending
        ones would report "I upgraded these" about files it cannot fully read."""
        with mock.patch("common.games.game_repository.info_maintenance_counts",
                        return_value={"pending_upgrade": 3, "restorable": 9,
                                      "newer_than_us": 1}), \
                mock.patch("common.games.game_repository.unreadable_games",
                           return_value=[{"folder": "Bad One", "path": "/games/Bad One",
                                          "error": "Its .info file is empty"}]), \
                mock.patch("common.games.game_service.newest_backup_stamp",
                           return_value="20260909T110917Z"), \
                mock.patch("common.games.game_service.pending_upgrade_game_names",
                           return_value=["A", "B", "C"]), \
                mock.patch("common.games.game_service.restorable_game_names",
                           return_value=["A"]):
            body = self.client.get("/library/info").json()

        self.assertEqual(body["pending_upgrade"], 3)
        self.assertEqual(body["newer_than_us"], 1)
        self.assertEqual(body["restorable"], 9)
        self.assertEqual([one["folder"] for one in body["unreadable"]], ["Bad One"])

    def _start(self, which: str, done: list):
        return mock.patch(f"common.games.game_service.{which}",
                          side_effect=lambda **kw: done.append(kw))

    def test_an_upgrade_hands_back_a_job_to_watch(self) -> None:
        done: list = []
        with self._start("upgrade_info", done):
            answer = self.client.post("/library/info/upgrade")

        self.assertEqual(answer.status_code, 202)
        self.assertTrue(answer.headers["Location"].startswith("/api/v1/jobs/"))
        self.assertEqual(answer.json()["kind"], job_registry.KIND_LIBRARY_SCAN)

    def test_the_route_owns_the_job_rather_than_the_service(self) -> None:
        """Otherwise the service registers a second one of the same kind and refuses
        itself as busy - which is a 500 for work that was about to run fine."""
        done: list = []
        with self._start("upgrade_info", done):
            self.client.post("/library/info/upgrade")

        self.assertEqual(len(done), 1)
        self.assertIn("job", done[0])
        self.assertIsNotNone(done[0]["job"])

    def test_a_restore_is_the_same_kind_as_a_scan(self) -> None:
        """Both rewrite a .info for every game they touch, so running them at once would
        interleave writes to the same files."""
        done: list = []
        with self._start("restore_info", done):
            answer = self.client.post("/library/info/restore")

        self.assertEqual(answer.json()["kind"], job_registry.KIND_LIBRARY_SCAN)

    def test_one_at_a_time(self) -> None:
        """A second pass while one is running is refused rather than queued: the two
        would be rewriting the same files."""
        job_registry.submit(job_registry.KIND_LIBRARY_SCAN,
                            lambda job: _never_finishes())

        answer = self.client.post("/library/info/upgrade")

        self.assertEqual(answer.status_code, 409)


class MetadataCardTests(unittest.TestCase):
    """What the Overview says about it."""

    def test_a_backup_stamp_reads_as_a_date(self) -> None:
        """It is shown to somebody deciding whether to go back to it, and nobody reads
        an ISO basic-format timestamp at a glance."""
        self.assertEqual(sections._stamp("20260909T110917Z"), "2026-09-09")

    def test_no_stamp_says_nothing_rather_than_guessing(self) -> None:
        self.assertEqual(sections._stamp(""), "")
        self.assertEqual(sections._stamp("2026"), "")

    def _unreadable(self, *names: str) -> list[dict]:
        """The rows the scan writes for folders whose `.info` is not valid metadata."""
        with TemporaryDirectory() as tmp:
            for name in names:
                (write_game(tmp, name) / f"{name}.info").write_text(
                    '{"Info": {"Title": "broken",,,}', encoding="utf-8")
            return GameParser(tmp).get_unreadable_games()

    def _drawn(self, unreadable: list[dict]) -> dict[str, str]:
        return _card({"unreadable": unreadable})

    def test_a_folder_it_could_not_read_is_named_with_why_on_hover(self) -> None:
        drawn = self._drawn(self._unreadable("Malformed Info (Original 2024)"))

        self.assertEqual(t("error.games.info_wrong_at_line", line=1),
                         drawn.get("Malformed Info (Original 2024)"), list(drawn))
        self.assertIn(t("console.sections.could_not_read_game"), drawn)

    def test_four_are_named_and_the_rest_counted(self) -> None:
        names = [f"Broken {i} (Original 2024)" for i in range(6)]

        drawn = self._drawn(self._unreadable(*names))

        self.assertEqual([True] * 4 + [False] * 2, [name in drawn for name in names])
        self.assertIn(t("said.and_more", count=2), drawn)

    def test_one_game_written_by_an_older_build_reads_as_one(self) -> None:
        one, two = (t("console.sections.written_older_build_can", count=n) for n in (1, 2))

        self.assertIn(one, _card({"pending_upgrade": 1}))
        self.assertIn(two, _card({"pending_upgrade": 2}))
        self.assertNotEqual(one, two.replace("2", "1"))

    def test_one_game_with_a_saved_copy_reads_as_one(self) -> None:
        for key, stamp in (("games_saved_copy", ""),
                           ("games_saved_copy_from", "20260909T110917Z")):
            with self.subTest(key=key):
                said = {n: t(f"console.sections.{key}", count=n, when="2026-09-09")
                        for n in (1, 2)}

                for n, line in said.items():
                    self.assertIn(line, _card({"restorable": n, "newest_backup": stamp}))
                self.assertNotEqual(said[1], said[2].replace("2 ", "1 ", 1))

    def test_a_folder_fixed_and_rescanned_is_no_longer_named(self) -> None:
        name = "Malformed Info (Original 2024)"
        with TemporaryDirectory() as tmp:
            info = write_game(tmp, name) / f"{name}.info"
            info.write_text('{"Info": {"Title": "broken",,,}', encoding="utf-8")
            client = mock.Mock()
            client.info_maintenance.side_effect = lambda: {
                "unreadable": GameParser(tmp).get_unreadable_games()}
            library = Library(client)
            library.read_metadata_state()
            named = name in _card(library.metadata_state())
            info.write_text(json.dumps(game_info(name)), encoding="utf-8")

            library.refresh_after_import()

        self.assertEqual((True, False), (named, name in _card(library.metadata_state())))


LEGACY = {"Info": {"Title": "Sample Game", "Rom": "sample"},
          "VPXFile": {"filename": "Sample Game.vpx", "filehash": "abc", "rom": "sample"}}
KEPT = "Sample Game (Original 2024)"
LOCKED = "Locked Game (Original 2024)"


def _card(metadata: dict, left: dict | None = None) -> dict[str, str]:
    """Each line the metadata card draws, with what hovering it shows."""
    with ui.column() as body:
        sections.metadata(metadata, lambda _which: None, left)
    return lines.details(body)


async def _now(callback, *args, **kwargs):
    return callback(*args, **kwargs)


@unittest.skipIf(TestClient is None, "starlette test client unavailable")
@needs_posix_permissions
class MetadataOutcomeTests(unittest.TestCase):
    """What Upgrade and Restore say once their job ends, from the job run over a library
    with one folder it may not write, read back as the resource the Console is handed."""

    def setUp(self) -> None:
        job_registry.reset_for_tests()
        self.addCleanup(job_registry.reset_for_tests)
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        for name in (KEPT, LOCKED):
            write_game(self.root, name, info=LEGACY)
        self.addCleanup(self._lock, self.root / LOCKED, False)
        self.addCleanup(self._lock, self.root, False)

    def _lock(self, folder: Path, locked: bool = True) -> None:
        folder.chmod(0o555 if locked else 0o755)

    def _job(self, work) -> dict:
        job = job_registry.submit(job_registry.KIND_LIBRARY_SCAN, lambda _job: work(self.root))
        for _ in range(500):
            if job.state != job_registry.RUNNING:
                break
            time.sleep(0.01)
        api = TestClient(httpapi.create_api_app(), raise_server_exceptions=False)
        return api.get(f"/jobs/{job.id}").json()

    def _metadata(self) -> dict:
        parser = GameParser(self.root)
        games = parser.get_all_games()
        pending = [one.game_dir_name for one in games if one.info_pending_upgrade]
        return {"pending_upgrade": len(pending), "pending_games": pending,
                "restorable": sum(1 for one in games if one.info_restorable),
                "unreadable": parser.get_unreadable_games()}

    def _press(self, which: str, work) -> tuple[list[tuple[str, str, str]], dict[str, str]]:
        """Press Upgrade or Restore over what `work` did. Hand back each thing the Console
        said, as lead, caption and type, and the card as it is drawn afterwards."""
        client = mock.Mock()
        client.upgrade_info.return_value = client.restore_info.return_value = {"id": which}
        client.job.return_value = self._job(work)
        client.info_maintenance.side_effect = self._metadata
        library = Library(client)
        page = {"view": "overview"}
        with mock.patch("console.confirm.ask", mock.AsyncMock(return_value=True)), \
                mock.patch("console.api.ApiClient", return_value=client), \
                mock.patch("nicegui.run.io_bound", new=_now), \
                mock.patch.object(sections, "_POLL_S", 0), \
                mock.patch.object(sections.ui, "notify") as notify:
            asyncio.run(sections._metadata_action(library, page, mock.Mock())(which))
        said = [(one.args[0], one.kwargs.get("caption", ""), one.kwargs.get("type", ""))
                for one in notify.call_args_list]
        return said, _card(library.metadata_state(), page.get(sections._LEFT))

    def _upgrade(self):
        self._lock(self.root / LOCKED)
        return self._press("upgrade", upgrade_library)

    def test_it_says_how_many_came_through(self) -> None:
        said, _ = self._upgrade()

        self.assertIn((t("console.sections.upgraded_some", done=1, total=2), "", "warning"),
                      said)

    def test_the_folder_it_could_not_write_is_named_with_why_on_hover(self) -> None:
        _, drawn = self._upgrade()

        self.assertEqual(drawn.get(LOCKED),
                         t("said.why.no_permission_at", path=str(self.root / LOCKED)))

    def test_a_restore_names_what_it_could_not_put_back(self) -> None:
        self._job(upgrade_library)
        self._lock(self.root / LOCKED)

        said, drawn = self._press("restore", restore_library)

        self.assertIn((t("console.sections.restored_some", done=1, total=2), "", "warning"),
                      said)
        self.assertEqual(drawn.get(LOCKED),
                         t("said.why.no_permission_at", path=str(self.root / LOCKED)))

    def test_a_job_that_fails_leads_with_words_and_its_reason(self) -> None:
        self.root.chmod(0o000)

        said, _ = self._press("upgrade", upgrade_library)

        lead, caption, kind = said[-1]
        self.assertEqual((lead, kind), (t("console.sections.upgrade_failed"), "negative"))
        self.assertTrue(caption.startswith(t("said.why.no_permission")), caption)


def _never_finishes() -> None:
    import threading

    threading.Event().wait(30)
