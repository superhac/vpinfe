"""Converting a source into entries, through the context and nothing else.

The importer holds no path of ours and opens no file of ours. Everything it does to the
library goes through what it was handed, which is the guarantee the whole model rests on
- so a wall it hits here is a gap in the contract rather than a special case to carve.
"""

from __future__ import annotations

import tempfile
import unittest
import unittest.mock
from pathlib import Path

from fastapi.testclient import TestClient

import httpapi
from common import extensions
from common.extensions import host, store
from common.extensions.contract import ContractError
from common.games import game_repository, locations

REPO = Path(__file__).resolve().parents[2]
FIXTURE = REPO / "tests" / "fixtures" / "pinballx"
BASE = "/ext/library_importer"
VPX = "Visual Pinball X"


class AdoptCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.library = self.root / "library"
        self.library.mkdir()

        self.locations = locations.LocationStore(self.root / "locations.json")
        patcher = unittest.mock.patch.object(locations, "get_location_store",
                                             return_value=self.locations)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.locations.mark_migration(locations.SEEDED)

        self.store = store.ExtensionStore(self.root / "extensions.json")
        self.registry = host.Registry(self.store)
        extensions.set_registry(self.registry)
        self.addCleanup(extensions.set_registry, host.Registry())
        self.addCleanup(self.registry.clear)
        self.record = self.registry.load(host.BUNDLED_DIR / "library_importer")
        self.assertEqual(self.record.state, host.LOADED, self.record.reason)

        self.client = TestClient(httpapi.create_api_app(), raise_server_exceptions=False)
        self.client.put("/locations/one", json={"path": str(self.library)})
        self.client.put("/locations/one/write-to", json={})
        game_repository.all_games(reload=True)
        self.addCleanup(game_repository.all_games, True)

        self.client.put(f"{BASE}/source", json={"path": str(FIXTURE)})

    def imported(self) -> dict:
        """Run the conversion on this thread, so the assertions are about a finished
        import rather than a race with one."""
        from vpinfe_ext_library_importer import adopt, pinballx

        library = pinballx.read(FIXTURE)
        return adopt.run(self.ctx(), library, [VPX])

    def ctx(self):
        """The context the host handed the extension, which is the only thing under
        test here - reaching past it is what the whole design forbids."""
        return self._ctx


class ImportTests(AdoptCase):
    def setUp(self) -> None:
        super().setUp()
        # The same context register() was given, so what the test drives is what runs.
        from common.extensions.context import ExtensionContext
        self._ctx = ExtensionContext(self.record.manifest, self.store,
                                     on_failure=lambda why: None)
        self._ctx.files.set_roots([str(FIXTURE)])

    def test_every_game_in_the_system_becomes_an_entry(self) -> None:
        report = self.imported()

        self.assertEqual(report["games"], 3)
        self.assertEqual(report["failed"], 0)

    def test_a_folder_is_named_the_way_our_own_are(self) -> None:
        """The source's description is already Title (Manufacturer Year), which is the
        convention we arrived at separately."""
        self.imported()

        self.assertTrue((self.library / "Attack from Mars (Bally 1995)").is_dir())
        self.assertTrue((self.library / "Taxi (Williams 1988)").is_dir())

    def test_what_the_source_knew_about_the_machine_comes_across(self) -> None:
        """The name is the machine, not the folder. PinballX has no title of its own, so
        without lifting one out of the description every imported game would repeat its
        manufacturer and year in the column beside the ones that hold them."""
        self.imported()
        game_repository.all_games(reload=True)

        rows = {row["name"]: row for row in self.client.get("/games").json()["games"]}
        afm = rows["Attack from Mars"]
        self.assertEqual(afm["manufacturer"], "Bally")
        self.assertEqual(afm["year"], "1995")
        self.assertEqual(afm["themes"], ["Aliens", "Outer Space"])

    def test_artwork_lands_in_our_slots(self) -> None:
        self.imported()

        folder = self.library / "Attack from Mars (Bally 1995)"
        landed = sorted(one.name for one in (folder / "medias").iterdir())
        self.assertTrue(any("Wheel" in one for one in landed), landed)
        self.assertTrue(any("Playfield" in one for one in landed), landed)

    def test_a_kind_we_have_no_slot_for_is_reported_not_guessed_at(self) -> None:
        report = self.imported()
        rows = {row["key"]: row for row in report["rows"]}

        self.assertEqual(rows["Taxi"]["skipped_media"], [])

    def test_a_source_whose_tables_are_elsewhere_still_imports(self) -> None:
        """Entries with artwork and no game file, which the library has a word for."""
        report = self.imported()

        self.assertEqual(report["tables"], 0)
        self.assertEqual(report["games"], 3)

    def test_one_game_failing_does_not_stop_the_rest(self) -> None:
        """An import of six hundred stopping on the one folder somebody already had
        would be worse than useless."""
        (self.library / "Taxi (Williams 1988)").mkdir()

        report = self.imported()

        self.assertEqual(report["games"], 2)
        self.assertEqual(report["failed"], 1)
        failed = next(row for row in report["rows"] if row["key"] == "Taxi")
        self.assertTrue(failed["error"])

    def test_running_it_twice_creates_nothing_the_second_time(self) -> None:
        """It only ever creates, so the second run has nowhere to put anything rather
        than quietly writing over the first."""
        self.imported()

        again = self.imported()

        self.assertEqual(again["games"], 0)
        self.assertEqual(again["failed"], 3)


class BoundsTests(AdoptCase):
    def setUp(self) -> None:
        super().setUp()
        from common.extensions.context import ExtensionContext
        self._ctx = ExtensionContext(self.record.manifest, self.store,
                                     on_failure=lambda why: None)

    def test_a_file_outside_what_it_declared_is_refused(self) -> None:
        """Tighter than the same check on a route, and it can be: this one knows which
        extension is asking."""
        self._ctx.files.set_roots([str(self.root / "somewhere-else")])
        game_id = self._ctx.games.create("Probe")
        stray = self.root / "stray.png"
        stray.write_bytes(b"art")

        with self.assertRaises(ContractError):
            self._ctx.games.put_media(game_id, "wheel", stray)

    def test_a_scope_the_manifest_never_declared_is_refused(self) -> None:
        """Which is what makes declaring them mean something."""
        from common.extensions.games import ExtensionGames

        modest = ExtensionGames("modest", ("games:read",), self._ctx.files)

        with self.assertRaises(ContractError):
            modest.create("Probe")

    def test_an_unknown_media_kind_is_refused(self) -> None:
        self._ctx.files.set_roots([str(FIXTURE)])
        game_id = self._ctx.games.create("Probe")
        art = (FIXTURE / "Media" / VPX / "Wheel Images"
               / "Attack from Mars (Bally 1995).png")

        with self.assertRaises(ValueError):
            self._ctx.games.put_media(game_id, "hologram", art)


if __name__ == "__main__":
    unittest.main()


class FolderNameTests(unittest.TestCase):
    """The folder a name becomes is core's rule, and the importer asks rather than
    reproduces it.

    A real library held both `Star Trek: The Next Generation (Williams 1993)` and
    `Star Trek - The Next Generation (Williams 1993)`. Core strips the colon, so the
    first two are one folder; the importer's own copy of the rule did not, so it thought
    they were two and the second failed on a name already taken.
    """

    def test_core_answers_what_a_name_becomes(self) -> None:
        from common.extensions.games import ExtensionGames

        games = ExtensionGames("probe", ("games:read",), None)

        self.assertEqual(
            games.folder_name_for("Star Trek: The Next Generation (Williams 1993)"),
            "Star Trek The Next Generation (Williams 1993)")

    def test_reading_a_name_is_a_read(self) -> None:
        """It tells an extension what core would do, so it is gated like anything else
        that reads."""
        from common.extensions.games import ExtensionGames

        with self.assertRaises(ContractError):
            ExtensionGames("silent", (), None).folder_name_for("Anything")


class CompanionTests(unittest.TestCase):
    """A table's backglass and settings come with it.

    Measured on a real library: 696 of 702 tables had a `.directb2s` beside them and 704
    had an `.ini`. Bringing the `.vpx` alone left every one of those behind, which is a
    game with no backglass - the single largest thing the import was losing.
    """

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.source = self.root / "Tables"
        self.source.mkdir()

    def _table(self, stem: str, *companions: str) -> Path:
        table = self.source / f"{stem}.vpx"
        table.write_bytes(b"table")
        for one in companions:
            (self.source / one).write_bytes(b"beside it")
        return table

    def test_what_travels_with_a_table(self) -> None:
        from common.games.game_service import companions_beside

        table = self._table("Taxi (Williams 1988)",
                            "Taxi (Williams 1988).directb2s",
                            "Taxi (Williams 1988).ini",
                            "Taxi (Williams 1988).vbs",
                            "Taxi (Williams 1988).pov")

        found = {one.name for one in companions_beside(table)}

        self.assertEqual(len(found), 4)
        self.assertIn("Taxi (Williams 1988).directb2s", found)

    def test_a_neighbour_is_not_a_companion(self) -> None:
        """Matched on the exact stem, or `Taxi.vpx` collects `Taxi 2`'s backglass."""
        from common.games.game_service import companions_beside

        table = self._table("Taxi", "Taxi.directb2s")
        (self.source / "Taxi 2.directb2s").write_bytes(b"another game")

        found = {one.name for one in companions_beside(table)}

        self.assertEqual(found, {"Taxi.directb2s"})

    def test_something_that_is_not_a_companion_kind_stays(self) -> None:
        """The list is the one the export bundle ships, because these are the same
        question asked in two directions."""
        from common.games.game_service import companions_beside

        table = self._table("Taxi", "Taxi.directb2s", "Taxi.png", "Taxi.txt")

        found = {one.name for one in companions_beside(table)}

        self.assertEqual(found, {"Taxi.directb2s"})


class RowShapeTests(unittest.TestCase):
    """Every row the run produces has the same keys.

    The report sums across all of them, so one row built somewhere else and missing a
    key fails the whole import at the end - after the copying, which is the worst moment
    to find out. It happened: a second build of a machine builds its own row, and only
    the first path had been taught the new counts.
    """

    def test_both_kinds_of_row_carry_the_same_counts(self) -> None:
        import inspect

        from extensions.library_importer import adopt

        source = inspect.getsource(adopt)
        rows = [one for one in source.splitlines() if '"key": game.key, "name": name' in one]
        self.assertEqual(len(rows), 2, "expected one row shape per path")

        counted = ("media", "companions", "roms", "altdata")
        for name in ("_one", "_another_build"):
            body = inspect.getsource(getattr(adopt, name))
            for key in counted:
                with self.subTest(function=name, key=key):
                    self.assertIn(f'"{key}"', body)
