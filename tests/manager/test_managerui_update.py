"""What the Manager UI's header says when installing an update fails."""

from __future__ import annotations

import errno
import unittest
from unittest import mock

import requests

from common.failures import why
from common.i18n import t
from common.online.app_updater import UpdateError
from managerui import managerui


async def _now(fn, *args):
    return fn(*args)


class WhatAFailedUpdateSays(unittest.IsolatedAsyncioTestCase):
    async def _notified(self, failure: Exception) -> mock.Mock:
        with mock.patch.object(managerui, "ui") as ui, \
                mock.patch.object(managerui, "prepare_update", side_effect=failure), \
                mock.patch("nicegui.run.io_bound", new=_now):
            await managerui._run_update_install(mock.MagicMock())
        return ui.notify

    async def test_a_folder_it_cannot_write_is_named_in_words(self) -> None:
        denied = PermissionError(errno.EACCES, "Permission denied", "/opt/vpinfe/update")

        notify = await self._notified(denied)

        notify.assert_called_with("Update failed", caption=why(denied), type="negative")
        self.assertNotIn("Errno", notify.call_args.kwargs["caption"])

    async def test_a_release_host_it_cannot_reach_is_named_in_words(self) -> None:
        unreached = requests.ConnectionError("HTTPSConnectionPool(host='github.com')")

        notify = await self._notified(unreached)

        notify.assert_called_with("Update failed", caption=t("said.why.unreachable"),
                                  type="negative")

    async def test_its_own_refusal_is_shown_as_it_said_it(self) -> None:
        said = t("error.instance.already_latest")

        notify = await self._notified(UpdateError(said))

        notify.assert_called_with("Update failed", caption=said, type="negative")

    async def test_a_failure_leaves_it_free_to_try_again(self) -> None:
        await self._notified(UpdateError(t("error.instance.already_latest")))

        self.assertFalse(managerui._update_action_state["busy"])


if __name__ == "__main__":
    unittest.main()
