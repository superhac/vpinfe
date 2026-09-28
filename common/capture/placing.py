"""Which output shows each window: the desktop once the table is up, then the app's own
settings, then VPinFE's screens."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from common import apps
from common.host import launch

from . import adapters
from .adapters import Output, Screen

NOT_SHOWN = "capture.screen.not_shown"


def _nothing(app_id: str, title: str) -> str:
    return ""


@dataclass(frozen=True)
class Shown:
    """What the app that plays a table says of its windows, as its capture hook answers.
    `app` is the app's name, said to people."""

    app: str
    outputs: Mapping[str, str] = field(default_factory=dict)
    window: Callable[[str, str], str] = _nothing


def shown(game: Any = None, table: str | None = None) -> Shown | None:
    """For the app a launch of this table would run, or the default launcher's with no
    game. None where no app with a capture hook would play it."""
    try:
        found = launch.launched_by(game, table)
    except launch.LaunchUnavailableError:
        return None
    if found is None:
        return None
    app, entry, settings = found
    if app.capture is None:
        return None
    return Shown(apps.app_name(app.id), dict(app.capture.outputs(entry, settings)),
                 app.capture.window)


def seen(adapter: adapters.Adapter, said: Shown) -> dict[str, str] | None:
    """The output each of the app's windows is on, as the desktop says, or None where it
    cannot say or shows no playfield window of the app's."""
    try:
        windows = adapter.windows()
    except (OSError, ValueError):
        return None
    found: dict[str, str] = {}
    for one in windows:
        window = said.window(one.app_id, one.title)
        if window:
            found.setdefault(window, one.output)
    return found if adapters.PLAYFIELD in found else None


@dataclass(frozen=True)
class Placing:
    """Everything that says where a window is, kept so it can be asked again once the
    desktop can say."""

    outputs: Sequence[Output]
    config: Any
    monitors: Sequence[Any]
    shown: Shown | None = None

    def screen(self, window: str, seen: Mapping[str, str] | None = None) -> Screen:
        named = {one.name: one for one in self.outputs if one.name}
        said = self.shown
        if said is not None and seen is not None:
            if window not in seen:
                return Screen(window, reason=NOT_SHOWN, params={"app": said.app})
            if seen[window] in named:
                return Screen(window, named[seen[window]])
        if said is not None and window in said.outputs:
            name = said.outputs[window]
            if not name:
                return Screen(window, reason=NOT_SHOWN, params={"app": said.app})
            if name in named:
                return Screen(window, named[name])
        return adapters.screen_of(window, self.outputs, self.config, self.monitors)

    def screens(self, seen: Mapping[str, str] | None = None) -> dict[str, Screen]:
        return {window: self.screen(window, seen) for window in adapters.WINDOWS}
