import unittest

from fastapi import FastAPI
from starlette.testclient import TestClient

import httpapi
from httpapi import capabilities
from httpapi.errors import ApiError, FeatureUnavailableError, NotFoundError


def _client() -> TestClient:
    return TestClient(httpapi.create_api_app(), raise_server_exceptions=False)


class ManufacturerEndpointTests(unittest.TestCase):
    def test_the_logo_lookup_is_enumerable_over_the_wire(self) -> None:
        """VPS names union library names, each with slug, resolution and count."""
        from collections import Counter
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from unittest.mock import patch

        from common.shared_assets import configure_shared_assets

        with TemporaryDirectory() as tmp:
            root = Path(tmp) / "assets"
            (root / "manufacturers" / "default").mkdir(parents=True)
            (root / "manufacturers" / "default" / "bally.png").write_bytes(b"png")
            configure_shared_assets(root)
            self.addCleanup(configure_shared_assets, None)

            with patch("httpapi.manufacturers._vps_names",
                       return_value=["Bally Manufacturing", "Bally Wulff"]), \
                 patch("httpapi.manufacturers._library_counts",
                       return_value=Counter({"Bally Manufacturing": 3,
                                             "Homebrew Works": 1})):
                response = _client().get("/manufacturers")

        self.assertEqual(response.status_code, 200)
        rows = {row["name"]: row for row in response.json()["manufacturers"]}
        self.assertEqual(rows["Bally Manufacturing"]["slug"], "bally")
        self.assertEqual(rows["Bally Manufacturing"]["logo"],
                         "/assets/manufacturers/default/bally.png")
        self.assertEqual(rows["Bally Manufacturing"]["tables"], 3)
        self.assertIsNone(rows["Bally Wulff"]["logo"])
        self.assertEqual(rows["Bally Wulff"]["tables"], 0)
        self.assertEqual(rows["Homebrew Works"]["tables"], 1,
                         "a library-only name still gets a row")


class DiscoveryTests(unittest.TestCase):
    def setUp(self) -> None:
        # create_api_app() declares the core capabilities, so a test that wants a
        # known registry has to build the app first and clear afterwards.
        self.app = httpapi.create_api_app()
        self.client = TestClient(self.app, raise_server_exceptions=False)
        self.addCleanup(capabilities.clear)

    def _isolated(self) -> TestClient:
        capabilities.clear()
        return self.client

    def test_discovery_describes_the_instance(self) -> None:
        body = self.client.get("/").json()

        self.assertEqual(body["name"], "VPinFE")
        self.assertEqual(body["api_version"], "v1")
        self.assertTrue(body["app_version"])
        self.assertEqual(body["extensions"], [])
        declared = {c["name"] for c in body["capabilities"]}
        self.assertIn("library", declared, "the shipped capabilities are declared")

    def test_discovery_links_point_under_the_api_prefix(self) -> None:
        links = self.client.get("/").json()["links"]

        self.assertEqual(links["self"], "/api/v1")
        self.assertEqual(links["health"], "/api/v1/health")
        self.assertEqual(links["openapi"], "/api/v1/openapi.json")
        self.assertEqual(links["docs"], "/api/v1/docs")
        self.assertEqual(links["events"], "/api/v1/events")

    def test_health_reports_ok(self) -> None:
        response = self.client.get("/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    def test_declared_capabilities_appear_in_discovery(self) -> None:
        self._isolated()
        capabilities.declare(capabilities.Capability(
            name="library",
            residency=[capabilities.RESIDENCY_CATALOG],
            description="Table inventory",
        ))
        capabilities.declare(capabilities.Capability(
            name="peripherals",
            residency=[capabilities.RESIDENCY_PLAY_HOST],
            is_available=lambda: (False, "No DOF hardware detected"),
        ))

        declared = self.client.get("/").json()["capabilities"]

        names = [c["name"] for c in declared]
        self.assertEqual(names, sorted(names), "sorted by name for a stable payload")

        by_name = {c["name"]: c for c in declared}
        self.assertEqual(by_name["library"]["residency"], ["catalog"])
        self.assertTrue(by_name["library"]["available"])
        self.assertIsNone(by_name["library"]["reason"])
        self.assertFalse(by_name["peripherals"]["available"])
        self.assertEqual(by_name["peripherals"]["reason"], "No DOF hardware detected")

    def test_a_capability_can_live_in_both_roles(self) -> None:
        """Both means each role serves its own, not that one spans the two."""
        self._isolated()
        capabilities.declare(capabilities.Capability(
            name="events",
            residency=[capabilities.RESIDENCY_CATALOG, capabilities.RESIDENCY_PLAY_HOST],
        ))

        declared = self.client.get("/").json()["capabilities"]

        self.assertEqual(declared[0]["residency"], ["catalog", "play_host"])

    def test_a_bare_string_residency_is_refused(self) -> None:
        """It would iterate into single characters and reach discovery as seven of them."""
        with self.assertRaises(ValueError):
            capabilities.Capability(name="library", residency=capabilities.RESIDENCY_CATALOG)

    def test_an_unknown_or_empty_residency_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            capabilities.Capability(name="library", residency=["somewhere-else"])
        with self.assertRaises(ValueError):
            capabilities.Capability(name="library", residency=[])

    def test_launch_declares_whether_this_machine_can_do_it(self) -> None:
        """Reading play state works without a launcher; starting a table does not.
        Discovery has to say so, or a client shows a Play button that always 501s."""
        declared = {c["name"]: c for c in self.client.get("/").json()["capabilities"]}

        self.assertIn("launch", declared)
        self.assertEqual(declared["launch"]["residency"], ["play_host"])
        self.assertIsNotNone(declared["launch"].get("available"))

    def test_a_broken_availability_probe_does_not_break_discovery(self) -> None:
        def _explode():
            raise RuntimeError("probe blew up")

        self._isolated()
        capabilities.declare(capabilities.Capability(
            name="flaky", residency=[capabilities.RESIDENCY_PLAY_HOST], is_available=_explode))

        response = self.client.get("/")
        declared = response.json()["capabilities"]

        self.assertEqual(response.status_code, 200)
        self.assertFalse(declared[0]["available"])
        self.assertIn("probe blew up", declared[0]["reason"])


class ErrorEnvelopeTests(unittest.TestCase):
    """Every failure under /api/v1 comes back in the one envelope shape."""

    def _envelope(self, response):
        body = response.json()
        self.assertEqual(set(body), {"error"})
        self.assertEqual(set(body["error"]), {"code", "message", "details"})
        return body["error"]

    def test_unknown_route_returns_not_found_envelope(self) -> None:
        response = _client().get("/no-such-thing")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(self._envelope(response)["code"], "not_found")

    def test_wrong_method_returns_method_not_allowed_envelope(self) -> None:
        response = _client().post("/health")

        self.assertEqual(response.status_code, 405)
        self.assertEqual(self._envelope(response)["code"], "method_not_allowed")

    def test_api_error_carries_its_code_status_and_details(self) -> None:
        api = httpapi.create_api_app()

        @api.get("/raises")
        def _raises():
            raise ApiError("teapot", "I'm a teapot", status_code=418, details={"tea": "earl grey"})

        response = TestClient(api, raise_server_exceptions=False).get("/raises")
        error = self._envelope(response)

        self.assertEqual(response.status_code, 418)
        self.assertEqual(error["code"], "teapot")
        self.assertEqual(error["message"], "I'm a teapot")
        self.assertEqual(error["details"], {"tea": "earl grey"})

    def test_helper_errors_map_to_their_statuses(self) -> None:
        api = httpapi.create_api_app()

        @api.get("/missing")
        def _missing():
            raise NotFoundError("No such table")

        @api.get("/unavailable")
        def _unavailable():
            raise FeatureUnavailableError("DOF is not configured on this instance")

        client = TestClient(api, raise_server_exceptions=False)

        missing = client.get("/missing")
        self.assertEqual(missing.status_code, 404)
        self.assertEqual(self._envelope(missing)["code"], "not_found")

        unavailable = client.get("/unavailable")
        self.assertEqual(unavailable.status_code, 501)
        self.assertEqual(self._envelope(unavailable)["code"], "feature_unavailable")

    def test_bad_query_parameter_returns_invalid_request_with_details(self) -> None:
        api = httpapi.create_api_app()

        @api.get("/needs-int")
        def _needs_int(count: int):
            return {"count": count}

        response = TestClient(api, raise_server_exceptions=False).get("/needs-int?count=nope")
        error = self._envelope(response)

        self.assertEqual(response.status_code, 422)
        self.assertEqual(error["code"], "invalid_request")
        self.assertTrue(error["details"])

    def test_unhandled_exception_returns_internal_error_and_leaks_nothing(self) -> None:
        api = httpapi.create_api_app()

        @api.get("/boom")
        def _boom():
            raise RuntimeError("secret internal detail")

        with self.assertLogs("vpinfe.httpapi.errors", level="ERROR"):
            response = TestClient(api, raise_server_exceptions=False).get("/boom")
        error = self._envelope(response)

        self.assertEqual(response.status_code, 500)
        self.assertEqual(error["code"], "internal_error")
        self.assertNotIn("secret internal detail", response.text)


class OpenApiTests(unittest.TestCase):
    def test_spec_is_served_and_scoped_to_the_mount(self) -> None:
        spec = _client().get("/openapi.json").json()

        self.assertEqual(spec["info"]["title"], "VPinFE API")
        self.assertIn("/health", spec["paths"])

    def test_docs_page_is_served(self) -> None:
        self.assertEqual(_client().get("/docs").status_code, 200)


class RegistrationTests(unittest.TestCase):
    """register() mounts the API without disturbing the app it mounts onto."""

    def setUp(self) -> None:
        self.parent = FastAPI()

        @self.parent.get("/api/host-owned")
        def _legacy():
            return {"launching": False, "table_name": None}

        @self.parent.get("/existing")
        def _existing():
            return {"ok": True}

        httpapi.register(self.parent)
        self.client = TestClient(self.parent, raise_server_exceptions=False)

    def test_discovery_answers_with_and_without_the_trailing_slash(self) -> None:
        for path in ("/api/v1", "/api/v1/"):
            with self.subTest(path=path):
                response = self.client.get(path, follow_redirects=False)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()["api_version"], "v1")

    def test_mounted_routes_are_reachable(self) -> None:
        self.assertEqual(self.client.get("/api/v1/health").json(), {"status": "ok"})

    def test_openapi_servers_url_lets_clients_resolve_real_paths(self) -> None:
        spec = self.client.get("/api/v1/openapi.json").json()

        # Paths in the spec are mount-relative, so the server URL is what makes
        # a generated client hit /api/v1/health rather than /health.
        self.assertEqual(spec.get("servers"), [{"url": "/api/v1"}])

    def test_existing_routes_are_untouched(self) -> None:
        self.assertEqual(self.client.get("/existing").json(), {"ok": True})
        self.assertEqual(
            self.client.get("/api/host-owned").json(),
            {"launching": False, "table_name": None},
        )

    def test_cors_is_scoped_to_the_api(self) -> None:
        preflight = {"Origin": "http://localhost:8000", "Access-Control-Request-Method": "GET"}

        allowed = self.client.options("/api/v1/health", headers=preflight)
        self.assertEqual(allowed.status_code, 200)
        self.assertEqual(allowed.headers["access-control-allow-origin"], "*")

        # The host app keeps whatever CORS behaviour it had, which is none.
        untouched = self.client.options("/api/host-owned", headers=preflight)
        self.assertNotIn("access-control-allow-origin", untouched.headers)

    def test_the_envelope_does_not_apply_outside_the_api(self) -> None:
        outside = self.client.get("/not-a-route")

        self.assertEqual(outside.status_code, 404)
        self.assertNotIn("error", outside.json())


if __name__ == "__main__":
    unittest.main()
