import unittest
from urllib.parse import parse_qs

from hubui import deeplink, workbench


def _address(state: dict) -> dict[str, str]:
    return {name: values[0] for name, values in parse_qs(deeplink.query(state)).items()}


class ChosenSectionTests(unittest.TestCase):
    """Which section a panel is on, including none of them."""

    def test_a_fresh_client_lands_on_the_default(self) -> None:
        state: dict = {}

        self.assertEqual(workbench.chosen_section(state), workbench.DEFAULT_SECTION)

    def test_a_section_the_subject_cannot_answer_falls_back(self) -> None:
        """Table details under a game is not a section to land on quietly."""
        state = {"section": "table_details"}

        self.assertEqual(workbench.chosen_section(state, "game"),
                         workbench.DEFAULT_SECTION)

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
        state = self._seed({"view": "games", "game": "abc", "section": "tables"})

        self.assertEqual(workbench.chosen_section(state, "game"), "tables")

    def test_a_section_nobody_has_falls_back_rather_than_erroring(self) -> None:
        """Addresses get hand-typed and go stale; neither is an error."""
        state = self._seed({"view": "games", "game": "abc", "section": "nonsense"})

        self.assertEqual(workbench.chosen_section(state, "game"),
                         workbench.DEFAULT_SECTION)


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

    def test_only_the_section_with_something_to_pick_reserves_a_dock(self) -> None:
        """The room is half the panel; a section with nothing to put in it left a void."""
        docked = {item.key for item in workbench.SECTIONS if item.dock}

        self.assertEqual(docked, {"media"})
