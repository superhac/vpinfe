"""The Overview's script fixes card, pressed as a click runs it."""

from __future__ import annotations

import asyncio
import unittest
from unittest import mock

from nicegui import ui

from common.i18n import t
from console import sections

OFFERED = {"reachable": True, "offered": ["Sample Game (Original 2024)"], "checked": 1,
           "already": 0}


async def _now(callback, *args, **kwargs):
    return callback(*args, **kwargs)


class FetchTests(unittest.TestCase):
    def test_how_it_went_is_said_after_the_page_is_left(self) -> None:
        library = mock.Mock()
        library.script_patches.return_value = OFFERED
        client = mock.Mock()
        with mock.patch("console.confirm.ask", mock.AsyncMock(return_value=True)), \
                mock.patch("console.api.ApiClient", return_value=client), \
                mock.patch.object(sections.run, "io_bound", new=_now), \
                mock.patch.object(sections.ui, "notify", wraps=ui.notify) as notify:
            with ui.column() as page, \
                    mock.patch.object(sections, "_metadata_row",
                                      wraps=sections._metadata_row) as row:
                sections.table_scripts(library)
            _label, fetch = row.call_args.args[3]
            [button] = [one for one in page.descendants()
                        if isinstance(one, ui.button) and one.text == t("word.fetch")]
            pressed = button.parent_slot
            del button
            client.apply_script_patches.side_effect = page.clear

            async def clicked() -> None:
                with pressed:
                    await fetch()

            asyncio.run(clicked())

        client.apply_script_patches.assert_called_once_with()

        notify.assert_called_once_with(t("console.sections.fetching_way"), type="positive")
