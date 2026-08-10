"""Whether a caller reached us from this machine or over the network.

The hub binds every interface by default and has since 2.x, so a phone can administer a
cabinet. That means "on this machine" and "able to reach this machine" have never been
the same question, and until now nothing could tell them apart - every caller was
identified as `local` whether it was or not.

This records the difference without acting on it. What a network caller is *allowed* is
a separate decision; this is the fact that decision needs, and asserting it now is what
stops the distinction being wrong on the day something starts depending on it.
"""

from __future__ import annotations

import unittest
from types import SimpleNamespace

from httpapi import auth, scopes


def _request(host, **headers):
    """A request as Starlette hands one over: a peer address, and headers."""
    client = SimpleNamespace(host=host) if host is not None else None
    return SimpleNamespace(client=client, headers=headers)


class CallerOriginTests(unittest.TestCase):
    def setUp(self) -> None:
        self.policy = auth.LocalTrustPolicy()

    def test_a_request_from_this_machine_is_local(self) -> None:
        for host in ("127.0.0.1", "::1", "localhost"):
            with self.subTest(host=host):
                self.assertTrue(auth.caller_is_local(_request(host)))

    def test_a_request_from_anywhere_else_is_not(self) -> None:
        for host in ("192.168.110.42", "10.0.0.5", "203.0.113.9"):
            with self.subTest(host=host):
                self.assertFalse(auth.caller_is_local(_request(host)))

    def test_an_in_process_call_is_local(self) -> None:
        """No socket means no remote party to be cautious about."""
        self.assertTrue(auth.caller_is_local(_request(None)))

    def test_a_caller_cannot_declare_itself_local(self) -> None:
        """X-Forwarded-For is written by whoever sent the request. Reading it here would
        let any caller claim to be on the machine, which is the whole distinction."""
        spoofed = _request("10.0.0.5", **{"X-Forwarded-For": "127.0.0.1"})

        self.assertFalse(auth.caller_is_local(spoofed))
        self.assertEqual(self.policy.identify(spoofed).origin, auth.NETWORK)

    def test_the_identity_records_where_the_caller_came_from(self) -> None:
        self.assertEqual(self.policy.identify(_request("127.0.0.1")).origin, auth.LOCAL)
        self.assertEqual(self.policy.identify(_request("10.0.0.5")).origin, auth.NETWORK)

    def test_nothing_a_caller_may_do_has_changed_yet(self) -> None:
        """Deliberately: this commit is the distinction, not a policy over it. A network
        caller keeps exactly the scopes it had, so no install behaves differently."""
        for host in ("127.0.0.1", "10.0.0.5"):
            with self.subTest(host=host):
                self.assertEqual(self.policy.identify(_request(host)).scopes, scopes.CORE)

    def test_an_identity_built_without_an_origin_reads_as_network(self) -> None:
        """The cautious default: a policy or a test that forgets to say must not have
        its identity silently claim to be on the machine."""
        anonymous = auth.Identity(name="whoever", scopes=frozenset())

        self.assertEqual(anonymous.origin, auth.NETWORK)
        self.assertFalse(anonymous.is_local)


if __name__ == "__main__":
    unittest.main()
