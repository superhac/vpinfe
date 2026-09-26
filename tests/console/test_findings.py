"""What is wrong with a game's tables, and the act each finding carries."""

from __future__ import annotations

import unittest
from typing import Any
from unittest.mock import AsyncMock, Mock, patch

from common.i18n import t
from console import game_tables, workbench


async def _now(callback: Any, *args: Any, **kwargs: Any) -> Any:
    return callback(*args, **kwargs)


def _table(table_id: str, **extra: Any) -> dict[str, Any]:
    return {"id": table_id, "filename": f"{table_id}.vpx", "version": "1.0",
            "authors": ["Someone"], "available": True, **extra}


def _context(*tables: dict[str, Any]) -> dict[str, Any]:
    library = Mock()
    library.vps_releases.return_value = [
        {"vps_file_id": "r-1", "version": "1.2", "url": "https://host.example/r-1"},
        {"vps_file_id": "r-2", "version": "2.0", "url": ""}]
    library.vps_entry.return_value = {"url": "https://vps.example/entry"}
    return {"library": library, "game": {"name": "Sample Game", "vps_id": "e-1",
                                         "folder": "/library/Sample Game"},
            "game_id": "g1", "tables": list(tables), "lens": "", "state": {},
            "rebuild": AsyncMock()}


class Findings(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        for patched in (
                patch("console.offload.run.io_bound", new=_now),
                patch.object(workbench.panel, "action",
                             new=lambda label, *_a, **_k: ("act", label)),
                patch.object(workbench.panel, "link_out",
                             new=lambda label, *, to, **_k: ("link", label, to)),
                patch.object(workbench, "_alert",
                             new=lambda line, act, said="": (line, act, said))):
            patched.start()
            self.addCleanup(patched.stop)

    async def _found(self, *tables: dict[str, Any]) -> list[tuple[Any, Any, str]]:
        entries = await workbench._findings(_context(*tables), tables)
        self.assertTrue(all(label == workbench.FULL for label, _ in entries))
        return [alert for _, alert in entries]

    async def test_a_rom_that_is_not_installed_is_added_from_its_alert(self) -> None:
        found = await self._found(_table("a", dependencies={
            "pinmame": {"effective": "hustler", "installed": False}}))

        self.assertEqual(found, [(t("console.workbench.rom_not_installed", value="hustler"),
                                  ("act", t("word.add")), "")])

    async def test_a_file_that_is_gone_is_forgotten_from_its_alert(self) -> None:
        found = await self._found(_table("a", available=False))

        self.assertEqual(found, [(t("console.workbench.file_not_disk"),
                                  ("act", t("word.forget")), "")])

    async def test_an_update_gives_both_versions_and_links_to_the_release(self) -> None:
        found = await self._found(_table("a", update_available=True, source={
            "vps_file_id": "r-1", "version": "1.2"}))

        self.assertEqual(found, [(
            t("console.workbench.newer_on_vps", theirs="1.2", ours="1.0"),
            ("link", t("console.workbench.get_version", version="1.2"),
             "https://host.example/r-1"), "")])

    async def test_a_release_with_no_page_links_to_its_entry(self) -> None:
        found = await self._found(_table("a", update_available=True, source={
            "vps_file_id": "r-2", "version": "2.0"}))

        self.assertEqual(found[0][1][2], "https://vps.example/entry")

    async def test_an_update_vps_could_not_be_read_for_says_so_in_place_of_the_link(
            self) -> None:
        for failing in ("vps_releases", "vps_entry"):
            with self.subTest(failing=failing):
                tables = (_table("a", update_available=True, source={
                    "vps_file_id": "r-9", "version": "3.0"}),)
                context = _context(*tables)
                getattr(context["library"], failing).side_effect = TimeoutError("timed out")

                with patch.object(workbench, "_state",
                                  new=lambda text, level, hint="": (text, level, hint)), \
                        self.assertLogs("vpinfe.console.workbench", level="WARNING"):
                    entries = await workbench._findings(context, tables)

                self.assertEqual([alert for _, alert in entries], [(
                    t("console.workbench.newer_on_vps", theirs="3.0", ours="1.0"),
                    (t("console.workbench.could_not_read_vps"), "unknown",
                     t("said.why.timed_out")), "")])

    async def test_a_fault_nothing_here_fixes_carries_no_act(self) -> None:
        found = await self._found(_table("a", dependencies={
            "flexdmd": {"detected": True, "installed": False}}))

        self.assertEqual(found, [(t("console.workbench.script_uses_flexdmd_not"), None, "")])

    async def test_a_choice_somebody_made_is_not_a_finding(self) -> None:
        self.assertEqual(await self._found(_table("a", hidden=True, default=False)), [])

    async def test_nothing_asks_the_catalog_without_an_update(self) -> None:
        context = _context(_table("a", available=False))

        await workbench._findings(context, context["tables"])

        context["library"].vps_releases.assert_not_called()

    async def test_each_says_its_table_where_the_game_has_several(self) -> None:
        tables = (_table("a", available=False), _table("b", version="2.0"))
        context = _context(*tables)

        entries = await workbench._findings(context, tables)

        self.assertEqual([said for _, (_, _, said) in entries],
                         [game_tables.name_among(tables[0], list(tables))])


class OncePerPanel(unittest.IsolatedAsyncioTestCase):
    """The game's section carries its tables' findings only while the game is the
    subject. Under Tables the table's own section leads with them."""

    async def _drawn(self, lens: str) -> list[Any]:
        context = _context(_table("a", available=False))
        context["lens"] = lens
        context["library"].vps_entry.return_value = {}
        context["library"].outside_links.return_value = []
        rows = Mock()
        with patch("console.offload.run.io_bound", new=_now), \
                patch.object(workbench, "_findings",
                             new=AsyncMock(return_value=[("finding", "alert")])), \
                patch.object(workbench, "_game_entries", return_value=[("fact", "value")]), \
                patch.object(workbench, "_rows", new=rows), \
                patch.object(workbench, "_tables_block"), \
                patch.object(workbench, "ui"):
            await workbench._game_block(context)
        return list(rows.call_args.args[1])

    async def test_a_game_leads_with_its_tables_findings(self) -> None:
        self.assertEqual(await self._drawn(lens=""), [("finding", "alert"), ("fact", "value")])

    async def test_under_a_table_the_game_does_not_repeat_them(self) -> None:
        self.assertEqual(await self._drawn(lens="a"), [("fact", "value")])


if __name__ == "__main__":
    unittest.main()
