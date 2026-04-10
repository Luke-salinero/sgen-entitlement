import unittest
from dataclasses import dataclass
from typing import Any, Mapping, Optional

from app.core.entitlementService import (
    EffectiveEntitlements,
    EntitlementsError,
    EntitlementService,
    PlanInactiveError,
    SubjectInactiveError,
    SubjectNotFoundError,
)
from app.db.repo import SubjectEffectiveEntitlementsRow


class FakeRepo:
    def __init__(
        self,
        row: Optional[SubjectEffectiveEntitlementsRow] = None,
        *,
        exc: Exception | None = None,
    ) -> None:
        self._row = row
        self._exc = exc
        self.calls: list[str] = []

    # Match your real repo signature (string subject id)
    def get_subject_effective_entitlements(
        self, user_id: str
    ) -> Optional[SubjectEffectiveEntitlementsRow]:
        self.calls.append(user_id)
        if self._exc is not None:
            raise self._exc
        return self._row


def make_row(
    *,
    userID: str = "user-1",
    apiKey: str = "api-key-1",
    accountName: str = "Acme",
    subject_status: str = "active",
    plan_id: int = 10,
    tier: str = "free",
    plan_status: str = "active",
    allow_live: bool = False,
    plan_description: Optional[str] = None,
    max_n: int = 15,
    max_k: int = 8,
    existential_only: bool = False,
    rate_limit: int = 10,
    rate_window: int = 60,
) -> SubjectEffectiveEntitlementsRow:
    return SubjectEffectiveEntitlementsRow(
        userID=userID,
        apiKey=apiKey,
        accountName=accountName,
        subject_status=subject_status,
        plan_id=plan_id,
        tier=tier,
        plan_status=plan_status,
        allow_live=allow_live,
        plan_description=plan_description,
        max_n=max_n,
        max_k=max_k,
        existential_only=existential_only,
        rate_limit=rate_limit,
        rate_window=rate_window,
    )


class TestResolveUserId(unittest.TestCase):
    def setUp(self) -> None:
        self.svc = EntitlementService(FakeRepo())

    def test_prefers_userID_over_sub(self):
        claims = {"userID": "u-123", "sub": "u-999"}
        self.assertEqual(self.svc.resolve_user_id(claims), "u-123")

    def test_uses_sub_when_userID_missing(self):
        self.assertEqual(self.svc.resolve_user_id({"sub": "u-456"}), "u-456")

    def test_raises_when_missing_both(self):
        with self.assertRaises(EntitlementsError):
            self.svc.resolve_user_id({"aud": "x"})

    def test_coerces_to_str(self):
        # if upstream gives ints, we coerce to string safely
        self.assertEqual(self.svc.resolve_user_id({"userID": 42}), "42")


class TestHappyPath(unittest.TestCase):
    def test_get_entitlements_maps_fields(self):
        row = make_row(
            userID="u-7",
            apiKey="k-77",
            accountName="Example",
            subject_status="active",
            plan_id=2,
            tier="pro",
            plan_status="active",
            allow_live=True,
            plan_description="Pro plan",
            max_n=31,
            max_k=16,
            existential_only=True,
            rate_limit=99,
            rate_window=120,
        )
        repo = FakeRepo(row)
        svc = EntitlementService(repo)

        ent = svc.get_entitlements({"userID": "u-7"})

        self.assertIsInstance(ent, EffectiveEntitlements)
        self.assertEqual(repo.calls, ["u-7"])
        self.assertEqual(ent.userID, "u-7")
        self.assertEqual(ent.apiKey, "k-77")
        self.assertEqual(ent.accountName, "Example")
        self.assertEqual(ent.tier, "pro")
        self.assertIs(ent.allow_live, True)
        self.assertEqual(ent.plan_description, "Pro plan")


class TestFailureModes(unittest.TestCase):
    def test_subject_not_found(self):
        svc = EntitlementService(FakeRepo(row=None))
        with self.assertRaises(SubjectNotFoundError):
            svc.get_entitlements({"userID": "u-1"})

    def test_subject_inactive(self):
        row = make_row(subject_status="disabled")
        with self.assertRaises(SubjectInactiveError):
            EntitlementService(FakeRepo(row)).get_entitlements({"userID": row.userID})

    def test_plan_inactive(self):
        row = make_row(plan_status="disabled")
        with self.assertRaises(PlanInactiveError):
            EntitlementService(FakeRepo(row)).get_entitlements({"userID": row.userID})

    def test_repo_exception_propagates(self):
        svc = EntitlementService(FakeRepo(exc=RuntimeError("db down")))
        with self.assertRaises(RuntimeError):
            svc.get_entitlements({"userID": "u-1"})


class TestClaimWeirdness(unittest.TestCase):
    def test_claims_mapping_types_work(self):
        @dataclass
        class Claims(Mapping[str, Any]):
            data: dict[str, Any]

            def __getitem__(self, k: str) -> Any:
                return self.data[k]

            def __iter__(self):
                return iter(self.data)

            def __len__(self) -> int:
                return len(self.data)

        row = make_row(userID="1234")
        ent = EntitlementService(FakeRepo(row)).get_entitlements(
            Claims({"userID": 1234})
        )
        self.assertEqual(ent.userID, "1234")


if __name__ == "__main__":
    unittest.main(verbosity=2)
