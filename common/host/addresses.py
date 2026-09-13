"""The addresses this machine can be reached on.

Written down once because it was written down three times: two copies in the frontend's
config API and one in the Manager UI, all answering "what would somebody type into a
phone to reach this install". A page that hands out the wrong address is a page that
sends a person to a machine that is not there, and three copies is three chances to
drift on which addresses count.

Loopback is offered last and never first. It is the one address that is certainly
listening and the one that certainly does not work from anywhere else, so a list that
led with it would be a list whose first answer is wrong for the reader holding a phone.
"""

from __future__ import annotations

import ipaddress
import socket


def usable_ipv4(value: str) -> bool:
    """Whether this is an address something else on the network could dial.

    Loopback and link-local are excluded here rather than filtered by the caller: a
    169.254 address means the machine failed to get a lease, and offering it reads as
    an answer.
    """
    try:
        found = ipaddress.ip_address((value or "").strip())
    except ValueError:
        return False
    return (found.version == 4 and not found.is_loopback
            and not found.is_link_local and not found.is_multicast
            and not found.is_unspecified)


def primary_ipv4() -> str:
    """The address this machine would use to reach the rest of the network.

    Asked by opening a socket at a public address and reading which interface the
    kernel chose. Nothing is sent - UDP connect only sets the peer - so this costs no
    traffic and works with the network down, which is when the answer is least obvious.
    """
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            probe.settimeout(0.2)
            probe.connect(("192.0.2.1", 9))
            found = str(probe.getsockname()[0])
    except Exception:
        return ""
    return found if usable_ipv4(found) else ""


def hosts() -> list[str]:
    """Every name and address worth offering, best first, loopback last.

    The routed address leads because it is the one that works from another machine.
    The hostname follows: it is what a person recognizes, and it is the one that keeps
    working when the lease changes.
    """
    found: list[str] = []
    seen: set[str] = set()

    def add(host: str) -> None:
        said = (host or "").strip()
        if said and said.lower() not in seen:
            seen.add(said.lower())
            found.append(said)

    add(primary_ipv4())
    name = _hostname()
    if name:
        add(name)
        for address in _resolved(name):
            add(address)
    add("localhost")
    return found


def urls(port: int, path: str = "/") -> list[str]:
    """The same list as somewhere to go."""
    return [f"http://{host}:{int(port)}{path}" for host in hosts()]


def best(port: int, path: str = "/") -> str:
    """The one to put in front of somebody, or "" where there is nothing to offer.

    Never loopback while anything else is on the list: this is the address that goes
    on a screen for a person holding a different device.
    """
    found = urls(port, path)
    return next((one for one in found if "://localhost:" not in one),
                found[0] if found else "")


def _hostname() -> str:
    try:
        name = socket.gethostname().strip()
    except Exception:
        return ""
    return "" if name.lower() in {"localhost", "ip6-localhost"} else name


def _resolved(name: str) -> list[str]:
    """The IPv4 addresses a hostname resolves to, or none.

    Never raises: a machine whose own name does not resolve is common enough - it is
    what a fresh container does - and it must not take the rest of the list with it.
    """
    try:
        found = socket.getaddrinfo(name, None, socket.AF_INET)
    except Exception:
        return []
    return [str(where[0]) for family, _, _, _, where in found
            if family == socket.AF_INET and usable_ipv4(str(where[0]))]
