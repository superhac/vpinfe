"""The four ways a service refuses, so a caller can tell one refusal from another.

A caller matches on the type, never on the message: the message is already the sentence a
person reads, and `details` is what a surface needs to name the thing it is about. Four,
because that is how many distinct things a caller does about a refusal - look elsewhere,
fix the request, try again later, or stop offering it here.

A service is free to raise something more specific as long as it derives from one of
these, which is how a caller that only cares about the kind and a caller that cares about
the particular can both be served.
"""

from __future__ import annotations

from typing import Any


class ServiceError(Exception):
    def __init__(self, message: str = "", *, details: Any = None) -> None:
        super().__init__(message)
        self.details = details


class NotFoundError(ServiceError):
    """Nothing here goes by that name."""


class RefusedError(ServiceError):
    """The request itself is wrong, and sending it again will not help."""


class BlockedError(ServiceError):
    """The request is fine and cannot happen right now - something is in the way."""


class UnavailableError(ServiceError):
    """Exists, but not on this install. The message says what is missing."""
