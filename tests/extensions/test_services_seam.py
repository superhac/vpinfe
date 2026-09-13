"""Core keeps the method; an extension answers it.

The other direction from `contributions`. That one answers "what does an extension know
about this game"; this answers questions with no game in them - who is signed in, sync
now.

The case that matters is the empty one. A theme has been able to ask who is playing
since long before extensions existed, and published themes still call those methods, so
they cannot move or be removed. With nothing answering - disabled, failed to load, never
installed - core has to say exactly what it said before there was an extension.
"""

from __future__ import annotations

import unittest

from common.extensions import services


class SeamTests(unittest.TestCase):
    def setUp(self) -> None:
        services.forget_all()
        self.addCleanup(services.forget_all)

    def test_an_extension_answers_and_core_asks_by_name(self) -> None:
        services.provide("vpinplay", "guest.state", lambda: {"active": True})

        self.assertEqual(services.ask("guest.state"), {"active": True})

    def test_nothing_answering_is_none_and_not_an_error(self) -> None:
        """The ordinary state, not a failure: every caller is a surface that has to keep
        working without an extension."""
        self.assertIsNone(services.ask("guest.state"))

    def test_a_provider_that_throws_answers_none(self) -> None:
        """A broken extension must not take a theme method down with it."""
        def boom():
            raise RuntimeError("no")

        services.provide("vpinplay", "guest.state", boom)

        self.assertIsNone(services.ask("guest.state"))

    def test_two_extensions_cannot_answer_the_same_thing(self) -> None:
        """Which answer a theme got would otherwise depend on load order."""
        services.provide("vpinplay", "guest.state", lambda: 1)

        with self.assertRaises(ValueError):
            services.provide("somebody_else", "guest.state", lambda: 2)

    def test_the_same_extension_may_replace_its_own(self) -> None:
        """A reload is not a conflict."""
        services.provide("vpinplay", "guest.state", lambda: 1)
        services.provide("vpinplay", "guest.state", lambda: 2)

        self.assertEqual(services.ask("guest.state"), 2)

    def test_what_it_answered_goes_when_it_unloads(self) -> None:
        services.provide("vpinplay", "guest.state", lambda: 1)

        services.forget("vpinplay")

        self.assertIsNone(services.ask("guest.state"))
        self.assertEqual(services.provided(), ())


class ThemeSurfaceTests(unittest.TestCase):
    """What a theme is told when nothing answers."""

    def setUp(self) -> None:
        services.forget_all()
        self.addCleanup(services.forget_all)

    def test_a_theme_is_told_nobody_is_signed_in(self) -> None:
        """Not an error and not an empty dict: the shape core answered with before any
        of this moved, so a cabinet with the extension off reads as one with no guest."""
        from frontend.api import _NOBODY_SIGNED_IN

        self.assertEqual(_NOBODY_SIGNED_IN["active"], False)
        self.assertIsNone(_NOBODY_SIGNED_IN["profile"])
        self.assertEqual(_NOBODY_SIGNED_IN["profiles"], [])


if __name__ == "__main__":
    unittest.main()
