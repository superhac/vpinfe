"""Whether an install's configuration is enough for the features it has switched on.

Enablement and availability answer different questions and this is the first. A feature
is a deliberate choice; a requirement is what that choice needs in order to work. An
install with `frontend` on and no launcher configured is *misconfigured*, which is not
the same as an install that simply has no peripherals - and only the first is something
a person should be shown and asked to fix.

That distinction is why this is separate from `is_available` on a capability.
`_peripherals_available` returns False on any machine without DOF or a real DMD, which is
most of them and is correctly configured; marking that as a problem would put a warning on
a healthy install, and a mark that appears on everything says nothing.
"""

from __future__ import annotations

from dataclasses import dataclass

from common import install_identity, path_checks
from common.config_access import cfg_get

# What each feature needs before it can do its job. Both of these happen to be paths,
# which is not a rule - a requirement is any setting a feature cannot work without, and
# paths are simply what the first two are.
REQUIREMENTS: dict[str, tuple[tuple[str, str], ...]] = {
    # Curating a library needs somewhere to find the games.
    install_identity.LIBRARY: (("general", "game_root_dir"),),
    # Launching needs the games and something to launch them with.
    install_identity.FRONTEND: (("general", "game_root_dir"),
                                ("general", "vpx_bin_path")),
    # Managing other installs needs nothing of its own: it reaches them over the network,
    # and an address it cannot reach is that device's row to report, not a setting here.
    install_identity.DEVICES: (),
    # A rollup reports on whatever the other features hold. It has nothing of its own to
    # be missing, and an empty library is a fact about the library rather than a fault
    # in the page that counts it.
    install_identity.OVERVIEW: (),
}


# Where a frontend is told which library to read. Not a path, which is why it sits beside
# the table above rather than in it: what it names is another install.
LIBRARY_URL = ("network", "library_url")


@dataclass(frozen=True)
class Unmet:
    """One requirement an enabled feature does not have. `reason` is written for the
    person who has to fix it, and names what was found rather than what was wanted."""

    feature: str
    section: str
    key: str
    state: str
    reason: str


def _option(section: str, key: str):
    from common import config_schema

    return next((o for o in config_schema.CONFIG_OPTIONS
                 if o.section == section and o.key == key), None)


def unmet(config, features=None) -> list[Unmet]:
    """Every requirement the enabled features do not satisfy, in feature order.

    One entry per (feature, setting), so a setting two features both need is reported
    against each of them - the person is looking at one feature's page and needs to know
    that page is affected, not that some other feature also is.
    """
    on = list(features) if features is not None else install_identity.features(config)
    found: list[Unmet] = []
    for feature in install_identity.FEATURES:
        if feature not in on:
            continue
        for section, key in REQUIREMENTS.get(feature, ()):
            option = _option(section, key)
            if option is None:
                continue
            state, reason = path_checks.check(option.path,
                                              cfg_get(config, section, key))
            if state == path_checks.OK:
                continue
            # Unset is a failure here even though it is not one for the setting itself:
            # blank means "use the default" for an optional path, and these have no
            # default to fall back on.
            if state == path_checks.UNSET:
                reason = f"{option.label} is not set."
            found.append(Unmet(feature=feature, section=section, key=key,
                               state=state, reason=reason))
    missing_library = _no_library_to_read(config, on)
    if missing_library is not None:
        found.append(missing_library)
    return found


def _no_library_to_read(config, on) -> Unmet | None:
    """A frontend that holds no library of its own and has not been told which to read.

    Not guessed at, not even when exactly one install on the network has a library. A
    silent pick is the kind of thing nobody can debug afterwards, and the catalog belongs
    to a different machine.
    """
    if install_identity.FRONTEND not in on or install_identity.LIBRARY in on:
        return None
    if cfg_get(config, *LIBRARY_URL).strip():
        return None
    return Unmet(feature=install_identity.FRONTEND,
                 section=LIBRARY_URL[0], key=LIBRARY_URL[1],
                 state=path_checks.UNSET,
                 reason="No library chosen, and this install holds none of its own.")


def features_in_trouble(config, features=None) -> set[str]:
    """Just the names, for a caller that only has to decide whether to mark something."""
    return {item.feature for item in unmet(config, features)}
