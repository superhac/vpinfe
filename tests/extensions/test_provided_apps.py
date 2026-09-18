"""An extension can add a way to play a table.

VPinFE plays Visual Pinball, and through the generic app anything a person can point at a
binary. What it could not do is treat another format as first-class - claim its suffixes,
so a library of them is worth importing rather than read and dropped.

The extension describes the app in plain data and hands over one callable. It cannot
import the app contract - its one door is `common.extensions.contract`, which is what
makes the import boundary checkable - so nothing here asks it to.
"""

from __future__ import annotations

import pathlib
import unittest

from common import apps
from common.extensions import provided_apps
from common.extensions.context import ExtensionApps
from common.extensions.contract import ContractError

SCOPES = (provided_apps.APPS_PROVIDE,)
FUTURE = {"id": "fp", "name": "Future Pinball", "suffixes": ("fpt",)}


class ProvideTests(unittest.TestCase):
    def setUp(self) -> None:
        apps.withdraw_all()
        self.addCleanup(apps.withdraw_all)
        self.apps = ExtensionApps("future_pinball", SCOPES)

    def test_a_provided_app_joins_the_ones_this_build_ships(self) -> None:
        self.apps.provide(**FUTURE)

        self.assertIn("fp", [one.id for one in apps.all_apps()])

    def test_it_claims_its_own_files(self) -> None:
        """Which is the point: a file nothing claimed had nothing that could play it."""
        self.assertIsNone(apps.app_for("Big Bang Bar.fpt"))

        self.apps.provide(**FUTURE)

        self.assertEqual(apps.app_for("Big Bang Bar.fpt").id, "fp")

    def test_a_dot_is_added_to_a_suffix_that_came_without_one(self) -> None:
        self.apps.provide(**FUTURE)

        self.assertEqual(apps.get("fp").claim.suffixes, (".fpt",))

    def test_it_cannot_take_a_suffix_from_the_app_that_ships_with_this(self) -> None:
        """Built-ins are offered first and `app_for` takes the first that claims, so a
        contributed app cannot capture .vpx by loading before somebody looks."""
        self.apps.provide(id="impostor", name="Impostor", suffixes=(".vpx",))

        self.assertEqual(apps.app_for("Table.vpx").id, "vpx")

    def test_an_id_this_build_already_uses_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            self.apps.provide(id="vpx", name="Not really", suffixes=(".x",))

    def test_the_same_id_twice_is_refused(self) -> None:
        """Ids are stored in a table's record, so two apps under one id makes what is
        stored ambiguous long after the run that wrote it."""
        self.apps.provide(**FUTURE)

        with self.assertRaises(ValueError):
            self.apps.provide(**FUTURE)

    def test_an_app_that_plays_nothing_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            self.apps.provide(id="nothing", name="Nothing")

    def test_every_launcher_gets_the_program_it_runs(self) -> None:
        """Filled in when the extension forgot, because a launcher with no binary field
        is one nobody can point at anything."""
        self.apps.provide(**FUTURE)

        self.assertIn("bin_path", [one.key for one in apps.get("fp").fields])

    def test_an_app_declares_what_travels_with_its_tables(self) -> None:
        """Its own list. A Future Pinball table's companions are not a VPX table's, and
        a generic list would be one program's habits taught to everything."""
        from common.games.game_service import companions_beside

        self.apps.provide(**FUTURE, companions=("fpl", ".bam"))

        self.assertEqual(apps.get("fp").claim.companions, (".fpl", ".bam"))
        self.assertEqual(companions_beside(pathlib.Path("/nowhere/x.fpt")), [])

    def test_providing_needs_the_scope(self) -> None:
        with self.assertRaises(ContractError):
            ExtensionApps("quiet", ()).provide(**FUTURE)

    def test_what_it_added_goes_when_it_does(self) -> None:
        """A disabled extension must not leave a suffix claimed by something that is no
        longer here."""
        self.apps.provide(**FUTURE)

        self.apps.withdraw()

        self.assertIsNone(apps.app_for("Big Bang Bar.fpt"))
        self.assertEqual(self.apps.provided(), ())


class CommandTests(unittest.TestCase):
    def setUp(self) -> None:
        apps.withdraw_all()
        self.addCleanup(apps.withdraw_all)

    def _entry(self, **fields):
        from common.apps.contract import Entry

        return Entry(**fields)

    def test_the_extension_says_how_to_run_it(self) -> None:
        seen = {}

        def command(entry, settings):
            seen.update(entry)
            return ["/opt/fp", "--play", entry["table"]]

        ExtensionApps("fp", SCOPES).provide(**FUTURE, command=command)
        found = apps.get("fp").launch.command(
            self._entry(table="/games/BBB.fpt"), {})

        self.assertEqual(found, ["/opt/fp", "--play", "/games/BBB.fpt"])
        self.assertEqual(seen["table"], "/games/BBB.fpt")

    def test_answering_with_nothing_runs_the_launcher_as_configured(self) -> None:
        """So an extension that only wants to claim a format need not reimplement
        argument handling it has no opinion about."""
        ExtensionApps("fp", SCOPES).provide(**FUTURE, command=lambda entry, settings: None)

        found = apps.get("fp").launch.command(
            self._entry(table="/games/BBB.fpt"), {"bin_path": "/opt/fp", "args": "-open"})

        self.assertEqual(found, ["/opt/fp", "-open", "/games/BBB.fpt"])

    def test_a_string_is_refused_rather_than_split(self) -> None:
        """Splitting a command someone built as a string is how a path with a space in
        it becomes a crash or an injection, and only the extension knows where its own
        arguments end."""
        ExtensionApps("fp", SCOPES).provide(
            **FUTURE, command=lambda entry, settings: "/opt/fp --play thing")

        with self.assertRaises(TypeError):
            apps.get("fp").launch.command(self._entry(table="/x.fpt"), {})


if __name__ == "__main__":
    unittest.main()
