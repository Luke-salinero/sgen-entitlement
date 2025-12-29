import unittest
from dataclasses import dataclass
from typing import Any, Mapping, Optional

# Adjust import path to wherever this code actually lives:
# from app.core.entitlements.types import (
#     EntitlementService,
#     EffectiveEntitlements,
#     EntitlementsError,
#     SubjectNotFoundError,
#     SubjectInactiveError,
#     PlanInactiveError,
# )
#
# And where these come from:
# from app.db.repo import SubjectEffectiveEntitlementsRow
#
# For this snippet, I'm importing from your shown module path:
from app.core import (
    EffectiveEntitlements,
    EntitlementsError,
    EntitlementService,
    PlanInactiveError,
    SubjectInactiveError,
    SubjectNotFoundError,
)
from app.db import SubjectEffectiveEntitlementsRow


class FakeRepo:
    """
    Minimal stub of PlanRepo used to isolate EntitlementService behavior.
    You can configure it to return a row, return None, or raise.
    """

    def __init__(
        self,
        row: Optional[SubjectEffectiveEntitlementsRow] = None,
        *,
        exc: Exception | None = None,
    ) -> None:
        self._row = row
        self._exc = exc
        self.calls: list[int] = []

    def get_subject_effective_entitlements(
        self, user_id: int
    ) -> Optional[SubjectEffectiveEntitlementsRow]:
        self.calls.append(user_id)
        if self._exc is not None:
            raise self._exc
        return self._row


def make_row(
    *,
    userID: int = 1,
    apiKeyID: int = 101,
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
        apiKeyID=apiKeyID,
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


class TestEntitlementServiceResolveUserId(unittest.TestCase):
    """
    Tests around claim parsing and identifier resolution.
    If these fail, valid users may be rejected or wrong users could be authorized.
    """

    def setUp(self) -> None:
        self.svc = EntitlementService(FakeRepo())

    def test_resolve_user_id_prefers_userID_over_sub(self):
        """
        Use case: JWT contains both userID and sub;
        service should consistently prefer userID.
        If this fails, you can authorize the wrong subject if sub and userID diverge.
        """
        claims = {"userID": 123, "sub": 999}
        self.assertEqual(self.svc.resolve_user_id(claims), 123)

    def test_resolve_user_id_uses_sub_when_userID_missing(self):
        """
        Use case: provider uses standard 'sub' claim instead of custom userID.
        If this fails, compatible JWTs will be rejected even though identity exists.
        """
        claims = {"sub": "456"}
        self.assertEqual(self.svc.resolve_user_id(claims), 456)

    def test_resolve_user_id_raises_when_missing_both(self):
        """
        Use case: claims missing identifiers should hard fail.
        If this fails, you'd silently authorize a request without a subject identity.
        """
        with self.assertRaises(EntitlementsError):
            self.svc.resolve_user_id({"aud": "x"})

    def test_resolve_user_id_casts_numeric_strings(self):
        """
        Use case: user id arrives as a string ("42") depending on JWT library/issuer.
        If this fails, legitimate tokens may crash or be rejected unexpectedly.
        """
        self.assertEqual(self.svc.resolve_user_id({"userID": "42"}), 42)

    def test_resolve_user_id_raises_on_non_int_cast(self):
        """
        Use case: malicious or malformed claims where identifier is not numeric.
        If this fails, you risk strange behavior or unintended user mapping.
        """
        with self.assertRaises(ValueError):
            self.svc.resolve_user_id({"userID": "not-a-number"})

    def test_resolve_user_id_bool_is_accepted_but_dangerous(self):
        """
        Use case: bool is an int subclass in Python; int(True)==1.
        If this fails, it highlights that claim types should be validated
        upstream to avoid userID=1 surprises.
        """
        # Current behavior: int(True) == 1
        self.assertEqual(self.svc.resolve_user_id({"userID": True}), 1)


class TestEntitlementServiceGetEntitlementsHappyPath(unittest.TestCase):
    """
    Tests around correct mapping and successful entitlements issuance.
    If these fail, your service could authorize incorrectly or drop important fields.
    """

    def test_get_entitlements_returns_domain_object_and_maps_all_fields(self):
        """
        Use case: active subject on active plan yields EffectiveEntitlements.
        If this fails, downstream code may enforce wrong limits or see missing metadata.
        """
        row = make_row(
            userID=7,
            apiKeyID=77,
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

        ent = svc.get_entitlements({"userID": 7})

        self.assertIsInstance(ent, EffectiveEntitlements)
        self.assertEqual(repo.calls, [7])

        # Field-by-field mapping assertions (nook & cranny correctness)
        self.assertEqual(ent.userID, 7)
        self.assertEqual(ent.apiKeyID, 77)
        self.assertEqual(ent.accountName, "Example")
        self.assertEqual(ent.subject_status, "active")

        self.assertEqual(ent.plan_id, 2)
        self.assertEqual(ent.tier, "pro")
        self.assertEqual(ent.plan_status, "active")
        self.assertIs(ent.allow_live, True)

        self.assertEqual(ent.max_n, 31)
        self.assertEqual(ent.max_k, 16)
        self.assertIs(ent.existential_only, True)
        self.assertEqual(ent.rate_limit, 99)
        self.assertEqual(ent.rate_window, 120)

        self.assertEqual(ent.plan_description, "Pro plan")

    def test_get_entitlements_accepts_sub_claim(self):
        """
        Use case: service supports standard JWT 'sub' claim.
        If this fails, tokens from common IdPs will be rejected.
        """
        row = make_row(userID=555)
        repo = FakeRepo(row)
        svc = EntitlementService(repo)

        ent = svc.get_entitlements({"sub": "555"})
        self.assertEqual(ent.userID, 555)
        self.assertEqual(repo.calls, [555])

    def test_plan_description_none_round_trips(self):
        """
        Use case: plan description is optional and may be NULL.
        If this fails, you may mis-handle optional plan metadata or crash on None.
        """
        row = make_row(plan_description=None)
        ent = EntitlementService(FakeRepo(row)).get_entitlements({"userID": row.userID})
        self.assertIsNone(ent.plan_description)


class TestEntitlementServiceFailureModes(unittest.TestCase):
    """
    Tests for all known failure conditions.
    If these fail, callers may get the wrong exception
    type or (worse) be authorized incorrectly.
    """

    def test_subject_not_found_raises_specific_error(self):
        """
        Use case: repo has no subject/plan mapping for the user.
        If this fails, you may return 500 instead of 404/401 style behavior.
        """
        svc = EntitlementService(FakeRepo(row=None))
        with self.assertRaises(SubjectNotFoundError):
            svc.get_entitlements({"userID": 1})

    def test_subject_inactive_raises(self):
        """
        Use case: disabled or suspended subject should not be authorized.
        If this fails, inactive users may still receive entitlements.
        """
        row = make_row(subject_status="disabled")
        svc = EntitlementService(FakeRepo(row))
        with self.assertRaises(SubjectInactiveError):
            svc.get_entitlements({"userID": row.userID})

    def test_subject_status_case_sensitivity_blocks_non_active(self):
        """
        Use case: DB might return 'Active' or 'ACTIVE' if data is inconsistent.
        If this fails, you can accidentally authorize users with non-standard statuses.
        """
        row = make_row(subject_status="ACTIVE")
        svc = EntitlementService(FakeRepo(row))
        with self.assertRaises(SubjectInactiveError):
            svc.get_entitlements({"userID": row.userID})

    def test_plan_inactive_raises(self):
        """
        Use case: plan is disabled; no users on it should be entitled.
        If this fails, you may grant access after a plan is turned off.
        """
        row = make_row(plan_status="disabled")
        svc = EntitlementService(FakeRepo(row))
        with self.assertRaises(PlanInactiveError):
            svc.get_entitlements({"userID": row.userID})

    def test_plan_status_case_sensitivity_blocks_non_active(self):
        """
        Use case: inconsistent plan statuses should still fail closed.
        If this fails, you may authorize plans that are not truly active.
        """
        row = make_row(plan_status="ACTIVE")
        svc = EntitlementService(FakeRepo(row))
        with self.assertRaises(PlanInactiveError):
            svc.get_entitlements({"userID": row.userID})

    def test_missing_identifier_claims_raises_entitlements_error(self):
        """
        Use case: token missing user identity should be rejected.
        If this fails, you risk granting entitlements without an identity anchor.
        """
        svc = EntitlementService(FakeRepo(make_row()))
        with self.assertRaises(EntitlementsError):
            svc.get_entitlements({"aud": "whatever"})

    def test_repo_exception_propagates_by_default(self):
        """
        Use case: DB layer error occurs; service currently does not wrap it.
        If this fails, callers may lose visibility into
        infra issues or get the wrong status mapping.
        """
        svc = EntitlementService(FakeRepo(exc=RuntimeError("db down")))
        with self.assertRaises(RuntimeError):
            svc.get_entitlements({"userID": 1})


class TestEntitlementServiceToDomain(unittest.TestCase):
    """
    Tests for the pure mapping layer (to_domain).
    If these fail, your domain object can silently drift from DB shape.
    """

    def test_to_domain_is_pure_and_does_not_mutate_input(self):
        """
        Use case: mapping should not mutate repo rows
        (dataclasses are frozen, but test intent matters).
        If this fails, mapping could have side effects and become hard to reason about.
        """
        row = make_row(userID=99, accountName="X", plan_description="desc")
        svc = EntitlementService(FakeRepo(row))

        ent = svc.to_domain(row)
        self.assertEqual(ent.userID, 99)
        self.assertEqual(ent.accountName, "X")
        self.assertEqual(ent.plan_description, "desc")

    def test_to_domain_handles_extreme_numeric_values(self):
        """
        Use case: large limits/rate limits shouldn't overflow or
        truncate in Python mapping.
        If this fails, a high-tier plan could be incorrectly limited.
        """
        row = make_row(
            max_n=2048,
            max_k=2048,
            rate_limit=10**9,
            rate_window=10**6,
        )
        ent = EntitlementService(FakeRepo(row)).to_domain(row)
        self.assertEqual(ent.max_n, 2048)
        self.assertEqual(ent.max_k, 2048)
        self.assertEqual(ent.rate_limit, 10**9)
        self.assertEqual(ent.rate_window, 10**6)


class TestEntitlementServiceClaimNastiness(unittest.TestCase):
    """
    Niche claim-shape tests.
    If these fail, your service may be vulnerable to weird token decoding edge cases.
    """

    def test_claims_mapping_types_work(self):
        """
        Use case: claims may be any Mapping (not necessarily dict).
        If this fails, you could break compatibility with some JWT libraries.
        """

        @dataclass
        class Claims(Mapping[str, Any]):
            data: dict[str, Any]

            def __getitem__(self, k: str) -> Any:
                return self.data[k]

            def __iter__(self):
                return iter(self.data)

            def __len__(self) -> int:
                return len(self.data)

        row = make_row(userID=1234)
        svc = EntitlementService(FakeRepo(row))
        ent = svc.get_entitlements(Claims({"userID": "1234"}))
        self.assertEqual(ent.userID, 1234)

    def test_claims_sub_with_whitespace_is_accepted_by_int(self):
        row = make_row(userID=1)
        svc = EntitlementService(FakeRepo(row))
        ent = svc.get_entitlements({"sub": " 1 "})
        self.assertEqual(ent.userID, 1)

    def test_claims_userID_float_is_coerced_by_int(self):
        """
        Use case: claim value could be float (bad issuer); int(1.9)==1 truncates.
        If this fails, it flags that strict upstream validation
        is needed to prevent truncation-based confusion.
        """
        row = make_row(userID=1)
        svc = EntitlementService(FakeRepo(row))
        ent = svc.get_entitlements({"userID": 1.9})
        self.assertEqual(ent.userID, 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
