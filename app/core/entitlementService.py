# app/core/entitlements/types.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Optional

from app.db import PlanRepo, SubjectEffectiveEntitlementsRow


# Should I split this up (into a different file) for clarity?
@dataclass(frozen=True)
class EffectiveEntitlements:
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


class EntitlementsError(Exception):
    pass


class SubjectNotFoundError(EntitlementsError):
    pass


class SubjectInactiveError(EntitlementsError):
    pass


class PlanInactiveError(EntitlementsError):
    pass


class EntitlementService:
    """
    Converts decoded JWT claims to EffectiveEntitlements.
    """

    def __init__(self, repo: PlanRepo) -> None:
        self._repo = repo

    def get_entitlements(self, claims: Mapping[str, Any]) -> EffectiveEntitlements:
        user_id = self.resolve_user_id(claims)

        row = self._repo.get_subject_effective_entitlements(user_id)
        if row is None:
            raise SubjectNotFoundError(f"No subject/plan found for userID={user_id}")

        if row.subject_status != "active":
            raise SubjectInactiveError(
                f"Subject userID={row.userID} not active (status={row.subject_status})"
            )

        if row.plan_status != "active":
            raise PlanInactiveError(
                f"Plan id={row.plan_id} not active (status={row.plan_status})"
            )

        return self.to_domain(row)

    def resolve_user_id(self, claims: Mapping[str, Any]) -> int:
        """
        Explicit userID claim.
        """
        if "userID" in claims:
            return str(claims["userID"])
        if "sub" in claims:
            return str(claims["sub"])
        raise EntitlementsError(
            "Claims missing user identifier (expected 'userID' or 'sub')."
        )

    def to_domain(self, row: SubjectEffectiveEntitlementsRow) -> EffectiveEntitlements:
        return EffectiveEntitlements(
            userID=row.userID,
            apiKey=row.apiKey,
            accountName=row.accountName,
            subject_status=row.subject_status,
            plan_id=row.plan_id,
            tier=row.tier,
            plan_status=row.plan_status,
            allow_live=row.allow_live,
            max_n=row.max_n,
            max_k=row.max_k,
            existential_only=row.existential_only,
            rate_limit=row.rate_limit,
            rate_window=row.rate_window,
            plan_description=row.plan_description,
        )
