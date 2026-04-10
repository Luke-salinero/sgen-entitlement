import unittest
from dataclasses import dataclass
from typing import Any, Optional
from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.api.v1 as v1_module


@dataclass(frozen=True)
class FakeIdentity:
    subject_id: str
    account_name: str
    provider: str


@dataclass(frozen=True)
class FakeEffectiveEntitlements:
    userID: str
    apiKey: str
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


def build_app() -> FastAPI:
    app = FastAPI()
    app.include_router(v1_module.router)
    return app


class TestRequestIdHelpers(unittest.TestCase):
    def test_request_id_prefers_gateway_header(self):
        req = MagicMock()
        req.headers = {"x-request-id": "gw-123"}
        self.assertEqual(v1_module._request_id_from_headers(req), "gw-123")

    def test_request_id_falls_back_to_uuid(self):
        req = MagicMock()
        req.headers = {}
        with patch.object(v1_module, "uuid4", return_value="fixed-uuid"):
            self.assertEqual(v1_module._request_id_from_headers(req), "fixed-uuid")


class TestWhoAmIEndpoint(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(build_app())

    def test_whoami_success(self):
        identity = FakeIdentity(subject_id="u-1", account_name="Acme", provider="jwt")
        with patch.object(v1_module, "authenticate_request", return_value=identity):
            resp = self.client.get(
                "/v1/whoami",
                headers={"x-request-id": "gw-1", "authorization": "Bearer x"},
            )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.headers.get("X-Request-Id"), "gw-1")
        self.assertEqual(
            resp.json(),
            {"subject_id": "u-1", "account_name": "Acme", "provider": "jwt"},
        )

    def test_whoami_missing_auth_maps_to_401(self):
        exc = v1_module.MissingAuthenticationError("missing auth")
        if not hasattr(exc, "message"):
            exc.message = "missing auth"
        with patch.object(v1_module, "authenticate_request", side_effect=exc):
            resp = self.client.get("/v1/whoami")
        self.assertEqual(resp.status_code, 401)
        self.assertEqual(resp.json()["detail"], "missing auth")


class TestEntitlementsEndpoint(unittest.TestCase):
    def setUp(self) -> None:
        self.app = build_app()
        self.client = TestClient(self.app)

    def tearDown(self) -> None:
        self.app.dependency_overrides = {}

    def test_entitlements_happy_path_shape(self):
        identity = FakeIdentity(subject_id="u-42", account_name="Acme", provider="jwt")
        eff = FakeEffectiveEntitlements(
            userID="u-42",
            apiKey="k-123",
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

        # Override dependency factory: no DB involved in this unit test.
        self.app.dependency_overrides[v1_module._get_entitlement_service] = lambda: svc

        with patch.object(v1_module, "authenticate_request", return_value=identity):
            resp = self.client.get(
                "/v1/entitlements", headers={"authorization": "Bearer good"}
            )

        self.assertEqual(resp.status_code, 200)
        body = resp.json()

        self.assertEqual(body["subject_id"], "u-42")
        self.assertEqual(body["account_name"], "Acme")
        self.assertEqual(body["tier"], "pro")
        self.assertEqual(body["allow_live"], True)

        self.assertEqual(body["limits"]["max_n"], 31)
        self.assertEqual(body["limits"]["max_k"], 16)
        self.assertEqual(body["limits"]["existential_only"], True)
        self.assertEqual(body["limits"]["rate_limit"], 99)
        self.assertEqual(body["limits"]["rate_window"], 120)

        self.assertEqual(svc.calls, [{"claims": {"userID": "u-42"}}])

    def test_entitlements_sets_request_id(self):
        identity = FakeIdentity(subject_id="u-7", account_name="Acme", provider="jwt")
        eff = FakeEffectiveEntitlements(
            userID="u-7",
            apiKey="k-77",
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

    def test_entitlements_subject_not_found_maps_to_403(self):
        identity = FakeIdentity(subject_id="u-5", account_name="X", provider="jwt")
        exc = v1_module.SubjectNotFoundError("no subject")
        if not hasattr(exc, "message"):
            exc.message = "no subject"

        svc = FakeEntitlementService(exc=exc)
        self.app.dependency_overrides[v1_module._get_entitlement_service] = lambda: svc

        with patch.object(v1_module, "authenticate_request", return_value=identity):
            resp = self.client.get(
                "/v1/entitlements", headers={"authorization": "Bearer x"}
            )

        self.assertEqual(resp.status_code, 403)

    def test_entitlements_unexpected_error_maps_to_503(self):
        identity = FakeIdentity(subject_id="u-8", account_name="X", provider="jwt")
        svc = FakeEntitlementService(exc=RuntimeError("db down"))
        self.app.dependency_overrides[v1_module._get_entitlement_service] = lambda: svc

        with patch.object(v1_module, "authenticate_request", return_value=identity):
            resp = self.client.get(
                "/v1/entitlements", headers={"authorization": "Bearer x"}
            )

        self.assertEqual(resp.status_code, 503)
        self.assertEqual(resp.json()["detail"], "Entitlements service unavailable")


if __name__ == "__main__":
    unittest.main(verbosity=2)
