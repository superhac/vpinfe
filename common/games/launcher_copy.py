"""Copying a launcher to another machine.

A copy, not shared storage. Launchers stay per install because what one names is a
program on one machine, and sharing is what you do when several cabinets are built the
same way.

**The copy keeps the id.** That is the whole trick: ids come from the generator every id
in this project uses, so they do not collide across machines, and preserving one means
the same launcher exists on every cabinet under one name and a mapping means the same
thing everywhere. Renumbering on the way in would break every mapping that travelled
with it.

**One way, with no ongoing link.** Edit a cabinet's launcher afterwards and it diverges,
and nothing here reconciles that. Real sync means conflict resolution, change tracking
and a rule about which side wins; growing that accidentally is worse than designing it.

A path that does not apply to the target announces itself: that machine's own path check
marks the program missing and its trouble badge lights, which is the machinery that
already exists for a launcher pointing at nothing.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger("vpinfe.common.games.launcher_copy")


class LocalWrites:
    """The two launcher writes against this install's own store.

    Here rather than on `device_client.LocalDevice` because that module is
    infrastructure and may not reach into a domain package - and a launcher is one. It
    gives `copy_to` the same two methods a remote device answers, so copying to the
    machine you are standing at is not a special case.
    """

    def put_launcher(self, launcher_id: str, body: dict[str, Any]) -> dict[str, Any]:
        from common.games import launchers

        made = launchers.Launcher(
            launcher_id=launcher_id,
            app=str(body.get("app") or ""),
            display_name=str(body.get("display_name") or ""),
            enabled=bool(body.get("enabled", True)),
            owns_ini=bool(body.get("owns_ini", False)),
            settings=dict(body.get("settings") or {}))
        return launchers.get_launcher_store().put(made).as_dict()

    def put_launcher_mapping(self, table_id: str, launcher_id: str) -> dict[str, Any]:
        from common.games import launchers

        launchers.get_launcher_store().assign(table_id, launcher_id)
        return {"table_id": table_id, "launcher_id": launcher_id}


@dataclass(frozen=True)
class Outcome:
    """What happened for one device. `error` is empty where it worked.

    Reported per device rather than as one verdict: copying to three cabinets and having
    the second one asleep is a partial success, and a caller that says only "failed"
    would send somebody to check all three.
    """

    device_id: str
    name: str
    launchers: int = 0
    mappings: int = 0
    error: str = ""

    @property
    def ok(self) -> bool:
        return not self.error


def copy_to(devices, launchers_to_send, mappings=None, *, client_for) -> list[Outcome]:
    """Send launchers, and optionally the tables that name them, to each device.

    `client_for` builds the client for a device, so this does not decide how a machine is
    reached - the same call works for the install you are standing at and for one across
    the network.

    Mappings are filtered to the launchers actually being sent. A mapping naming a
    launcher the target does not have is dropped on read at the far end anyway, so
    sending one is a write that quietly does nothing.
    """
    sending = list(launchers_to_send)
    ids = {one["launcher_id"] for one in sending}
    wanted = {table: to for table, to in (mappings or {}).items() if to in ids}

    found = []
    for device in devices:
        found.append(_send(device, sending, wanted, client_for))
    return found


def _send(device: dict[str, Any], sending, mappings, client_for) -> Outcome:
    name = str(device.get("display_name") or device.get("device_id") or "?")
    device_id = str(device.get("device_id") or "")
    try:
        client = client_for(device)
    except Exception as exc:  # noqa: BLE001 - a device that cannot be addressed is news
        return Outcome(device_id, name, error=f"could not be reached: {exc}")

    sent = 0
    for one in sending:
        try:
            client.put_launcher(one["launcher_id"], _body(one))
        except Exception as exc:  # noqa: BLE001
            logger.warning("Could not copy launcher %s to %s: %s",
                           one.get("display_name"), name, exc)
            return Outcome(device_id, name, launchers=sent,
                           error=f"{one.get('display_name')} did not arrive: {exc}")
        sent += 1

    mapped = 0
    for table_id, launcher_id in mappings.items():
        try:
            client.put_launcher_mapping(table_id, launcher_id)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Could not copy a mapping to %s: %s", name, exc)
            return Outcome(device_id, name, launchers=sent, mappings=mapped,
                           error=f"the launchers arrived, the assignments did not: {exc}")
        mapped += 1

    return Outcome(device_id, name, launchers=sent, mappings=mapped)


def _body(launcher: dict[str, Any]) -> dict[str, Any]:
    """What travels. Not `owns_ini`: it says whether *this* install created the file, and
    the copy did not create anything on the machine it lands on."""
    return {"app": launcher.get("app", ""),
            "display_name": launcher.get("display_name", ""),
            "enabled": bool(launcher.get("enabled", True)),
            "owns_ini": False,
            "settings": dict(launcher.get("settings") or {})}


def said(outcomes) -> str:
    """One sentence for a notification, naming what did not work.

    Counts where it all worked, names where it did not: "3 devices" is enough when the
    answer is yes, and a person whose cabinet was asleep needs to know which one.
    """
    good = [one for one in outcomes if one.ok]
    bad = [one for one in outcomes if not one.ok]
    if not bad:
        return f"Copied to {len(good)} device{'s' if len(good) != 1 else ''}."
    trouble = "; ".join(f"{one.name} - {one.error}" for one in bad)
    if not good:
        return f"Nothing was copied. {trouble}"
    return (f"Copied to {len(good)} of {len(good) + len(bad)}. {trouble}")
