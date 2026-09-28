"""Which frontend devices won't play a video, from what each device's browser said.

Never the Console's own browser: it is not the cabinet, and it previews perfectly a file
the cabinet cannot play at all. Only what a device's frontend reported about itself, as
the device registry keeps it.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from common.host import frontend_browser
from common.i18n import t
from console import settings
from console.devices import device_label

_NAMES = {one.id: one.name for one in frontend_browser.FORMATS}
_VIDEO = {one.id for one in frontend_browser.FORMATS if one.kind == frontend_browser.VIDEO}

# The states the Browser settings page leads with, and the codecs its finding is about.
_FIXED_BY_ITS_BROWSER = {frontend_browser.NO_H264: {"h264"},
                         frontend_browser.NO_VIDEO: {"h264", "vp9"}}


@dataclass(frozen=True)
class Refusal:
    label: str
    why: str


def _formats(device: dict[str, Any]) -> dict[str, Any]:
    return dict((device.get("browser") or {}).get("formats") or {})


def asks_codecs(devices: Sequence[dict[str, Any]]) -> bool:
    """Whether any device said no to a video format: until one does, no file's codec
    can matter."""
    return any(_formats(device).get(one) is False for device in devices for one in _VIDEO)


def refusals(codec: str | None, devices: Sequence[dict[str, Any]],
             local_id: str) -> list[Refusal]:
    """One for each of `devices`, the whole registry, whose browser said it does not play
    `codec`."""
    if not codec:
        return []
    alone = all(str(device.get("device_id") or "") == local_id for device in devices)
    found = []
    for device in devices:
        if _formats(device).get(codec) is not False:
            continue
        here = str(device.get("device_id") or "") == local_id
        label = t("console.plays_on.wont_play_here") if here and alone \
            else t("console.plays_on.wont_play_on", device=device_label(device))
        found.append(Refusal(label, _why(device, codec, here)))
    return found


def _why(device: dict[str, Any], codec: str, here: bool) -> str:
    name = _NAMES.get(codec, codec)
    state = str((device.get("browser") or {}).get("state") or "")
    if codec not in _FIXED_BY_ITS_BROWSER.get(state, set()):
        return t("console.plays_on.why", codec=name)
    place = " › ".join(settings.place_of("chromium"))
    return t("console.plays_on.why_fix_here" if here else "console.plays_on.why_fix_there",
             codec=name, place=place)
