import unittest
from urllib.parse import parse_qs

from common.i18n import t
from console import deeplink, workbench


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


class CollectionAddressTests(unittest.TestCase):
    def test_a_collection_survives_the_round_trip(self) -> None:
        state: dict = {}
        deeplink.apply(state, {"view": "collections", "collection": "Friday Night"},
                       views=["games", "collections"], sections=[])

        self.assertEqual(_address(state),
                         {"view": "collections", "collection": "Friday Night"})

    def test_the_games_grid_carries_the_collection_it_is_narrowed_to(self) -> None:
        self.assertEqual({"view": "games", "collection": "Friday Night"},
                         _address({"view": "games", "collection": "Friday Night"}))

    def test_a_collection_is_noise_anywhere_else(self) -> None:
        self.assertNotIn("collection",
                         _address({"view": "tables", "collection": "Friday Night"}))

    def test_leaving_a_page_drops_the_collection_it_had_open(self) -> None:
        from console import page

        state = {"view": "collections", "collection": "Friday Night"}
        page.leave_for(state, "games")

        self.assertEqual({"view": "games"}, _address(state))


class SectionTests(unittest.TestCase):
    """What the rows offer, and which of them brings its own work area."""

    def test_both_rails_offer_collections(self) -> None:
        for subject in ("game", "table"):
            with self.subTest(subject=subject):
                self.assertIn("collections",
                              {item.key for item in workbench.sections_for(subject)})

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
        Media puts the picked slot beside the map."""
        docked = {item.key for item in workbench.SECTIONS if item.dock}

        self.assertEqual(docked, {"media"})

    def test_a_key_means_one_section_across_every_rail(self) -> None:
        """The rail is per subject; the key namespace is not.

        `section=` in an address is resolved before a subject is settled - `deeplink`
        is handed every rail's keys, not one rail's - so two sections sharing a key
        would make a link mean whichever one the reader happened to be on. The
        `subjects` field is what answers it: a section says which rails it appears in
        rather than a rail owning a namespace.

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
        """Most games hold one, so "Tables (1)" would be a rail entry you went to in
        order to read a single row - and the rail holds places. It takes the other shape
        instead: a sub-table, a related collection with its own columns."""
        for subject in ("game", "table"):
            with self.subTest(subject=subject):
                keys = {item.key for item in workbench.sections_for(subject)}
                self.assertNotIn("tables", keys)

    def test_a_game_still_lands_on_details_where_they_now_live(self) -> None:
        self.assertEqual(workbench.chosen_section({}, "game"), "game_details")


class MatchTests(unittest.TestCase):
    """The match heads Game details, on both subjects."""

    def test_both_rails_offer_it(self) -> None:
        """A game's match identifies the machine, which a table belongs to - so it is
        answerable whichever of the two is selected."""
        for subject in ("game", "table"):
            with self.subTest(subject=subject):
                keys = {item.key for item in workbench.sections_for(subject)}
                self.assertIn("game_details", keys)
                self.assertNotIn("vps", keys)

    def test_an_unmatched_game_says_so_in_the_rail(self) -> None:
        self.assertEqual(workbench._game_label({"game": {}}),
                         t("console.workbench.game_details_not_matched"))
        self.assertEqual(workbench._game_label({"game": {"vps_id": "abc"}}),
                         t("console.workbench.game_details"))

    def test_a_game_declared_in_no_catalog_is_not_flagged(self) -> None:
        declared = {"game": {"overrides": {"alt_vps_id": None}}}
        self.assertEqual(workbench._game_label(declared),
                         t("console.workbench.game_details"))
