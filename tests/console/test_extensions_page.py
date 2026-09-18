"""What the Extensions page says about an extension that is not running.

The words are the whole of this page: the list itself is one card per row. What is worth
pinning is that every state the host can reach has a word, and that the word for a switch
somebody set is not the word for something that broke.
"""

from __future__ import annotations

import unittest
from pathlib import Path

from common.extensions import host
from console import sections


class StateWordTests(unittest.TestCase):
    def test_every_state_that_is_not_running_has_a_word(self) -> None:
        """A state with no word draws no chip, so a stopped extension would look fine."""
        states = {value for name, value in vars(host).items()
                  if name.isupper() and isinstance(value, str)
                  and value in {"loaded", "failed", "disabled", "off"}}

        self.assertEqual(states - {host.LOADED}, set(sections.STATE_WORDS))

    def test_running_draws_no_chip(self) -> None:
        """A badge on every row says nothing."""
        self.assertNotIn(host.LOADED, sections.STATE_WORDS)

    def test_a_switch_somebody_set_reads_differently_from_a_fault(self) -> None:
        self.assertNotEqual(sections.STATE_WORDS[host.OFF],
                            sections.STATE_WORDS[host.DISABLED])

    def test_only_a_state_that_costs_something_wears_the_warn_tone(self) -> None:
        self.assertEqual(sections.QUIET_STATES, {host.OFF})


class FrontDoorTests(unittest.TestCase):
    """What a person browsing what is installed is shown.

    Not what an extension may reach. A scope is what somebody agrees to when installing
    something; on a list of what is already installed it is jargon in front of everybody
    who is not auditing, and it belongs on the extension's own page.
    """

    def test_the_card_does_not_name_scopes_or_capabilities(self) -> None:
        source = Path(sections.__file__).read_text(encoding="utf-8")
        card = source[source.index("def _extension_card"):source.index("def _actions")]

        self.assertNotIn("scopes", card)
        self.assertNotIn("capabilities", card)

    def test_an_action_is_drawn_from_its_label_alone(self) -> None:
        """The description is already the line under the extension's name."""
        source = Path(sections.__file__).read_text(encoding="utf-8")
        actions = source[source.index("def _actions"):]

        self.assertIn("tooltip", actions)


if __name__ == "__main__":
    unittest.main()
