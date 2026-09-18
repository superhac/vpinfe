"""An extension's routes: gated by core, listed by core, and gone when it breaks.

The app mounts what the registry already holds, so each test builds the registry it
wants and then the app - which is also how `main.py` does it.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from starlette.testclient import TestClient

import httpapi
from common import extensions
from common.extensions import contract, host, store
from httpapi import auth, scopes

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "extensions"


class SeamCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.store = store.ExtensionStore(self.root / "extensions.json")
        self.registry = host.Registry(self.store)
        extensions.set_registry(self.registry)
        self.addCleanup(extensions.set_registry, host.Registry())
        self.addCleanup(self.registry.clear)

    def client(self, load: bool = True) -> TestClient:
        if load:
            self.registry.load_from(FIXTURES)
        return TestClient(httpapi.create_api_app(), raise_server_exceptions=False)


class MountTests(SeamCase):
    def test_an_extensions_routes_answer_under_its_own_name(self) -> None:
        found = self.client().get("/ext/sample/hello")

        self.assertEqual(found.status_code, 200)
        self.assertEqual(found.json(), {"name": "sample", "greeting": "hello"})

    def test_a_route_reads_the_extensions_own_settings(self) -> None:
        self.store.set_setting("sample", "greeting", "good evening")

        found = self.client().get("/ext/sample/hello")

        self.assertEqual(found.json()["greeting"], "good evening")

    def test_every_extension_route_declares_the_scope_it_was_gated_on(self) -> None:
        """Core attaches the gate, so an extension cannot ship a route without one."""
        self.registry.load_from(FIXTURES)
        api = httpapi.create_api_app()

        gated = {path: auth.route_scope(route)
                 for path, route in auth.iter_api_routes(api)
                 if path.startswith("/ext/")}

        self.assertTrue(gated)
        self.assertEqual(set(gated.values()), {"ext:sample:read", "ext:bystander:read"})

    def test_a_running_extension_grants_the_scope_its_routes_need(self) -> None:
        self.registry.load_from(FIXTURES)

        held = auth.LocalTrustPolicy().identify(None).scopes

        self.assertTrue(scopes.CORE <= held)
        self.assertIn("ext:sample:read", held)

    def test_an_install_with_no_extensions_holds_the_core_scopes_and_no_more(self) -> None:
        self.assertEqual(auth.LocalTrustPolicy().identify(None).scopes, scopes.CORE)

    def test_the_gate_actually_runs(self) -> None:
        """Declaring the scope is not the same as enforcing it, and the difference is
        invisible under local trust - which grants everything. So the policy is swapped
        for one that grants core and nothing else, and the route has to refuse."""
        class CoreOnly:
            name = "test"

            def identify(self, request) -> auth.Identity:
                return auth.Identity(name="test", scopes=scopes.CORE)

        client = self.client()
        auth.set_policy(CoreOnly())
        self.addCleanup(auth.set_policy, auth.LocalTrustPolicy())

        found = client.get("/ext/sample/hello")

        self.assertEqual(found.status_code, 403)
        self.assertIn("ext:sample:read", found.json()["error"]["message"])


class ListingTests(SeamCase):
    def test_the_listing_names_every_extension_and_its_state(self) -> None:
        found = self.client().get("/extensions").json()["extensions"]

        self.assertEqual([one["name"] for one in found], ["bystander", "sample"])
        self.assertEqual({one["state"] for one in found}, {"loaded"})

    def test_the_listing_carries_what_an_extension_declared(self) -> None:
        found = self.client().get("/extensions").json()["extensions"]
        sample = next(one for one in found if one["name"] == "sample")

        self.assertEqual(sample["display_name"], "Sample")
        self.assertEqual(sample["capabilities"], ["config:own", "ui:mount"])
        self.assertEqual(sample["routes"], ["ext:sample:read"])

    def test_one_that_did_not_load_is_listed_with_the_reason(self) -> None:
        self.store.set_enabled("sample", False)

        found = self.client().get("/extensions").json()["extensions"]
        sample = next(one for one in found if one["name"] == "sample")

        self.assertEqual(sample["state"], "off")
        self.assertEqual(sample["reason"], "Switched off")


class FailureTests(SeamCase):
    def test_a_route_that_throws_disables_that_extension_and_leaves_core_running(self):
        client = self.client()

        with self.assertLogs("vpinfe.httpapi.errors", "ERROR"), \
                self.assertLogs("vpinfe.common.extensions", "ERROR"):
            self.assertEqual(client.get("/ext/sample/boom").status_code, 500)

        self.assertEqual(self.registry.get("sample").state, host.DISABLED)
        self.assertEqual(client.get("/health").status_code, 200)
        self.assertEqual(client.get("/ext/bystander/hello").status_code, 200)

    def test_a_disabled_extensions_routes_say_which_one_and_why(self) -> None:
        client = self.client()
        with self.assertLogs("vpinfe.httpapi.errors", "ERROR"), \
                self.assertLogs("vpinfe.common.extensions", "ERROR"):
            client.get("/ext/sample/boom")

        found = client.get("/ext/sample/hello")

        self.assertEqual(found.status_code, 501)
        self.assertIn("Sample", found.json()["error"]["message"])
        self.assertIn("Unhandled error", found.json()["error"]["message"])

    def test_a_disabled_extension_no_longer_holds_its_scope(self) -> None:
        client = self.client()
        with self.assertLogs("vpinfe.httpapi.errors", "ERROR"), \
                self.assertLogs("vpinfe.common.extensions", "ERROR"):
            client.get("/ext/sample/boom")

        self.assertNotIn("ext:sample:read",
                         auth.LocalTrustPolicy().identify(None).scopes)

    def test_an_extension_asking_for_a_scope_that_does_not_exist_is_refused(self) -> None:
        """The manifest is the consent surface, so a scope nobody could grant is a
        manifest nobody could have agreed to."""
        directory = self.root / "invented"
        directory.mkdir()
        (directory / "extension.json").write_text(json.dumps({
            "name": "invented", "version": "1.0.0",
            "requires_platform": contract.PLATFORM_ABI,
            "scopes": ["tables:teleport"], "provides": ["read"],
        }), encoding="utf-8")
        (directory / "__init__.py").write_text(
            "from fastapi import APIRouter\n"
            "def register(ctx):\n"
            "    router = APIRouter()\n"
            "    @router.get('/hello')\n"
            "    def hello() -> dict:\n"
            "        return {}\n"
            "    ctx.add_router(router, scope=ctx.scope('read'))\n", encoding="utf-8")
        self.registry.load(directory)

        with self.assertLogs("vpinfe.common.extensions", "ERROR"):
            client = TestClient(httpapi.create_api_app(), raise_server_exceptions=False)

        self.assertEqual(self.registry.get("invented").state, host.FAILED)
        self.assertEqual(client.get("/ext/invented/hello").status_code, 501)


if __name__ == "__main__":
    unittest.main()
