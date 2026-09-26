"""Getting a newly matched game the art it is missing, and nothing more."""

from __future__ import annotations

import configparser
import hashlib
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from common import i18n, jobs, service_errors, timestamps
from common.games import asset_origin, library_policy, media_fill, media_placement
from common.online import asset_sources, vpsdb_sync
from tests.support.library import TempTree, fake_game, game_info, write_game

FOLDER = "Fathom (Bally 1981)"
OTHER = "Eight Ball (Bally 1977)"


def _url(name: str) -> str:
    return f"https://media.invalid/{name}"


# Largest first, the way the catalog lists them, so taking the first offer is visibly
# different from taking the configured size.
MANIFEST = {
    "fathom": {
        "wheel": _url("wheel.png"), "wheel_md5": "wheel-md5",
        "4k": {"table": _url("table-4k.png"), "fss": _url("fss-4k.png"),
               "table_video": _url("table-4k.mp4")},
        "1k": {"bg": _url("bg-1k.png"), "table": _url("table-1k.png"),
               "fss": _url("fss-1k.png"), "table_video": _url("table-1k.mp4")},
    },
    "eightball": {"wheel": _url("eightball-wheel.png")},
}


def _downloaded(url: str, path: Path) -> None:
    Path(path).write_bytes(url.encode())


class _Library(TempTree):
    def setUp(self) -> None:
        super().setUp()
        self.games: dict[str, object] = {}
        self.sets: dict[str, str] = {}
        self.folder = self.game(FOLDER, "fathom")
        self.downloads = MagicMock(side_effect=_downloaded)
        self.config = configparser.ConfigParser()
        policy = library_policy.reset_for_tests(self.root / "library.json")
        self.addCleanup(library_policy.reset_for_tests)
        self.policy = policy
        for patcher in (
                patch("common.games.game_repository.catalog", return_value=self.games),
                patch("common.games.game_repository.refresh_game"),
                patch("common.http_client.download_file", self.downloads),
                patch.object(asset_sources, "_MANIFEST", MANIFEST),
                patch.object(media_fill, "get_ini_config", return_value=self.config),
                patch("common.games.media_service.media_settings",
                      side_effect=lambda: (self.variant(), self.sets)),
                patch("socket.socket.connect", side_effect=OSError("offline"))):
            patcher.start()
            self.addCleanup(patcher.stop)

    def game(self, name: str, vps_id: str, **medias: bytes) -> Path:
        game_id = f"id{len(self.games):09d}"
        info = game_info(name, vps_id=vps_id, game_id=game_id,
                         tables={"tbl0000001": {"id": "tbl0000001",
                                                "filename": f"{name}.vpx"}})
        folder = write_game(self.root, name, info=info, medias=medias)
        self.games[game_id] = fake_game(folder, name, meta=info)
        return folder

    def variant(self) -> str:
        return self.config.get("media", "playfield_variant", fallback="table")

    def placed(self, folder: Path | None = None) -> dict[str, str]:
        medias = (folder or self.folder) / "medias"
        return {path.name: path.read_bytes().decode(errors="replace")
                for path in medias.iterdir() if path.is_file()} if medias.is_dir() else {}


class FillTests(_Library):
    def test_each_missing_kind_the_catalog_has_is_fetched(self) -> None:
        result = media_fill.fill([self.folder])

        placed = self.placed()
        self.assertEqual(placed[f"(Wheel) {FOLDER}.png"], _url("wheel.png"))
        self.assertEqual(placed[f"(Backglass) {FOLDER}.png"], _url("bg-1k.png"))
        self.assertEqual(result["filled"], len(placed))
        self.assertEqual(result["failed"], 0)

    def test_the_progress_says_what_the_job_is_doing(self) -> None:
        reporter = MagicMock()

        media_fill.fill([self.folder], reporter=reporter)

        said = reporter.progress.call_args.args[2]
        self.assertEqual(said, i18n.t("said.getting_art_for", game=FOLDER))
        self.assertNotEqual(said, FOLDER)

    def test_where_it_came_from_is_recorded(self) -> None:
        media_fill.fill([self.folder])

        hosts = {str(entry.get("host")) for entry in
                 asset_origin.sources(self.folder).values()}
        self.assertEqual(hosts, {"vpinmediadb"})

    def test_a_slot_with_a_file_is_left_alone(self) -> None:
        self.folder = self.game(OTHER, "fathom", **{"wheel.png": b"mine"})

        media_fill.fill([self.folder])

        placed = self.placed()
        self.assertEqual(placed["wheel.png"], "mine")
        self.assertNotIn(f"(Wheel) {OTHER}.png", placed)

    def test_a_slot_an_active_set_answers_is_left_alone(self) -> None:
        self.sets = {"wheel": "Classic"}
        self.folder = self.game(OTHER, "fathom", **{"wheels/Classic/wheel.png": b"set"})

        media_fill.fill([self.folder])

        self.assertNotIn(f"(Wheel) {OTHER}.png", self.placed())
        self.assertIn(f"(Backglass) {OTHER}.png", self.placed())

    def test_a_kind_this_library_does_not_collect_is_not_fetched(self) -> None:
        self.policy.set("hidden_media_kinds", ["wheel"])

        media_fill.fill([self.folder])

        self.assertNotIn(f"(Wheel) {FOLDER}.png", self.placed())

    def test_the_size_the_display_is_set_to_is_the_one_fetched(self) -> None:
        media_fill.fill([self.folder])

        placed = self.placed()
        self.assertEqual(placed[f"(Playfield) {FOLDER}.png"], _url("table-4k.png"))
        self.assertEqual(placed[f"(Playfield) {FOLDER}.mp4"], _url("table-1k.mp4"))

    def test_under_fss_the_playfield_is_the_fss_render_with_no_video(self) -> None:
        self.config.read_dict({"media": {"playfield_variant": "fss"}})

        media_fill.fill([self.folder])

        placed = self.placed()
        self.assertEqual(placed[f"(Playfield) {FOLDER}.png"], _url("fss-4k.png"))
        self.assertNotIn(f"(Playfield) {FOLDER}.mp4", placed)

    def test_a_game_with_no_match_fetches_nothing(self) -> None:
        folder = self.game(OTHER, "")

        result = media_fill.fill([folder])

        self.assertEqual(result["unmatched"], 1)
        self.downloads.assert_not_called()

    def test_a_source_that_cannot_be_reached_is_asked_once(self) -> None:
        other = self.game(OTHER, "eightball")
        with patch.object(asset_sources, "_MANIFEST", None), \
                patch("common.online.vpsdb_cache.VPinMediaDatabase.load",
                      return_value=None) as load:
            result = media_fill.fill([self.folder, other])

        self.assertEqual(load.call_count, 1)
        self.assertEqual(result["filled"], 0)
        self.downloads.assert_not_called()

    def test_a_download_that_fails_leaves_the_gap_and_the_rest_go_on(self) -> None:
        def flaky(url: str, path: Path) -> None:
            if url == _url("wheel.png"):
                raise OSError("offline")
            _downloaded(url, path)

        self.downloads.side_effect = flaky

        result = media_fill.fill([self.folder])

        placed = self.placed()
        self.assertNotIn(f"(Wheel) {FOLDER}.png", placed)
        self.assertIn(f"(Backglass) {FOLDER}.png", placed)
        self.assertEqual(result["failed"], 1)

    def test_turned_off_it_stops_between_games(self) -> None:
        other = self.game(OTHER, "eightball")
        answers = iter([True, False])

        media_fill._fill([str(self.folder), str(other)], media_fill.kept_kinds(),
                         ("vpinmediadb",), None, lambda: next(answers))

        self.assertTrue(self.placed())
        self.assertEqual(self.placed(other), {})


class AskedTests(_Library):
    """Getting missing art because someone asked, for the games and kinds they picked."""

    def setUp(self) -> None:
        super().setUp()
        jobs.reset_for_tests()
        self.addCleanup(jobs.reset_for_tests)
        self.other = self.game(OTHER, "eightball")
        self.loose = self.game("Loose Ends", "")

    def id_of(self, folder: Path) -> str:
        return next(game_id for game_id, game in self.games.items()
                    if Path(str(getattr(game, "full_path_game", ""))) == folder)

    def ran(self, job: jobs.Job) -> dict:
        deadline = time.monotonic() + 10
        while job.state == jobs.RUNNING:
            self.assertLess(time.monotonic(), deadline, "the fill never finished")
            time.sleep(0.02)
        self.assertIsNone(job.error)
        return job.result if isinstance(job.result, dict) else {}

    @staticmethod
    def rows(found: dict) -> dict[str, tuple[int, int]]:
        return {row["kind"]: (row["missing"], row["available"]) for row in found["kinds"]}

    def test_the_plan_counts_what_is_missing_and_what_can_be_had(self) -> None:
        found = media_fill.plan()

        self.assertEqual((found["games"], found["unmatched"]), (3, 1))
        self.assertEqual(found["sources"], ["VPinMediaDB"])
        rows = self.rows(found)
        self.assertEqual(rows["wheel"], (3, 2))
        self.assertEqual(rows["backglass"], (3, 1))
        self.assertEqual(rows["flyer"], (3, 0))
        self.assertEqual(found["unreachable"], [])
        self.downloads.assert_not_called()

    def test_a_source_that_cannot_be_reached_is_named_and_offers_nothing(self) -> None:
        with patch.object(asset_sources, "_MANIFEST", None), \
                patch("common.online.vpsdb_cache.VPinMediaDatabase.load",
                      return_value=None) as load:
            found = media_fill.plan()

        self.assertEqual(found["unreachable"], ["VPinMediaDB"])
        self.assertEqual(self.rows(found)["wheel"], (3, 0))
        self.assertEqual(load.call_count, 1)

    def test_a_fill_names_the_source_it_could_not_reach(self) -> None:
        with patch.object(asset_sources, "_MANIFEST", None), \
                patch("common.online.vpsdb_cache.VPinMediaDatabase.load", return_value=None):
            result = self.ran(media_fill.start(kinds=["wheel"]))

        self.assertEqual((result["filled"], result["unreachable"]), (0, ["VPinMediaDB"]))
        self.downloads.assert_not_called()

    def test_a_fill_that_reached_every_source_names_none(self) -> None:
        result = self.ran(media_fill.start([self.id_of(self.folder)], ["wheel"]))

        self.assertEqual(result["unreachable"], [])

    def test_the_plan_leaves_out_a_hidden_kind_and_a_slot_with_a_file(self) -> None:
        self.policy.set("hidden_media_kinds", ["backglass"])
        held = self.game("Held", "fathom", **{"wheel.png": b"mine"})

        found = media_fill.plan([self.id_of(held), self.id_of(self.other)])

        self.assertEqual((found["games"], found["unmatched"]), (2, 0))
        rows = self.rows(found)
        self.assertNotIn("backglass", rows)
        self.assertEqual(rows["wheel"], (1, 1))

    def test_a_game_the_library_does_not_hold_is_left_out(self) -> None:
        found = media_fill.plan(["gone"])

        self.assertEqual(found["games"], 0)
        self.assertEqual({counts for counts in self.rows(found).values()}, {(0, 0)})

    def test_only_the_kinds_asked_are_fetched(self) -> None:
        result = self.ran(media_fill.start([self.id_of(self.folder)], ["wheel"]))

        self.assertEqual(self.placed(), {WHEEL: _url("wheel.png")})
        self.assertEqual(self.placed(self.other), {})
        self.assertEqual(result["filled"], 1)

    def test_no_games_named_is_the_whole_library(self) -> None:
        result = self.ran(media_fill.start(kinds=["wheel"]))

        self.assertIn(WHEEL, self.placed())
        self.assertIn(f"(Wheel) {OTHER}.png", self.placed(self.other))
        self.assertEqual((result["games"], result["unmatched"]), (3, 1))

    def test_a_hidden_kind_is_never_fetched_even_when_asked(self) -> None:
        self.policy.set("hidden_media_kinds", ["wheel"])

        self.ran(media_fill.start([self.id_of(self.folder)], ["wheel", "backglass"]))
        self.ran(media_fill.start(slots=[(self.id_of(self.other), "wheel")]))

        self.assertEqual(set(self.placed()), {f"(Backglass) {FOLDER}.png"})
        self.assertEqual(self.placed(self.other), {})

    def test_a_slot_fetches_that_one_kind(self) -> None:
        self.ran(media_fill.start(slots=[(self.id_of(self.folder), "backglass")]))

        self.assertEqual(set(self.placed()), {f"(Backglass) {FOLDER}.png"})

    def test_the_size_the_display_is_set_to_is_the_one_fetched(self) -> None:
        self.config.read_dict({"media": {"playfield_resolution": "1k"}})

        self.ran(media_fill.start([self.id_of(self.folder)], ["playfield"]))

        self.assertEqual(self.placed(), {f"(Playfield) {FOLDER}.png": _url("table-1k.png")})

    def test_a_file_already_there_is_not_replaced(self) -> None:
        held = self.game("Held", "fathom", **{"wheel.png": b"mine"})

        self.ran(media_fill.start([self.id_of(held)], ["wheel"]))

        self.assertEqual(self.placed(held), {"wheel.png": "mine"})
        self.downloads.assert_not_called()

    def test_it_will_not_run_beside_another_fill(self) -> None:
        with jobs.track(jobs.KIND_MEDIA_FILL), self.assertRaises(service_errors.BlockedError):
            media_fill.start()


def _md5(data: bytes) -> str:
    return hashlib.md5(data).hexdigest()


WHEEL = f"(Wheel) {FOLDER}.png"
PLAYFIELD = f"(Playfield) {FOLDER}.png"
OLD_WHEEL = b"the wheel as it was"
OLD_TABLE = b"the playfield as it was"

# The catalog after it replaced the wheel and the playfield.
REPLACED = {"fathom": {
    "wheel": _url("wheel-new.png"), "wheel_md5": "wheel-new-md5",
    "4k": {"table": _url("table-4k-new.png"), "table_md5": "table-4k-new-md5"},
    "1k": {"table": _url("table-1k-new.png"), "table_md5": "table-1k-new-md5"},
}}


class UpdateTests(_Library):
    def setUp(self) -> None:
        super().setUp()
        loaded = patch("common.online.vpsdb_cache.VPinMediaDatabase.load",
                       return_value=REPLACED)
        self.load = loaded.start()
        self.addCleanup(loaded.stop)
        replaced = patch("common.online.vpsdb_media.download_file", self.downloads)
        replaced.start()
        self.addCleanup(replaced.stop)

    def ours(self, name: str, data: bytes, recorded: bytes | None = None) -> Path:
        path = self.folder / "medias" / name
        path.parent.mkdir(exist_ok=True)
        path.write_bytes(data)
        media_placement.record_origin(self.folder, path, "vpinmediadb",
                                      _md5(data if recorded is None else recorded))
        return path

    def recorded(self, name: str) -> str:
        return str(asset_origin.sources(self.folder)[f"medias/{name}"]["hash"])

    def test_ours_and_stale_is_replaced_at_the_configured_size(self) -> None:
        self.ours(WHEEL, OLD_WHEEL)
        self.ours(PLAYFIELD, OLD_TABLE)

        result = media_fill.update_downloaded()

        placed = self.placed()
        self.assertEqual(placed[WHEEL], _url("wheel-new.png"))
        self.assertEqual(placed[PLAYFIELD], _url("table-4k-new.png"))
        self.assertEqual(self.recorded(WHEEL), "wheel-new-md5")
        self.assertEqual(result["updated"], 2)

    def test_the_catalog_is_read_afresh(self) -> None:
        self.ours(WHEEL, OLD_WHEEL)
        held = {"fathom": {"wheel": _url("wheel.png"), "wheel_md5": _md5(OLD_WHEEL)}}

        with patch.object(asset_sources, "_MANIFEST", held):
            media_fill.update_downloaded()

        self.assertEqual(self.placed()[WHEEL], _url("wheel-new.png"))

    def test_ours_and_current_is_not_read(self) -> None:
        self.load.return_value = {"fathom": {"wheel": _url("wheel.png"),
                                             "wheel_md5": _md5(OLD_WHEEL)}}
        self.ours(WHEEL, OLD_WHEEL)

        with patch("common.online.vpsdb_media.file_md5") as hashed:
            result = media_fill.update_downloaded()

        hashed.assert_not_called()
        self.assertEqual(self.placed()[WHEEL], OLD_WHEEL.decode())
        self.assertEqual(result["updated"], 0)

    def test_art_still_published_at_another_size_is_left(self) -> None:
        self.load.return_value = {"fathom": {
            "1k": {"table": _url("table-1k.png"), "table_md5": _md5(OLD_TABLE)},
            "4k": {"table": _url("table-4k-new.png"), "table_md5": "table-4k-new-md5"}}}
        self.ours(PLAYFIELD, OLD_TABLE)

        media_fill.update_downloaded()

        self.assertEqual(self.placed()[PLAYFIELD], OLD_TABLE.decode())

    def test_art_changed_since_it_was_recorded_is_left(self) -> None:
        self.ours(WHEEL, b"drawn over", recorded=OLD_WHEEL)

        media_fill.update_downloaded()

        self.assertEqual(self.placed()[WHEEL], "drawn over")
        self.downloads.assert_not_called()

    def test_art_with_no_ledger_entry_is_left(self) -> None:
        path = self.folder / "medias" / WHEEL
        path.parent.mkdir(exist_ok=True)
        path.write_bytes(OLD_WHEEL)

        media_fill.update_downloaded()

        self.assertEqual(self.placed()[WHEEL], OLD_WHEEL.decode())
        self.downloads.assert_not_called()

    def test_a_kind_this_library_does_not_collect_is_left(self) -> None:
        self.policy.set("hidden_media_kinds", ["wheel"])
        self.ours(WHEEL, OLD_WHEEL)

        media_fill.update_downloaded()

        self.assertEqual(self.placed()[WHEEL], OLD_WHEEL.decode())

    def test_a_source_switched_off_is_not_asked(self) -> None:
        self.policy.set("hidden_sources", ["vpinmediadb"])
        self.ours(WHEEL, OLD_WHEEL)

        media_fill.update_downloaded()

        self.assertEqual(self.placed()[WHEEL], OLD_WHEEL.decode())
        self.downloads.assert_not_called()

    def test_a_failed_download_keeps_the_file_and_its_record(self) -> None:
        self.ours(WHEEL, OLD_WHEEL)
        self.downloads.side_effect = OSError("offline")

        result = media_fill.update_downloaded()

        self.assertEqual(self.placed(), {WHEEL: OLD_WHEEL.decode()})
        self.assertEqual(self.recorded(WHEEL), _md5(OLD_WHEEL))
        self.assertEqual(result["failed"], 1)

    def test_the_progress_says_what_the_job_is_doing(self) -> None:
        reporter = MagicMock()

        media_fill.update_downloaded(reporter)

        self.assertEqual(reporter.progress.call_args.args[2],
                         i18n.t("said.updating_art_for", game=FOLDER))


class ArtDueTests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = configparser.ConfigParser()

    def test_never_compared_is_due(self) -> None:
        self.assertTrue(vpsdb_sync.art_due(self.config))

    def test_compared_today_is_not_due_and_yesterday_is(self) -> None:
        self.config.read_dict({"vpsdb": {"art_checked": "2026-01-01T00:00:00Z"}})
        was = timestamps.iso_to_epoch("2026-01-01T00:00:00Z") or 0

        self.assertFalse(vpsdb_sync.art_due(self.config, was + 3600))
        self.assertTrue(vpsdb_sync.art_due(self.config, was + 86400))

    def test_switched_off_is_never_due(self) -> None:
        self.config.read_dict({"updates": {"update_downloaded_art": "false"}})
        self.assertFalse(vpsdb_sync.art_due(self.config))

    def test_a_running_fill_leaves_it_due(self) -> None:
        with patch.object(media_fill, "start_update", return_value=False):
            self.assertFalse(vpsdb_sync.update_art(self.config))
        self.assertTrue(vpsdb_sync.art_due(self.config))

    def test_a_started_sweep_is_stamped(self) -> None:
        with patch.object(media_fill, "start_update", return_value=True):
            self.assertTrue(vpsdb_sync.update_art(self.config))
        self.assertFalse(vpsdb_sync.art_due(self.config))


class QueueTests(_Library):
    def setUp(self) -> None:
        super().setUp()
        media_fill.reset_for_tests()
        jobs.reset_for_tests()
        self.addCleanup(media_fill.reset_for_tests)
        self.addCleanup(jobs.reset_for_tests)

    def test_a_request_runs_as_a_job(self) -> None:
        media_fill.request([self.folder])

        deadline = time.monotonic() + 10
        while media_fill._running or jobs.active(jobs.KIND_MEDIA_FILL):
            self.assertLess(time.monotonic(), deadline, "the fill never finished")
            time.sleep(0.02)
        self.assertIn(f"(Wheel) {FOLDER}.png", self.placed())

    def test_switched_off_a_request_does_nothing(self) -> None:
        self.config.read_dict({"updates": {"get_art_for_new_games": "false"}})
        with patch.object(media_fill, "_start") as start:
            media_fill.request([self.folder])

        start.assert_not_called()

    def test_a_request_during_a_run_joins_it(self) -> None:
        batches: list[list[str]] = []

        def one_batch(folders: list[str], *_: object) -> dict[str, int]:
            batches.append(list(folders))
            if len(batches) == 1:
                media_fill.request(["second"])
            return {"games": len(folders), "filled": 0, "unmatched": 0, "failed": 0}

        with patch.object(media_fill, "_start") as start, \
                patch.object(media_fill, "_fill", side_effect=one_batch):
            media_fill.request(["first"])
            media_fill._work(MagicMock())

        self.assertEqual(batches, [["first"], ["second"]])
        start.assert_called_once()
        self.assertFalse(media_fill._running)


if __name__ == "__main__":
    unittest.main()
