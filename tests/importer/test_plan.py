"""What an import would do, before it does any of it.

Two things this holds. Every source is an option with a derived default, so "no ROMs came
across" is something somebody chose and can see they chose. And an import can be run more
than once - a first pass fails partway, or the games come now and the ROMs when the old
machine is back - so what is already here is recognised rather than collided with.
"""

from __future__ import annotations

import unittest

from common.extensions import host

host.Registry().load(host.BUNDLED_DIR / "library_importer")

from vpinfe_ext_library_importer import plan as plan_for  # noqa: E402
from vpinfe_ext_library_importer.source import (  # noqa: E402
    SourceGame,
    SourceLibrary,
    SourceMedia,
    SourceSystem,
)


def _library(*games, tables_dir="/src/tables", roms="/src/roms"):
    return SourceLibrary(source_id="pinballx", root="/src", systems=(
        SourceSystem(name="Visual Pinball X", games=tuple(games),
                     tables_dir=tables_dir, working_path=roms),))


def _game(key, **fields):
    fields.setdefault("display_name", key)
    return SourceGame(key=key, **fields)


class SourceTests(unittest.TestCase):
    def test_what_can_be_worked_out_is_the_default(self) -> None:
        library = _library(_game("Taxi", media=(
            SourceMedia(source_kind="Wheel Images", path="/src/Media/VPX/Wheel/Taxi.png"),)))

        found = {one.key: one for one in plan_for.derive_sources(library)}

        self.assertEqual(found["tables"].path, "/src/tables")
        self.assertTrue(found["tables"].derived)
        self.assertTrue(found["media"].derived)

    def test_a_kind_with_nowhere_to_go_is_not_offered(self) -> None:
        """A field that carries nothing is a promise the code cannot keep. Registry
        settings have no destination on this platform at all - VPinMAME's per-ROM values
        live in memory and nothing persists them - so they are read and not offered."""
        found = {one.key for one in plan_for.derive_sources(_library())}

        self.assertNotIn("registry", found)
        self.assertIn("roms", found)

    def test_what_the_user_said_wins(self) -> None:
        found = {one.key: one for one in
                 plan_for.derive_sources(_library(_game("Taxi")),
                                         {"tables": "/elsewhere"})}

        self.assertEqual(found["tables"].path, "/elsewhere")
        self.assertFalse(found["tables"].derived)

    def test_clearing_one_is_how_somebody_says_not_that(self) -> None:
        """An empty source means that kind is not imported. It has to be reachable, or
        a derived guess cannot be refused."""
        found = {one.key: one for one in
                 plan_for.derive_sources(_library(_game("Taxi")), {"tables": ""})}

        self.assertFalse(found["tables"].active)


class MatchTests(unittest.TestCase):
    HELD = [{"game_id": "g1", "folder_name": "Taxi (Williams 1988)",
             "name": "Taxi", "vps_id": "vps-taxi"}]

    def test_a_game_a_previous_run_made_is_recognised_by_its_folder(self) -> None:
        library = _library(_game("Taxi", display_name="Taxi (Williams 1988)"))

        found = plan_for.match_existing(library, self.HELD)

        self.assertTrue(found[0].existing)
        self.assertEqual(found[0].how, "folder")

    def test_one_renamed_since_is_still_recognised(self) -> None:
        """A rename should not turn one game into two."""
        library = _library(_game("Taxi", display_name="Taxi, the good one",
                                 vps_id="vps-taxi"))

        found = plan_for.match_existing(library, self.HELD)

        self.assertTrue(found[0].existing)
        self.assertEqual(found[0].how, "catalog id")

    def test_a_game_nothing_here_matches_is_new(self) -> None:
        found = plan_for.match_existing(_library(_game("Funhouse")), self.HELD)

        self.assertFalse(found[0].existing)


class ExpectedTests(unittest.TestCase):
    KINDS = ("playfield", "wheel")

    def _plan(self, library, held=(), **fields):
        """Built the way the extension builds it: the counts a report compares against
        are worked out while each game is in hand, so the plan needs to know what a
        media kind is."""
        fields.setdefault("source_id", "pinballx")
        fields.setdefault("kinds", self.KINDS)
        return plan_for.build(library, list(held), **fields)

    def test_it_counts_what_the_run_will_act_on(self) -> None:
        library = _library(
            _game("Taxi", table_file="/src/tables/Taxi.vpx", rom="taxi_l4",
                  media=(SourceMedia(source_kind="Wheel Images", path="/w/Taxi.png"),)),
            _game("Funhouse", table_file="/src/tables/Funhouse.vpx"))

        counts = plan_for.expected(self._plan(library))

        self.assertEqual(counts["games"], 2)
        self.assertEqual(counts["tables"], 2)
        self.assertEqual(counts["media"], 1)

    def test_several_builds_of_one_machine_are_one_game(self) -> None:
        """A real library held three of Kiss (Bally 1979) by different authors, and 34
        colliding folder names across 656 games. They are one game with three tables
        here, so the count has to say one - a plan promising three reports a shortfall
        for behaving correctly."""
        library = _library(
            _game("Kiss (Bally 1979)", table_file="/src/a.vpx"),
            _game("Kiss (Bally 1979)", table_file="/src/b.vpx"),
            _game("Kiss (Bally 1979)", table_file="/src/c.vpx"))

        counts = plan_for.expected(self._plan(library))

        self.assertEqual(counts["games"], 1)
        self.assertEqual(counts["tables"], 3)

    def test_only_the_first_build_brings_artwork(self) -> None:
        """The rest are the same table photographed twice, and the run does not place
        them - so counting them promises files that never arrive."""
        art = (SourceMedia(source_kind="Wheel Images", path="/w/Kiss.png"),)
        library = _library(
            _game("Kiss (Bally 1979)", table_file="/src/a.vpx", media=art),
            _game("Kiss (Bally 1979)", table_file="/src/b.vpx", media=art))

        counts = plan_for.expected(self._plan(library))

        self.assertEqual(counts["media"], 1)

    def test_two_games_with_the_same_key_are_both_counted(self) -> None:
        """A real source held two entries with byte-identical name attributes. Keyed on
        that, a dict silently keeps one, and the run then does more than the plan said."""
        library = _library(
            _game("Alpha", table_file="/src/a.vpx"),
            _game("Beta", table_file="/src/b.vpx"))
        same = [one for one in library.games]
        self.assertEqual(len({one.key for one in same}), 2)

        counts = plan_for.expected(self._plan(library))

        self.assertEqual(counts["tables"], 2)

    def test_a_quote_a_filesystem_cannot_keep_does_not_make_a_second_game(self) -> None:
        """A real library held `'300' (Gottlieb 1975)` where the source called it
        `"300" (Gottlieb 1975)`. The quote is the only difference, and a filesystem
        substitutes one for the other - matched literally, the machine ends up with the
        game twice."""
        library = _library(_game('"300"', display_name='"300" (Gottlieb 1975)',
                                 table_file="/src/tables/300.vpx"))
        held = [{"game_id": "g1", "folder_name": "'300' (Gottlieb 1975)",
                 "name": "300", "vps_id": ""}]

        made = self._plan(library, held)

        self.assertEqual(len(made.already), 1)
        self.assertEqual(made.new, [])

    def test_two_machines_whose_names_differ_stay_two(self) -> None:
        """The line this stops at: stripping punctuation generally would make Taxi and
        Taxi 2 one game, and merging two machines is worse than holding a duplicate."""
        library = _library(_game("Taxi", display_name="Taxi",
                                 table_file="/src/tables/Taxi.vpx"))
        held = [{"game_id": "g1", "folder_name": "Taxi 2", "name": "Taxi 2",
                 "vps_id": ""}]

        made = self._plan(library, held)

        self.assertEqual(made.already, [])
        self.assertEqual(len(made.new), 1)

    def test_a_source_nobody_set_contributes_nothing(self) -> None:
        """And says zero rather than being left out - an absent row reads as an
        oversight where a zero reads as a decision."""
        library = _library(_game("Taxi", rom="taxi_l4"))

        counts = plan_for.expected(
            self._plan(library, chosen={"media": ""}))

        self.assertEqual(counts["media"], 0)

    def test_a_kind_with_nowhere_to_go_is_not_offered(self) -> None:
        """Registry settings are read and not offered: nothing on this platform reads
        per-ROM VPinMAME values back, so anything written would be consumed by nothing."""
        offered = {key for key, *_rest in plan_for.SOURCES}

        self.assertNotIn("registry", offered)
        self.assertIn("registry", plan_for.NOT_YET)
        # And what does have somewhere to go is offered.
        self.assertIn("roms", offered)

    def test_games_already_here_are_not_counted_unless_they_are_being_filled(self) -> None:
        library = _library(_game("Taxi", display_name="Taxi (Williams 1988)",
                                 table_file="/src/tables/Taxi.vpx"))
        held = [{"game_id": "g1", "folder_name": "Taxi (Williams 1988)",
                 "name": "Taxi", "vps_id": ""}]

        skipping = plan_for.expected(self._plan(library, held))
        filling = plan_for.expected(self._plan(library, held, on_existing="fill"))

        self.assertEqual(skipping["games"], 0)
        self.assertEqual(filling["games"], 1)

    def test_leaving_them_alone_is_the_default(self) -> None:
        """Rewriting what somebody has curated since the last run is the worse
        mistake."""
        self.assertEqual(plan_for.build(_library(), []).on_existing, "skip")


class ComparisonTests(unittest.TestCase):
    def test_expected_and_actual_come_back_together(self) -> None:
        rows = {one["key"]: one for one in
                plan_for.against({"games": 8, "media": 20}, {"games": 7, "media": 20})}

        self.assertEqual(rows["games"]["short"], 1)
        self.assertEqual(rows["media"]["short"], 0)

    def test_every_row_is_reported_not_only_the_short_ones(self) -> None:
        """A line that appears only when something went wrong makes a clean import read
        as a report with things missing from it."""
        rows = plan_for.against({"games": 3}, {"games": 3})

        self.assertEqual(len(rows), len(plan_for.COUNTS))


if __name__ == "__main__":
    unittest.main()
