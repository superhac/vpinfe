"""Taking 3.0's state back off an install.

The round trip is the real test: a 2.x install, migrated, reset, and the `.info` files
byte-identical to what went in. The second one matters more - running the migrations
again and asserting every one did work is what keeps the marker list honest, because a
migration whose marker nobody recorded here would report success while doing nothing.
"""

from __future__ import annotations

import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from common import install_identity
from common.config_store import ConfigStore
from common.games import revert_3x
from common.games.collection_migration import ensure_last_played, ensure_order_direction
from common.games.collection_store import CollectionStore
from common.games.game_identity import ensure_unique_ids, game_id
from common.games.game_parser import GameParser
from common.games.info_migration import schema_of
from common.games.table_identity import ensure_unique_table_ids
from common.games.tables import TABLES_KEY, table_id
from tests.support.browser_session import free_port
from tests.support.library import TempTree, write_game

LEGACY_INFO = {
    "Info": {"Title": "Dr. Dude", "VPSId": "vps-dude", "Rom": "dd_l2",
             "Authors": "someone"},
    "User": {"Rating": 4, "StartCount": 12, "Tags": ["fast"]},
    "VPXFile": {"filename": "Dr. Dude.vpx", "filehash": "abc123", "rom": "dd_l2"},
    "Medias": {"wheel": {"Source": "user"}},
}

LEGACY_INI = """[Settings]
gamerootdir = {games}
"""

LEGACY_COLLECTIONS = """[Favorites]
vpsids = vps-dude,vps-taxi

[Recent]
type = filter
sort_by = LastRun
order_by = Ascending
"""


def legacy_info(title: str, vps_id: str) -> dict:
    """One `.info` in the shape 2.x wrote, with nothing 3.0 stamps on it."""
    info = json.loads(json.dumps(LEGACY_INFO))
    info["Info"]["Title"] = title
    info["Info"]["VPSId"] = vps_id
    info["VPXFile"]["filename"] = f"{title}.vpx"
    return info


def unversioned_count(games_root: Path) -> int:
    return sum(1 for path in games_root.glob("*/*.info")
               if schema_of(json.loads(path.read_text(encoding="utf-8"))) is None)


def table_id_count(games_root: Path) -> int:
    """How many tables across the library carry an id. A 2.x `.info` has no tables
    section at all, so this is zero until the backfill has run."""
    return sum(
        1
        for path in games_root.glob("*/*.info")
        for entry in (json.loads(path.read_text(encoding="utf-8")).get(TABLES_KEY)
                      or {}).values()
        if isinstance(entry, dict) and table_id(entry))


def run_startup_migrations(games_root: Path, config_dir: Path) -> dict:
    """The one-time conversions a start performs, in main.py's order, and what each did.

    Every value is a count or a flag of work actually done. A migration whose marker is
    already set answers zero, so this is what turns "the reset cleared every marker"
    into an assertion instead of a claim.
    """
    work: dict[str, int | bool] = {}

    had_json = (config_dir / "vpinfe.json").exists()
    config = ConfigStore(str(config_dir / "vpinfe.ini"))
    work["settings_converted"] = not had_json and (config_dir / "vpinfe.json").exists()

    work["install_id_minted"] = not install_identity.install_id(config)
    install_identity.ensure_id(config)

    unversioned = unversioned_count(games_root)
    table_ids = table_id_count(games_root)
    games = GameParser(str(games_root)).getAllGames()
    work["game_ids_minted"] = sum(1 for game in games if not game_id(game))
    ensure_unique_ids(games)
    ensure_unique_table_ids(games)
    work["info_files_migrated"] = unversioned - unversioned_count(games_root)
    work["table_ids_minted"] = table_id_count(games_root) - table_ids

    collections = CollectionStore(str(config_dir / "collections.json"))
    work["members_rekeyed"] = collections.migrate_membership_to_game_ids(games)
    work["last_played_seeded"] = ensure_last_played(collections)
    work["orders_pinned"] = ensure_order_direction(collections)
    return work


class StubHub(HTTPServer):
    """Something answering on the hub port. `name` is what its discovery document says,
    so a test can be a VPinFE or can be whatever else grabbed the port first."""

    def __init__(self, name: str | None):
        self.name = name
        super().__init__(("127.0.0.1", 0), _StubHandler)
        self._thread = threading.Thread(target=self.serve_forever, daemon=True)
        self._thread.start()

    @property
    def port(self) -> int:
        return self.server_address[1]

    def stop(self) -> None:
        self.shutdown()
        self.server_close()
        self._thread.join(timeout=5)


class _StubHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:                                   # noqa: N802 - BaseHTTPRequestHandler
        name = self.server.name
        body = b"not json" if name is None else json.dumps({"name": name}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args) -> None:
        pass


class RevertTestCase(TempTree):
    """A 2.x install: a library of unversioned `.info` files and an ini pair beside it."""

    GAMES = (("Dr. Dude", "vps-dude"), ("Taxi", "vps-taxi"), ("Whirlwind", "vps-whirl"))

    def setUp(self) -> None:
        super().setUp()
        self.games_root = self.root / "tables"
        self.config_dir = self.root / "config"
        self.games_root.mkdir()
        self.config_dir.mkdir()
        self.closed_port = free_port()
        for title, vps_id in self.GAMES:
            write_game(self.games_root, title, info=legacy_info(title, vps_id))
        (self.config_dir / "vpinfe.ini").write_text(
            LEGACY_INI.format(games=self.games_root), encoding="utf-8")
        (self.config_dir / "collections.ini").write_text(LEGACY_COLLECTIONS,
                                                         encoding="utf-8")
        self.original = self._library_bytes()

    def _library_bytes(self) -> dict[str, bytes]:
        return {path.name: path.read_bytes() for path in self.games_root.glob("*/*.info")}

    def _backup_copies(self) -> list[str]:
        return sorted(path.name for path in self.root.rglob("*")
                      if ".vpinfe-" in path.name or path.name.startswith(".vpinfe_write_"))

    def _reset(self, **kwargs) -> dict:
        kwargs.setdefault("hub_port", self.closed_port)
        return revert_3x.reset(self.games_root, self.config_dir, **kwargs)

    def _migrate(self) -> dict:
        return run_startup_migrations(self.games_root, self.config_dir)


class RoundTripTests(RevertTestCase):
    def test_a_migrated_install_comes_back_exactly_as_it_went_in(self):
        self._migrate()
        self.assertNotEqual(self._library_bytes(), self.original)

        self._reset()

        self.assertEqual(self._library_bytes(), self.original)
        self.assertEqual(self._backup_copies(), [])
        self.assertEqual(sorted(p.name for p in self.config_dir.iterdir()),
                         ["collections.ini", "vpinfe.ini"])

    def test_every_migration_runs_again_after_a_reset(self):
        """The point of the whole exercise. A marker the reset misses makes the
        migration behind it a silent no-op, and a second pass is the only thing that
        can tell that apart from a pass that worked."""
        first = self._migrate()
        self.assertTrue(all(first.values()), first)

        self._reset()
        second = self._migrate()

        self.assertEqual(second, first)

    def test_a_second_migration_without_a_reset_does_nothing(self):
        """The defect this tool exists for, asserted so the test above cannot pass by
        accident: without the reset, every one of those counts is zero."""
        self._migrate()

        self.assertFalse(any(self._migrate().values()))

    def test_the_2x_files_themselves_are_never_written(self):
        self._migrate()
        ini = (self.config_dir / "vpinfe.ini").read_bytes()
        collections = (self.config_dir / "collections.ini").read_bytes()

        self._reset()

        self.assertEqual((self.config_dir / "vpinfe.ini").read_bytes(), ini)
        self.assertEqual((self.config_dir / "collections.ini").read_bytes(), collections)


class ConfigTests(RevertTestCase):
    def test_a_hand_made_repro_file_is_not_a_backup(self):
        """The reset names what it deletes. Anything shaped as "delete what looks like a
        backup" eats the repro copies kept beside the real files."""
        self._migrate()
        for name in ("collections.json.bak-repro3", "vpinfe.json.bak-repro"):
            (self.config_dir / name).write_text("mine", encoding="utf-8")

        self._reset()

        self.assertTrue((self.config_dir / "collections.json.bak-repro3").exists())
        self.assertTrue((self.config_dir / "vpinfe.json.bak-repro").exists())

    def test_the_2x_files_of_other_features_are_left_alone(self):
        for name in ("roms.json", "vpsdb.json"):
            (self.config_dir / name).write_text("{}", encoding="utf-8")
        for name in ("themes", "collection_icons", "plugin_profiles", "cache", "assets"):
            (self.config_dir / name).mkdir()
        self._migrate()

        self._reset()

        for name in ("roms.json", "vpsdb.json", "themes", "collection_icons",
                     "plugin_profiles", "cache", "assets"):
            self.assertTrue((self.config_dir / name).exists(), name)

    def test_3x_only_files_go_whether_or_not_a_migration_wrote_them(self):
        self._migrate()
        (self.config_dir / "players.json").write_text("{}", encoding="utf-8")
        (self.config_dir / "manager-ui-state.json").write_text("{}", encoding="utf-8")
        options = self.config_dir / "theme_user_options"
        options.mkdir()
        (options / "Trifecta.json").write_text("{}", encoding="utf-8")

        result = self._reset()

        self.assertFalse(options.exists())
        self.assertIn("players.json", result["config_removed"])
        self.assertIn("manager-ui-state.json", result["config_removed"])

    def test_a_half_written_temp_file_is_swept_up(self):
        self._migrate()
        (self.config_dir / ".vpinfe_write_abc.tmp").write_text("", encoding="utf-8")
        (self.games_root / "Taxi" / ".vpinfe_write_xyz.tmp").write_text("", encoding="utf-8")

        self._reset()

        self.assertEqual(self._backup_copies(), [])

    def test_an_install_with_no_ini_comes_back_as_a_fresh_install(self):
        """Not a keep-list. An install that never had 2.x settings has nothing to go
        back to, and first-run defaults are the only baseline that occurs in the wild."""
        (self.config_dir / "vpinfe.ini").unlink()
        (self.config_dir / "collections.ini").unlink()
        self._migrate()

        result = self._reset()

        self.assertEqual(result["end_state"], revert_3x.FRESH_INSTALL)
        self.assertFalse((self.config_dir / "vpinfe.json").exists())
        self.assertTrue(ConfigStore(str(self.config_dir / "vpinfe.ini")).is_new)

    def test_an_install_with_an_ini_reports_that_it_kept_it(self):
        self._migrate()

        self.assertEqual(self._reset()["end_state"], revert_3x.RESTORED_FROM_2X)


class LibraryTests(RevertTestCase):
    def test_a_game_3x_added_loses_the_info_3x_made_for_it(self):
        """And it is the id backfill that made it, which writes a game_id and no schema
        stamp - so "is it stamped" is the wrong question to ask of the file."""
        self._migrate()
        write_game(self.games_root, "New Game", info=None)
        ensure_unique_ids(GameParser(str(self.games_root)).getAllGames())
        made = self.games_root / "New Game" / "New Game.info"
        self.assertEqual(json.loads(made.read_text(encoding="utf-8")).keys(), {"vpinfe"})

        result = self._reset()

        self.assertFalse(made.exists())
        self.assertEqual(result["deleted_info"], ["New Game"])

    def test_a_2x_file_nothing_has_upgraded_yet_is_left_alone(self):
        """It has no backup either, but 3.0 never wrote it - so there is nothing of
        3.0's in that folder to take out, and deleting it would destroy 2.x data."""
        untouched = write_game(self.games_root, "Fresh Import",
                               info=legacy_info("Fresh Import", "vps-fresh"))
        before = (untouched / "Fresh Import.info").read_bytes()

        result = self._reset()

        self.assertEqual((untouched / "Fresh Import.info").read_bytes(), before)
        self.assertEqual(result["deleted_info"], [])

    def test_a_file_too_broken_to_read_is_left_alone(self):
        self._migrate()
        broken = self.games_root / "Taxi" / "Taxi.info"
        for path in broken.parent.glob("*.vpinfe-*"):
            path.unlink()
        broken.write_text("{ not json", encoding="utf-8")

        result = self._reset()

        self.assertEqual(broken.read_text(encoding="utf-8"), "{ not json")
        self.assertEqual(result["deleted_info"], [])

    def test_config_only_leaves_every_info_where_it_is(self):
        self._migrate()
        migrated = self._library_bytes()

        self._reset(config_only=True)

        self.assertEqual(self._library_bytes(), migrated)
        self.assertFalse((self.config_dir / "vpinfe.json").exists())

    def test_the_schema_2_backup_a_restore_left_behind_is_not_restored(self):
        """`restorable_backup` takes anything at or below the schema it is given, so the
        default would put back a schema 2 file rather than the 2.x original under it."""
        self._migrate()
        from common.games.info_maintenance import restore_library
        restore_library(self.games_root)          # leaves a schema 2 copy in each folder
        self._migrate()

        self._reset()

        self.assertEqual(self._library_bytes(), self.original)


class DryRunTests(RevertTestCase):
    def test_it_changes_nothing(self):
        self._migrate()
        write_game(self.games_root, "New Game", info=None)
        ensure_unique_ids(GameParser(str(self.games_root)).getAllGames())
        before = self._library_bytes()
        config_before = sorted(p.name for p in self.config_dir.iterdir())

        self._reset(dry_run=True)

        self.assertEqual(self._library_bytes(), before)
        self.assertEqual(sorted(p.name for p in self.config_dir.iterdir()), config_before)

    def test_it_names_the_same_work_the_run_does(self):
        self._migrate()
        write_game(self.games_root, "New Game", info=None)
        ensure_unique_ids(GameParser(str(self.games_root)).getAllGames())

        planned = self._reset(dry_run=True)
        done = self._reset()

        self.assertEqual(planned["deleted_info"], ["New Game"])
        self.assertEqual(planned["deleted_info"], done["deleted_info"])
        self.assertEqual(planned["config_removed"], done["config_removed"])
        self.assertEqual(planned["restored"], done["restored"])

    def test_it_is_allowed_while_vpinfe_is_running(self):
        """It writes nothing, so refusing would be friction with nothing behind it. It
        does say the real run will refuse, which is what the tester needs to know."""
        self._migrate()
        hub = StubHub("VPinFE")
        self.addCleanup(hub.stop)

        result = self._reset(dry_run=True, hub_port=hub.port)

        self.assertTrue(result["instance_running"])
        self.assertTrue((self.config_dir / "vpinfe.json").exists())


class RunningInstanceTests(RevertTestCase):
    def test_it_refuses_while_vpinfe_is_running(self):
        """Its failure mode is silence: a reset that looks like it worked and is then
        written straight back over by the live process, markers and all."""
        self._migrate()
        hub = StubHub("VPinFE")
        self.addCleanup(hub.stop)
        migrated = self._library_bytes()

        with self.assertRaises(revert_3x.InstanceRunningError):
            self._reset(hub_port=hub.port)

        self.assertTrue((self.config_dir / "vpinfe.json").exists())
        self.assertEqual(self._library_bytes(), migrated)

    def test_something_else_on_that_port_does_not_block_a_reset(self):
        """The port is configurable and ordinary. Refusing on a bare TCP connect would
        make an unrelated server on 8001 look like a running VPinFE."""
        self._migrate()
        for name in ("Grafana", None):
            with self.subTest(answers=name):
                hub = StubHub(name)
                self.addCleanup(hub.stop)
                self.assertFalse(revert_3x.running_instance(hub.port))

    def test_a_port_nobody_is_listening_on_is_not_a_running_instance(self):
        self.assertFalse(revert_3x.running_instance(self.closed_port))


class LiveRefusalTests(unittest.TestCase):
    """The probe against a real VPinFE rather than a stand-in.

    The stub above proves what the code does with an answer; this proves the answer is
    the one a running instance actually gives, which is the half that goes stale when
    the hub moves or its discovery document changes.
    """

    def test_a_real_instance_is_seen_on_its_hub_port(self):
        from tempfile import TemporaryDirectory

        from tests.support.live_instance import LiveInstance

        with TemporaryDirectory() as games:
            write_game(games, "Dr. Dude", info=legacy_info("Dr. Dude", "vps-dude"))
            with LiveInstance(Path(games)) as live:
                live.wait_for_api()
                port = live.ports["manager"]
                self.assertTrue(revert_3x.running_instance(port))
                with self.assertRaises(revert_3x.InstanceRunningError):
                    revert_3x.reset(games, live.config_dir, hub_port=port)
        self.assertFalse(revert_3x.running_instance(port))


if __name__ == "__main__":
    unittest.main()
