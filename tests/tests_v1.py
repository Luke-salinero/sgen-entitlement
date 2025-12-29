import unittest
from dataclasses import dataclass
from typing import Any, Optional
from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.api.v1 as v1_module

# --------- Helpers / test doubles ---------


@dataclass(frozen=True)
class FakeIdentity:
    subject_id: int
    account_name: str
    provider: str


@dataclass(frozen=True)
class FakeEffectiveEntitlements:
    userID: int
    apiKeyID: int
    accountName: str
    subject_status: str

    plan_id: int
    tier: str
    plan_status: str
    allow_live: bool

    max_n: int
    max_k: int
    existential_only: bool
    rate_limit: int
    rate_window: int

    plan_description: Optional[str] = None


class FakeEntitlementService:
    def __init__(self, result: Any = None, exc: Exception | None = None) -> None:
        self._result = result
        self._exc = exc
        self.calls: list[dict[str, Any]] = []

    def get_entitlements(self, claims: dict[str, Any]) -> Any:
        self.calls.append({"claims": claims})
        if self._exc is not None:
            raise self._exc
        return self._result


def make_exc(exc_cls: type[Exception], msg: str) -> Exception:
    """
    Create an instance of a project exception robustly.
    v1.py reads `.message` for auth errors, so ensure it's present.
    """
    try:
        e = exc_cls(msg)  # type: ignore[call-arg]
    except TypeError:
        e = exc_cls()  # type: ignore[call-arg]
        e.message = msg
        return e

    if not hasattr(e, "message"):
        e.message = msg
    return e


def build_app() -> FastAPI:
    app = FastAPI()
    app.include_router(v1_module.router)
    return app


# --------- Tests ---------


class TestRequestIdHelpers(unittest.TestCase):
    def test_request_id_prefers_gateway_header(self):
        """Use case: preserve upstream trace id across services.
        If this fails, distributed tracing becomes fragmented and
        debugging production incidents is harder."""
        req = MagicMock()
        req.headers = {"x-request-id": "gw-123"}
        self.assertEqual(v1_module._request_id_from_headers(req), "gw-123")

    def test_request_id_falls_back_to_uuid(self):
        """Use case: still emit a request id when no gateway header exists.
        If this fails, some requests lose correlation ids in logs/metrics."""
        req = MagicMock()
        req.headers = {}
        with patch.object(v1_module, "uuid4", return_value="fixed-uuid"):
            self.assertEqual(v1_module._request_id_from_headers(req), "fixed-uuid")


class TestGetConnDependency(unittest.TestCase):
    def test_get_conn_yields_connection_and_closes_on_generator_close(self):
        """Use case: DB connections must be cleaned up reliably after request handling.
        If this fails, you can leak SQLite connections and
        degrade the service over time.
        """
        mock_conn = MagicMock()
        with patch.object(v1_module, "get_connection", return_value=mock_conn):
            gen = v1_module.get_conn()
            yielded = next(gen)
            self.assertIs(yielded, mock_conn)

            # FastAPI will close/finish the generator after the request;
            # this should run the finally: conn.close()
            gen.close()
            mock_conn.close.assert_called_once()


class TestWhoAmIEndpoint(unittest.TestCase):
    def setUp(self) -> None:
        self.app = build_app()

    def test_whoami_success_returns_identity_and_sets_request_id(self):
        """Use case: debug endpoint confirms auth plumbing works end-to-end.
        If this fails, you may have a broken auth integration or
        response shaping issues.
        """
        client = TestClient(self.app)

        identity = FakeIdentity(subject_id=1, account_name="Acme", provider="jwt")
        with patch.object(v1_module, "authenticate_request", return_value=identity):
            resp = client.get(
                "/v1/whoami",
                headers={"x-request-id": "gw-1", "authorization": "Bearer x"},
            )
            self.assertEqual(resp.status_code, 200)
            self.assertEqual(resp.headers.get("X-Request-Id"), "gw-1")
            self.assertEqual(
                resp.json(),
                {"subject_id": 1, "account_name": "Acme", "provider": "jwt"},
            )

    def test_whoami_generates_request_id_when_missing(self):
        """Use case: every response should include a
        request id even without gateway support.
        If this fails, some responses cannot be
        correlated during incident investigation.
        """
        client = TestClient(self.app)

        identity = FakeIdentity(subject_id=1, account_name="Acme", provider="jwt")
        with (
            patch.object(v1_module, "uuid4", return_value="fixed-uuid"),
            patch.object(v1_module, "authenticate_request", return_value=identity),
        ):
            resp = client.get("/v1/whoami", headers={"authorization": "Bearer x"})
            self.assertEqual(resp.status_code, 200)
            self.assertEqual(resp.headers.get("X-Request-Id"), "fixed-uuid")

    def test_whoami_missing_auth_maps_to_401(self):
        """Use case: missing credentials must be rejected as unauthorized.
        If this fails, anonymous callers may get access or
        clients will see incorrect status codes.
        """
        client = TestClient(self.app)

        exc = make_exc(v1_module.MissingAuthenticationError, "missing auth")
        with patch.object(v1_module, "authenticate_request", side_effect=exc):
            resp = client.get("/v1/whoami")
            self.assertEqual(resp.status_code, 401)
            self.assertEqual(resp.json()["detail"], "missing auth")

    def test_whoami_invalid_auth_maps_to_401(self):
        """Use case: invalid credentials must be rejected as unauthorized.
        If this fails, bad tokens may produce misleading 500s or leak internal details.
        """
        client = TestClient(self.app)

        exc = make_exc(v1_module.InvalidAuthenticationError, "invalid auth")
        with patch.object(v1_module, "authenticate_request", side_effect=exc):
            resp = client.get("/v1/whoami", headers={"authorization": "Bearer bad"})
            self.assertEqual(resp.status_code, 401)
            self.assertEqual(resp.json()["detail"], "invalid auth")

    def test_whoami_generic_auth_error_maps_to_401(self):
        """Use case: all auth failures should be treated as unauthorized for callers.
        If this fails, clients may retry incorrectly or treat auth issues as outages."""
        client = TestClient(self.app)

        exc = make_exc(v1_module.AuthenticationError, "auth error")
        with patch.object(v1_module, "authenticate_request", side_effect=exc):
            resp = client.get("/v1/whoami", headers={"authorization": "Bearer x"})
            self.assertEqual(resp.status_code, 401)
            self.assertEqual(resp.json()["detail"], "auth error")


class TestEntitlementsEndpoint(unittest.TestCase):
    def setUp(self) -> None:
        self.app = build_app()
        self.client = TestClient(self.app)

    def tearDown(self) -> None:
        # Avoid cross-test pollution if any overrides were used.
        self.app.dependency_overrides = {}

    def test_entitlements_happy_path_payload_shape_and_values(self):
        """Use case: gateway depends on this exact JSON shape to enforce limits.
        If this fails, enforcement may break or apply incorrect limits."""
        identity = FakeIdentity(subject_id=42, account_name="Acme", provider="jwt")
        eff = FakeEffectiveEntitlements(
            userID=42,
            apiKeyID=123,
            accountName="Acme",
            subject_status="active",
            plan_id=2,
            tier="pro",
            plan_status="active",
            allow_live=True,
            max_n=31,
            max_k=16,
            existential_only=True,
            rate_limit=99,
            rate_window=120,
            plan_description="Pro plan",
        )
        svc = FakeEntitlementService(result=eff)

        # With Depends, the clean way is dependency override:
        self.app.dependency_overrides[v1_module._get_entitlement_service] = lambda: svc

        with patch.object(v1_module, "authenticate_request", return_value=identity):
            resp = self.client.get(
                "/v1/entitlements", headers={"authorization": "Bearer good"}
            )
            self.assertEqual(resp.status_code, 200)

            body = resp.json()
            self.assertEqual(body["subject_id"], 42)
            self.assertEqual(body["account_name"], "Acme")
            self.assertEqual(body["tier"], "pro")
            self.assertEqual(body["allow_live"], True)

            self.assertEqual(body["limits"]["max_n"], 31)
            self.assertEqual(body["limits"]["max_k"], 16)
            self.assertEqual(body["limits"]["existential_only"], True)
            self.assertEqual(body["limits"]["rate_limit"], 99)
            self.assertEqual(body["limits"]["rate_window"], 120)

            self.assertEqual(svc.calls, [{"claims": {"userID": 42}}])

    def test_entitlements_sets_x_request_id_from_incoming_header(self):
        """Use case: preserve upstream request id for traceability in the gateway.
        If this fails, debugging and correlation across services becomes harder."""
        identity = FakeIdentity(subject_id=7, account_name="Acme", provider="jwt")
        eff = FakeEffectiveEntitlements(
            userID=7,
            apiKeyID=77,
            accountName="Acme",
            subject_status="active",
            plan_id=1,
            tier="free",
            plan_status="active",
            allow_live=False,
            max_n=15,
            max_k=8,
            existential_only=False,
            rate_limit=10,
            rate_window=60,
        )
        svc = FakeEntitlementService(result=eff)
        self.app.dependency_overrides[v1_module._get_entitlement_service] = lambda: svc

        with patch.object(v1_module, "authenticate_request", return_value=identity):
            resp = self.client.get(
                "/v1/entitlements",
                headers={"x-request-id": "gw-abc", "authorization": "Bearer x"},
            )
            self.assertEqual(resp.status_code, 200)
            self.assertEqual(resp.headers.get("X-Request-Id"), "gw-abc")

    def test_entitlements_generates_x_request_id_when_missing(self):
        """Use case: response should always carry a request id even
        without gateway header.
        If this fails, observability and incident triage suffer."""
        identity = FakeIdentity(subject_id=7, account_name="Acme", provider="jwt")
        eff = FakeEffectiveEntitlements(
            userID=7,
            apiKeyID=77,
            accountName="Acme",
            subject_status="active",
            plan_id=1,
            tier="free",
            plan_status="active",
            allow_live=False,
            max_n=15,
            max_k=8,
            existential_only=False,
            rate_limit=10,
            rate_window=60,
        )
        svc = FakeEntitlementService(result=eff)
        self.app.dependency_overrides[v1_module._get_entitlement_service] = lambda: svc

        with (
            patch.object(v1_module, "uuid4", return_value="fixed-uuid"),
            patch.object(v1_module, "authenticate_request", return_value=identity),
        ):
            resp = self.client.get(
                "/v1/entitlements", headers={"authorization": "Bearer x"}
            )
            self.assertEqual(resp.status_code, 200)
            self.assertEqual(resp.headers.get("X-Request-Id"), "fixed-uuid")

    def test_entitlements_missing_auth_maps_to_401(self):
        """Use case: missing credentials must be unauthorized.
        If this fails, unauthenticated callers might get
        entitlements or incorrect HTTP semantics."""
        exc = make_exc(v1_module.MissingAuthenticationError, "missing auth")
        with patch.object(v1_module, "authenticate_request", side_effect=exc):
            resp = self.client.get("/v1/entitlements")
            self.assertEqual(resp.status_code, 401)
            self.assertEqual(resp.json()["detail"], "missing auth")

    def test_entitlements_invalid_auth_maps_to_401(self):
        """Use case: invalid credentials must be unauthorized.
        If this fails, callers may see 500s or you may leak internal auth details."""
        exc = make_exc(v1_module.InvalidAuthenticationError, "invalid auth")
        with patch.object(v1_module, "authenticate_request", side_effect=exc):
            resp = self.client.get(
                "/v1/entitlements", headers={"authorization": "Bearer bad"}
            )
            self.assertEqual(resp.status_code, 401)
            self.assertEqual(resp.json()["detail"], "invalid auth")

    def test_entitlements_generic_auth_error_maps_to_401(self):
        """Use case: catch-all auth errors should still result in 401.
        If this fails, the gateway may treat auth issues as infrastructure outages."""
        exc = make_exc(v1_module.AuthenticationError, "auth error")
        with patch.object(v1_module, "authenticate_request", side_effect=exc):
            resp = self.client.get(
                "/v1/entitlements", headers={"authorization": "Bearer x"}
            )
            self.assertEqual(resp.status_code, 401)
            self.assertEqual(resp.json()["detail"], "auth error")

    def test_entitlements_subject_not_found_maps_to_403(self):
        """Use case: authenticated identity without DB subject mapping is forbidden.
        If this fails, unknown subjects might be treated as
        outages or incorrectly allowed.
        """
        identity = FakeIdentity(subject_id=5, account_name="X", provider="jwt")
        svc = FakeEntitlementService(
            exc=make_exc(v1_module.SubjectNotFoundError, "no subject")
        )
        self.app.dependency_overrides[v1_module._get_entitlement_service] = lambda: svc

        with patch.object(v1_module, "authenticate_request", return_value=identity):
            resp = self.client.get(
                "/v1/entitlements", headers={"authorization": "Bearer x"}
            )
            self.assertEqual(resp.status_code, 403)
            self.assertIn("no subject", resp.json()["detail"])

    def test_entitlements_subject_inactive_maps_to_403(self):
        """Use case: disabled subjects must be forbidden even if authenticated.
        If this fails, suspended users may still receive entitlements."""
        identity = FakeIdentity(subject_id=6, account_name="X", provider="jwt")
        svc = FakeEntitlementService(
            exc=make_exc(v1_module.SubjectInactiveError, "inactive subject")
        )
        self.app.dependency_overrides[v1_module._get_entitlement_service] = lambda: svc

        with patch.object(v1_module, "authenticate_request", return_value=identity):
            resp = self.client.get(
                "/v1/entitlements", headers={"authorization": "Bearer x"}
            )
            self.assertEqual(resp.status_code, 403)
            self.assertIn("inactive subject", resp.json()["detail"])

    def test_entitlements_plan_inactive_maps_to_403(self):
        """Use case: plan shutdown should immediately
        prevent access for all subjects on it.
        If this fails, users may access features after plan disablement."""
        identity = FakeIdentity(subject_id=7, account_name="X", provider="jwt")

        # NOTE: assumes your v1.py catches PlanInactiveError (not InactivePlanError).
        svc = FakeEntitlementService(
            exc=make_exc(v1_module.PlanInactiveError, "inactive plan")
        )
        self.app.dependency_overrides[v1_module._get_entitlement_service] = lambda: svc

        with patch.object(v1_module, "authenticate_request", return_value=identity):
            resp = self.client.get(
                "/v1/entitlements", headers={"authorization": "Bearer x"}
            )
            self.assertEqual(resp.status_code, 403)
            self.assertIn("inactive plan", resp.json()["detail"])

    def test_entitlements_unexpected_error_maps_to_503_with_generic_detail(self):
        """Use case: DB outages should become 503 without leaking internals.
        If this fails, clients may see sensitive errors or
        get the wrong retry semantics.
        """
        identity = FakeIdentity(subject_id=8, account_name="X", provider="jwt")
        svc = FakeEntitlementService(exc=RuntimeError("db down"))
        self.app.dependency_overrides[v1_module._get_entitlement_service] = lambda: svc

        with patch.object(v1_module, "authenticate_request", return_value=identity):
            resp = self.client.get(
                "/v1/entitlements", headers={"authorization": "Bearer x"}
            )
            self.assertEqual(resp.status_code, 503)
            self.assertEqual(resp.json()["detail"], "Entitlements service unavailable")

    def test_entitlements_does_not_call_service_when_auth_fails(self):
        """Use case: avoid DB work when authentication fails (cost + attack surface).
        If this fails, unauthenticated calls could still
        hit your repo and waste resources.
        """
        svc = FakeEntitlementService(result=object())
        self.app.dependency_overrides[v1_module._get_entitlement_service] = lambda: svc

        exc = make_exc(v1_module.MissingAuthenticationError, "missing auth")
        with patch.object(v1_module, "authenticate_request", side_effect=exc):
            resp = self.client.get("/v1/entitlements")
            self.assertEqual(resp.status_code, 401)
            self.assertEqual(svc.calls, [])


class TestGetEntitlementServiceFactory(unittest.TestCase):
    def test_get_entitlement_service_constructs_repo_and_service_given_conn(self):
        """Use case: dependency factory must wire PlanRepo(conn)
        into EntitlementService(repo).
        If this fails, your endpoint may use a wrong repo or crash due to bad wiring."""
        fake_conn = object()
        fake_repo = object()
        fake_svc = object()

        with (
            patch.object(v1_module, "PlanRepo", return_value=fake_repo) as p_repo,
            patch.object(
                v1_module, "EntitlementService", return_value=fake_svc
            ) as p_svc,
        ):
            out = v1_module._get_entitlement_service(conn=fake_conn)

        self.assertIs(out, fake_svc)
        p_repo.assert_called_once_with(fake_conn)
        p_svc.assert_called_once_with(fake_repo)

    def test_entitlements_request_closes_connection_via_dependency_cleanup(self):
        """Use case: connections must close after each request to avoid leaks.
        If this fails, production traffic can eventually
        exhaust resources and cause timeouts.
        """
        app = build_app()
        client = TestClient(app)

        # Patch DB connection returned by get_connection
        mock_conn = MagicMock()
        with (
            patch.object(v1_module, "get_connection", return_value=mock_conn),
            patch.object(
                v1_module,
                "authenticate_request",
                return_value=FakeIdentity(1, "Acme", "jwt"),
            ),
        ):

            # Patch PlanRepo/EntitlementService used inside _get_entitlement_service
            eff = FakeEffectiveEntitlements(
                userID=1,
                apiKeyID=1,
                accountName="Acme",
                subject_status="active",
                plan_id=1,
                tier="free",
                plan_status="active",
                allow_live=False,
                max_n=15,
                max_k=8,
                existential_only=False,
                rate_limit=10,
                rate_window=60,
            )

            fake_svc = FakeEntitlementService(result=eff)

            with (
                patch.object(v1_module, "PlanRepo", return_value=object()),
                patch.object(v1_module, "EntitlementService", return_value=fake_svc),
            ):
                resp = client.get(
                    "/v1/entitlements", headers={"authorization": "Bearer x"}
                )
                self.assertEqual(resp.status_code, 200)

        # After request finishes, FastAPI should have
        # finalized get_conn() -> finally -> close
        mock_conn.close.assert_called_once()


if __name__ == "__main__":
    unittest.main(verbosity=2)
