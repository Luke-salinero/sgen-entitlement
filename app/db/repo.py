from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import List, Optional


@dataclass(frozen=True)
class PlanWithLimits:
    # plans.*
    plan_id: int
    tier: str
    status: str
    allow_live: bool
    description: Optional[str]
    created_at: str
    updated_at: str

    # plan_limits.*
    max_n: int
    max_k: int
    existential_only: bool
    rate_limit: int
    rate_window: int
    limits_updated_at: str


@dataclass(frozen=True)
class SubjectEffectiveEntitlementsRow:
    userID: str
    apiKeyID: int
    accountName: str
    subject_status: str

    plan_id: int
    tier: str
    plan_status: str
    allow_live: bool
    plan_description: Optional[str]

    max_n: int
    max_k: int
    existential_only: bool
    rate_limit: int
    rate_window: int


class PlanRepo:
    """
    Repository layer for reading/writing plan data.
    The rest of the app should call these methods instead of writing SQL.
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def get_planLimits(self, tier: str) -> Optional[PlanWithLimits]:
        """
        Returns the plan row joined with its limits row
        for the given tier.
        Returns None if the plan doesn't exist
        """
        sql = """
        SELECT
            p.id, p.tier, p.status, p.allow_live, p.description, p.created_at,
            p.updated_at,
            l.max_n, l.max_k, l.existential_only, l.rate_limit, l.rate_window,
            l.updated_at
        FROM plans p
        JOIN plan_limits l
            ON l.plan_id = p.id
        WHERE p.tier = ?
        LIMIT 1
        """
        cur = self._conn.execute(sql, (tier,))
        row = cur.fetchone()
        if row is None:
            return None

        (
            plan_id,
            tier,
            status,
            allow_live_int,
            description,
            created_at,
            updated_at,
            max_n,
            max_k,
            existential_only_int,
            rate_limit,
            rate_window,
            limits_updated_at,
        ) = row

        return PlanWithLimits(
            plan_id=plan_id,
            tier=tier,
            status=status,
            allow_live=bool(allow_live_int),
            description=description,
            created_at=created_at,
            updated_at=updated_at,
            max_n=max_n,
            max_k=max_k,
            existential_only=bool(existential_only_int),
            rate_limit=rate_limit,
            rate_window=rate_window,
            limits_updated_at=limits_updated_at,
        )

    def get_planLimitsID(self, plan_id: int) -> Optional[PlanWithLimits]:
        """
        Returns the plan row joined with its limits row
        for the given plan_id.
        Returns None if the plan doesn't exist
        """
        sql = """
        SELECT
            p.id, p.tier, p.status, p.allow_live, p.description, p.created_at, 
            p.updated_at,
            l.max_n, l.max_k, l.existential_only, l.rate_limit, l.rate_window, 
            l.updated_at
        FROM plans p
        JOIN plan_limits l
            ON l.plan_id = p.id
        WHERE p.id = ?
        LIMIT 1
        """
        cur = self._conn.execute(sql, (plan_id,))
        row = cur.fetchone()
        if row is None:
            return None

        (
            plan_id,
            tier,
            status,
            allow_live_int,
            description,
            created_at,
            updated_at,
            max_n,
            max_k,
            existential_only_int,
            rate_limit,
            rate_window,
            limits_updated_at,
        ) = row

        return PlanWithLimits(
            plan_id=plan_id,
            tier=tier,
            status=status,
            allow_live=bool(allow_live_int),
            description=description,
            created_at=created_at,
            updated_at=updated_at,
            max_n=max_n,
            max_k=max_k,
            existential_only=bool(existential_only_int),
            rate_limit=rate_limit,
            rate_window=rate_window,
            limits_updated_at=limits_updated_at,
        )

    def list_activeUsers(self, status: str) -> List[SubjectEffectiveEntitlementsRow]:
        """
        Returns all subjects (with the given subject status) joined to their
        effective entitlements (plan + limits, with subject overrides if present).
        Returns an empty list if none match.
        """
        sql = """
        SELECT
        s.userID,
        s.apiKeyID,
        s.accountName,
        s.status AS subject_status,

        p.id AS plan_id,
        p.tier,
        p.status AS plan_status,
        p.allow_live,
        p.description,

        COALESCE(spl.max_n, pl.max_n) AS max_n,
        COALESCE(spl.max_k, pl.max_k) AS max_k,
        COALESCE(spl.existential_only, pl.existential_only) AS existential_only,
        COALESCE(spl.rate_limit, pl.rate_limit) AS rate_limit,
        COALESCE(spl.rate_window, pl.rate_window) AS rate_window

        FROM subjects s
        JOIN subject_plan sp ON sp.subject_id = s.userID
        JOIN plans p ON p.id = sp.plan_id
        JOIN plan_limits pl ON pl.plan_id = p.id
        LEFT JOIN subject_plan_limits spl ON spl.subject_id = s.userID
        WHERE s.status = ?
        """
        cur = self._conn.execute(sql, (status,))
        rows = cur.fetchall()

        out: List[SubjectEffectiveEntitlementsRow] = []
        for row in rows:
            (
                userID,
                apiKeyID,
                accountName,
                subject_status,
                plan_id,
                tier,
                plan_status,
                allow_live_int,
                description,
                max_n,
                max_k,
                existential_only_int,
                rate_limit,
                rate_window,
            ) = row

            out.append(
                SubjectEffectiveEntitlementsRow(
                    userID=str(userID),
                    apiKeyID=int(apiKeyID),
                    accountName=str(accountName),
                    subject_status=str(subject_status),
                    plan_id=int(plan_id),
                    tier=str(tier),
                    plan_status=str(plan_status),
                    allow_live=bool(allow_live_int),
                    plan_description=description,
                    max_n=int(max_n),
                    max_k=int(max_k),
                    existential_only=bool(existential_only_int),
                    rate_limit=int(rate_limit),
                    rate_window=int(rate_window),
                )
            )

        return out

    def get_subject_effective_entitlements(
        self, user_id: int
    ) -> Optional[SubjectEffectiveEntitlementsRow]:
        sql = """
        SELECT
          s.userID,
          s.apiKeyID,
          s.accountName,
          s.status AS subject_status,

          p.id AS plan_id,
          p.tier,
          p.status AS plan_status,
          p.allow_live,
          p.description,

          COALESCE(spl.max_n, pl.max_n) AS max_n,
          COALESCE(spl.max_k, pl.max_k) AS max_k,
          COALESCE(spl.existential_only, pl.existential_only) AS existential_only,
          COALESCE(spl.rate_limit, pl.rate_limit) AS rate_limit,
          COALESCE(spl.rate_window, pl.rate_window) AS rate_window

        FROM subjects s
        JOIN subject_plan sp ON sp.subject_id = s.userID
        JOIN plans p ON p.id = sp.plan_id
        JOIN plan_limits pl ON pl.plan_id = p.id
        LEFT JOIN subject_plan_limits spl ON spl.subject_id = s.userID
        WHERE s.userID = ?
        LIMIT 1;
        """
        cur = self._conn.execute(sql, (user_id,))
        row = cur.fetchone()
        if row is None:
            return None

        (
            userID,
            apiKeyID,
            accountName,
            subject_status,
            plan_id,
            tier,
            plan_status,
            allow_live_int,
            description,
            max_n,
            max_k,
            existential_only_int,
            rate_limit,
            rate_window,
        ) = row

        return SubjectEffectiveEntitlementsRow(
            userID=str(userID),
            apiKeyID=int(apiKeyID),
            accountName=str(accountName),
            subject_status=str(subject_status),
            plan_id=int(plan_id),
            tier=str(tier),
            plan_status=str(plan_status),
            allow_live=bool(allow_live_int),
            plan_description=description,
            max_n=int(max_n),
            max_k=int(max_k),
            existential_only=bool(existential_only_int),
            rate_limit=int(rate_limit),
            rate_window=int(rate_window),
        )
