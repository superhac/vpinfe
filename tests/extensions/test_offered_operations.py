"""What core lets an extension do to the library.

An extension used to reach eight things where an HTTP client reached twenty-five, which
is backwards: games are the thing extensions are mostly for. Core now hands the host its
own route functions, so the two cannot answer differently.

Called directly rather than over the wire - they are plain functions, and the scope gate
lives in each route's dependencies, which only fires for a real request. So the gate is
re-applied here, against the manifest, which is what makes declaring a scope mean
something.
"""

from __future__ import annotations

import unittest

import httpapi
from common.extensions.contract import ContractError
from common.extensions.games import ExtensionGames, offered, withdraw_all


class OfferedTests(unittest.TestCase):
    def setUp(self) -> None:
        withdraw_all()
        self.addCleanup(withdraw_all)
        httpapi.create_api_app()

    def test_building_the_api_offers_the_library_to_extensions(self) -> None:
        """Wired where the app is built, so a test app offers what the real one does."""
        self.assertIn("list_games", offered())
        self.assertIn("rate_table", offered())

    def test_an_extension_reaches_what_its_manifest_declared(self) -> None:
        reader = ExtensionGames("reader", ("games:read",), None)

        self.assertIn("list_games", reader.reaches())
        self.assertNotIn("rate_table", reader.reaches())

    def test_writing_needs_the_write_scope(self) -> None:
        reader = ExtensionGames("reader", ("games:read",), None)

        with self.assertRaises(ContractError):
            reader.rate_table("g1", "t1", 5)

    def test_something_core_never_offered_is_not_reachable(self) -> None:
        """And it says what is on offer, because the alternative is an author guessing
        at names against an AttributeError."""
        anyone = ExtensionGames("anyone", ("games:read", "games:write"), None)

        with self.assertRaises(AttributeError) as caught:
            anyone.delete_the_whole_library("please")
        self.assertIn("list_games", str(caught.exception))

    def test_launching_is_not_granted_by_being_allowed_to_write(self) -> None:
        """It takes over the cabinet rather than editing a record, and the scope
        vocabulary said so before extensions existed. An extension that starts a game
        asks for that by name, and whoever installs it reads it by name."""
        writer = ExtensionGames("writer", ("games:read", "games:write"), None)

        self.assertNotIn("launch_game", writer.reaches())
        with self.assertRaises(ContractError):
            writer.launch_game("g1")

    def test_an_extension_that_asked_to_launch_can(self) -> None:
        launcher = ExtensionGames("scheduler", ("launch:invoke",), None)

        self.assertIn("launch_game", launcher.reaches())

    def test_launching_alone_grants_nothing_else(self) -> None:
        """The three are separate on purpose: a scheduler that can start a table should
        not thereby be able to rewrite one."""
        launcher = ExtensionGames("scheduler", ("launch:invoke",), None)

        self.assertEqual(launcher.reaches(), ("launch_game",))

    def test_the_named_methods_still_win(self) -> None:
        """`kinds` is wrapped for a reason and is not one of the offered names; the
        lookup must not shadow it."""
        anyone = ExtensionGames("anyone", ("games:read",), None)

        self.assertTrue(callable(anyone.kinds))
        self.assertNotIn("kinds", offered())


if __name__ == "__main__":
    unittest.main()
