"""The guided task the importer offers, as core sees it.

Core draws the wizard from what the extension declares, so what is pinned here is the
declaration and the three calls behind it - not the drawing, which is core's and is the
same for every task.
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

REPO = Path(__file__).resolve().parents[2]
FIXTURE = REPO / "tests" / "fixtures" / "pinballx"
BASE = "/ext/library_importer"


class WizardCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.store = store.ExtensionStore(self.root / "extensions.json")
        self.registry = host.Registry(self.store)
        extensions.set_registry(self.registry)
        self.addCleanup(extensions.set_registry, host.Registry())
        self.addCleanup(self.registry.clear)
        self.record = self.registry.load(host.BUNDLED_DIR / "library_importer")
        self.assertEqual(self.record.state, host.LOADED, self.record.reason)
        self.client = TestClient(httpapi.create_api_app(), raise_server_exceptions=False)

    def _step(self, path, leaving="source", **values) -> dict:
        """The one step after the one named, with whatever has been answered so far."""
        return self.client.post(
            f"{BASE}/wizard/check",
            json={"values": {"path": str(path), **values}, "step": leaving}).json()

    def _check(self, path, **values) -> dict:
        """Walk to the summary the way somebody pressing Next does.

        Walked rather than asked for, because the summary is what the earlier steps add
        up to: a test that jumped to it would pass over the thing being described.
        """
        found = self._step(path, **values)
        seen = {}
        while "summary" not in found and found.get("step"):
            for field in found.get("fields") or []:
                seen.setdefault(field["key"], field.get("value"))
            seen.pop("path", None)
            found = self._step(path, leaving=found["step"], **{**seen, **values})
        return found


class DeclarationTests(WizardCase):
    def test_the_action_is_listed_with_the_extension(self) -> None:
        found = self.client.get("/extensions").json()["extensions"][0]

        action = found["actions"][0]
        self.assertEqual(action["key"], "import")
        self.assertEqual(action["base"], "/wizard")
        self.assertTrue(action["label"])

    def test_an_action_declares_no_mode(self) -> None:
        """How many steps it has is read off what it answers - the fields it asks
        for and the confirm it names. A declared mode would be a second statement
        of the same thing, and the two come apart."""
        found = self.client.get("/extensions").json()["extensions"][0]
        action = found["actions"][0]

        self.assertEqual(sorted(action), ["base", "description", "key", "label"])

    def test_an_extension_that_is_not_running_offers_nothing(self) -> None:
        """A button that refuses is worse than no button."""
        with self.assertLogs("vpinfe.common.extensions", "ERROR"):
            self.registry.disable("library_importer", "asked to")

        found = self.client.get("/extensions").json()["extensions"][0]

        self.assertEqual(found["actions"], [])

    def test_offering_one_without_the_capability_is_refused(self) -> None:
        from common.extensions.context import ExtensionUI

        with self.assertRaises(ContractError):
            ExtensionUI("quiet", allowed=False).action("go", "Go", "/x")


class FormTests(WizardCase):
    def test_the_first_step_asks_where_the_library_is(self) -> None:
        found = self.client.get(f"{BASE}/wizard").json()

        self.assertTrue(found["title"])
        self.assertEqual([one["key"] for one in found["fields"]],
                         ["source_type", "path"])
        self.assertEqual(
            next(one["type"] for one in found["fields"] if one["key"] == "path"),
            "path")


class CheckTests(WizardCase):
    def test_it_says_what_would_come_across(self) -> None:
        """Counted before it runs, so the report afterwards has something to be
        measured against."""
        found = self._check(FIXTURE)

        self.assertTrue(found["ready"])
        summary = dict(one for one in found["summary"] if len(one) == 2)
        self.assertEqual(summary["Games"], "4")
        self.assertEqual(summary["Reads as"], "PinballX or PinballY")

    def test_a_kind_with_no_source_says_it_is_not_coming(self) -> None:
        """"No artwork" should be a choice somebody can see they made, not a silence
        they notice afterwards."""
        found = self._check(FIXTURE, media="")
        summary = dict(one for one in found["summary"] if len(one) == 2)

        self.assertEqual(summary["No artwork"], "not being imported")

    def test_every_kind_of_source_is_offered_and_can_be_cleared(self) -> None:
        """Derived where it can be, overridable always, and empty means not imported."""
        found = self._step(FIXTURE)
        fields = {one["key"]: one for one in found["fields"]}

        for key in ("tables", "media"):
            self.assertIn(key, fields)
            self.assertEqual(fields[key]["type"], "path")

    def test_the_notes_travel_with_the_counts(self) -> None:
        """A summary that said four games and stayed quiet about their tables being on a
        machine that is not here would describe an import that will not happen."""
        found = self._check(FIXTURE)

        self.assertTrue(any("not reachable from here" in note
                            for note in found["notes"]))

    def test_the_confirm_says_what_it_will_do(self) -> None:
        self.assertEqual(self._check(FIXTURE)["confirm"], "Bring in 4 games")

    def test_several_systems_are_a_choice_and_one_is_not(self) -> None:
        found = self._step(FIXTURE)
        fields = {one["key"]: one for one in found["fields"]}

        self.assertIn("systems", fields)
        self.assertEqual(len(fields["systems"]["choices"]), 2)

    def test_a_folder_holding_nothing_readable_is_asked_again(self) -> None:
        """Asked again rather than carried forward. Somebody who typed the wrong folder
        wants that question back, not a summary of nothing four steps later."""
        empty = self.root / "empty"
        empty.mkdir()

        found = self._step(empty)

        self.assertEqual(found["step"], "source")
        self.assertTrue(found["notes"])

    def test_choosing_the_folder_here_is_what_lets_core_read_it(self) -> None:
        """It is set at the check rather than at the end, because there is nothing to
        summarize until core may read the folder at all."""
        from httpapi import filesystem

        self._check(FIXTURE)

        self.assertEqual(filesystem.within_roots(str(FIXTURE / "Config")).name, "Config")


if __name__ == "__main__":
    unittest.main()


class StepOrderTests(WizardCase):
    """Which question comes next, and why it does not depend on how somebody got here."""

    def test_the_source_step_is_followed_by_the_source_map(self) -> None:
        self.assertEqual(self._step(FIXTURE)["step"], "sources")

    def test_going_back_and_forward_asks_the_same_thing_again(self) -> None:
        """The step being left decides what comes next, not what has been answered.

        Answered values decide the *content* of a step; if they decided the order too,
        pressing Back and then Next would skip the step just returned to - which is the
        one thing somebody pressing Back is trying to reach.
        """
        first = self._step(FIXTURE)
        again = self._step(FIXTURE, leaving="source",
                           **{one["key"]: one.get("value")
                              for one in first["fields"] if one["key"] != "path"})

        self.assertEqual(again["step"], first["step"])

    def test_existing_games_are_only_asked_about_when_there_are_some(self) -> None:
        """A library with nothing matching gets one step fewer, not a step saying zero."""
        found = self._step(FIXTURE, leaving="sources", tables="", media="")

        self.assertEqual(found["step"], "summary")

    def test_the_summary_is_the_last_step(self) -> None:
        found = self._check(FIXTURE)

        self.assertEqual(found["step"], "summary")
        self.assertIn("summary", found)
        self.assertNotIn("fields", found)


class SummaryShapeTests(WizardCase):
    def test_a_row_of_one_is_a_heading(self) -> None:
        """Which is how the counts get separated from the settings above them without
        the extension deciding anything about how either is drawn."""
        found = self._check(FIXTURE)

        headings = [one[0] for one in found["summary"] if len(one) == 1]
        self.assertEqual(headings, ["What comes across"])

    def test_the_counts_come_after_the_heading(self) -> None:
        found = self._check(FIXTURE)
        at = next(i for i, one in enumerate(found["summary"]) if len(one) == 1)

        after = [one[0] for one in found["summary"][at + 1:]]
        self.assertEqual(after, ["Games", "Game files", "Artwork files",
                                 "Backglasses and settings"])
