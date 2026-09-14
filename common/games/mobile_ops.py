"""What a VPX Mobile device is carrying, and putting games on it or taking them off.

Asked of the device, never remembered. A phone is taken away, filled up and emptied by
hand, so anything this end recorded about it would be a claim rather than a fact.
"""

from __future__ import annotations

from typing import Any

from common import device_ops, service_errors
from common import jobs as job_registry
from common.games import game_repository, mobile_transfer
from common.i18n import t


def carried_by(device_id: str) -> dict[str, Any]:
    """It is a short question and the answer is only true at the moment it is given."""
    device = device_ops.mobile_or_refuse(device_id)
    try:
        found = mobile_transfer.carried(device.address, device.port)
    except mobile_transfer.DeviceUnreachableError as exc:
        raise service_errors.BlockedError(str(exc)) from exc
    return {"device_id": device_id, "count": len(found), "games": found}


def send(device_id: str, game_ids, everything: bool = False) -> job_registry.Job:
    """A job, not an action.

    The lifecycle vocabulary is for things that happen at once - stop the table, reboot.
    A multi-file transfer with per-file progress over a phone's wifi is slow work, and
    slow work has a shape here already.
    """
    device = device_ops.mobile_or_refuse(device_id)
    folders = [_folder_or_refuse(game_id) for game_id in game_ids]
    if not folders:
        raise service_errors.RefusedError(t("error.devices.name_least_one_game"))

    def work(job) -> None:
        reporter = job.reporter()

        # The whole transfer's progress, not one game's: what a person watching wants is
        # how far through the twelve they are. `at` comes in by call so it is this
        # folder's position and not wherever the loop has reached.
        def reporting(at: int) -> mobile_transfer.Progress:
            def sent(done: int, total: int, said: str) -> None:
                reporter.progress(at * 100 + int(100 * done / max(total, 1)),
                                  len(folders) * 100, said)
            return sent

        for index, folder in enumerate(folders):
            reporter.progress(index, len(folders), f"Sending {folder.name}")
            mobile_transfer.send(folder, device.address, device.port,
                                 everything=everything, on_progress=reporting(index))
        reporter.progress(len(folders), len(folders),
                          f"Sent {len(folders)} to "
                          f"{device.display_name or device_id}")

    try:
        return job_registry.submit(job_registry.KIND_DEVICE_SEND, work)
    except job_registry.JobBusyError as exc:
        raise service_errors.BlockedError(str(exc)) from exc


def remove(device_id: str, name: str) -> None:
    device = device_ops.mobile_or_refuse(device_id)
    try:
        mobile_transfer.remove(name, device.address, device.port)
    except mobile_transfer.DeviceUnreachableError as exc:
        raise service_errors.BlockedError(str(exc)) from exc


def _folder_or_refuse(game_id: str):
    folder = game_repository.game_folder(game_id)
    if folder is None:
        raise service_errors.NotFoundError(
            t("error.games.no_game_id", game_id=(game_id)))
    return folder
