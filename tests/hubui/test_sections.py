import unittest
from urllib.parse import parse_qs

from hubui import deeplink, workbench


def _address(state: dict) -> dict[str, str]:
    return {name: values[0] for name, values in parse_qs(deeplink.query(state)).items()}


class ChosenSectionTests(unittest.TestCase):
    """Which section a panel is on, including none of them."""

    def test_a_fresh_client_lands_on_the_default(self) -> None:
        state: dict = {}

        self.assertEqual(workbench.chosen_section(state), workbench.DEFAULT_SECTION["game"])

    def test_a_section_the_subject_cannot_answer_falls_back(self) -> None:
        """Table details under a game is not a section to land on quietly."""
        state = {"section": "table_details"}

        self.assertEqual(workbench.chosen_section(state, "game"),
                         workbench.DEFAULT_SECTION["game"])

    def test_closed_stays_closed(self) -> None:
        state = {"section": workbench.COLLAPSED}

        self.assertEqual(workbench.chosen_section(state, "game"), workbench.COLLAPSED)

    def test_closed_survives_a_change_of_subject(self) -> None:
        """Otherwise the fallback reopens a section the user just shut."""
        state = {"section": workbench.COLLAPSED}
        workbench.chosen_section(state, "game")

        self.assertEqual(workbench.chosen_section(state, "table"), workbench.COLLAPSED)


class AddressTests(unittest.TestCase):
    """A place has to survive being written down and read back."""

    def _seed(self, params: dict[str, str]) -> dict:
        state: dict = {}
        deeplink.apply(state, params, views=["games"],
                       sections=[item.key for item in workbench.SECTIONS])
        return state

    def test_a_closed_panel_is_named_rather_than_left_out(self) -> None:
        address = _address({"view": "games", "game": "abc",
                            "section": workbench.COLLAPSED})

        self.assertEqual(address.get("section"), deeplink.NO_SECTION)

    def test_a_closed_panel_survives_the_round_trip(self) -> None:
        """The reason it is named: dropping it reopens a section on reload."""
        state = self._seed({"view": "games", "game": "abc",
                            "section": deeplink.NO_SECTION})

        self.assertEqual(workbench.chosen_section(state, "game"), workbench.COLLAPSED)

    def test_an_open_section_survives_the_round_trip(self) -> None:
        state = self._seed({"view": "games", "game": "abc", "section": "assets"})

        self.assertEqual(workbench.chosen_section(state, "game"), "assets")

    def test_a_section_nobody_has_falls_back_rather_than_erroring(self) -> None:
        """Addresses get hand-typed and go stale; neither is an error."""
        state = self._seed({"view": "games", "game": "abc", "section": "nonsense"})

        self.assertEqual(workbench.chosen_section(state, "game"),
                         workbench.DEFAULT_SECTION["game"])


class SectionTests(unittest.TestCase):
    """What the rows offer, and which of them brings its own work area."""

    def test_a_table_section_is_absent_under_a_game(self) -> None:
        keys = [item.key for item in workbench.sections_for("game")]

        self.assertNotIn("table_details", keys)
        self.assertIn("game_details", keys)

    def test_a_table_shows_the_game_first(self) -> None:
        """Parent before the thing it contains, which is the reading order."""
        keys = [item.key for item in workbench.sections_for("table")]

        self.assertLess(keys.index("game_details"), keys.index("table_details"))

    def test_only_a_section_with_two_regions_reserves_a_dock(self) -> None:
        """The room is half the panel; a section with nothing to put in it left a void.

        Two sections have something for it. Media puts the picked slot beside the map;
        a collection's Contents puts what the rule matched beside the rule, which is
        the whole reason a rule is edited here rather than in a dialog.
        """
        docked = {item.key for item in workbench.SECTIONS if item.dock}

        self.assertEqual(docked, {"media", "collection_contents"})

    def test_a_key_means_one_section_across_every_rail(self) -> None:
        """The rail is per subject; the key namespace is not.

        `section=` in an address is resolved before a subject is settled - `deeplink`
        is handed every rail's keys, not one rail's - so two sections sharing a key
        would make a link mean whichever one the reader happened to be on. Section 11
        called this out and the `subjects` field is what answered it: a section says
        which rails it appears in rather than a rail owning a namespace.

        Asserted rather than left to the docstring, because the pressure arrives with
        the next rail: Assets, the Tag Editor and the VPS section each want a short
        noun somebody has already used.
        """
        keys = [item.key for item in workbench.SECTIONS]

        self.assertEqual(sorted(keys), sorted(set(keys)))


class RailDefaultTests(unittest.TestCase):
    """Each rail lands where it declares, not on whatever is first."""

    def test_a_game_lands_on_the_game(self) -> None:
        self.assertEqual(workbench.chosen_section({}, "game"), "game_details")

    def test_a_table_lands_on_the_table(self) -> None:
        """Selecting a file on purpose should not open on the machine holding it."""
        self.assertEqual(workbench.chosen_section({}, "table"), "table_details")

    def test_every_rail_declares_a_section_it_actually_has(self) -> None:
        for subject, wanted in workbench.DEFAULT_SECTION.items():
            keys = {item.key for item in workbench.sections_for(subject)}
            self.assertIn(wanted, keys, f"{subject} lands nowhere")


class TablesBlockTests(unittest.TestCase):
    """A game's tables are a block inside Game Details, not a place of their own."""

    def test_no_rail_offers_tables_as_a_section(self) -> None:
        """Most games hold one, so "Tables (1)" was a rail entry you went to in order to
        read a single row - and the rail holds places. Section 7 already names the shape
        it takes instead: a sub-table, a related collection with its own columns."""
        for subject in ("game", "table"):
            with self.subTest(subject=subject):
                keys = {item.key for item in workbench.sections_for(subject)}
                self.assertNotIn("tables", keys)

    def test_a_game_still_lands_on_details_where_they_now_live(self) -> None:
        self.assertEqual(workbench.chosen_section({}, "game"), "game_details")


class VpsSectionTests(unittest.TestCase):
    """The match is a place on both subjects, and the id is not the label."""

    def test_both_rails_offer_it(self) -> None:
        """A game's match identifies the machine, which a table belongs to - so it is
        answerable whichever of the two is selected."""
        for subject in ("game", "table"):
            with self.subTest(subject=subject):
                keys = {item.key for item in workbench.sections_for(subject)}
                self.assertIn("vps", keys)

    def test_an_unmatched_game_says_so_in_the_rail(self) -> None:
        """Not matched is a state, not an empty section - and the rail is where it is
        seen without opening anything."""
        self.assertEqual(workbench._vps_label({"game": {}}), "VPS - not matched")
        self.assertEqual(workbench._vps_label({"game": {"vps_id": "abc"}}), "VPS")
