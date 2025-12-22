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
class UsersWithPlan:
    # subjects.*
    userID: int
    apiKeyID: int
    accountName: str
    status: str
    created_at: str

    # subject_plan.*
    plan_id: int


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

    def list_activeUsers(self, status: str) -> List[UsersWithPlan]:
        """
        Returns all subjects with their assigned plan_id
        for the given subject status
        Returns an empty list if none subjects
        """
        sql = """
        SELECT
            s.userID, s.apiKeyID, s.accountName, s.status, s.created_at,
            sp.plan_id
        FROM subjects s
        JOIN subject_plan sp
            ON sp.subject_id = s.userID
        WHERE s.status = ?
        """
        cur = self._conn.execute(sql, (status,))
        rows = cur.fetchall()

        return [
            UsersWithPlan(
                userID=userID,
                apiKeyID=apiKeyID,
                accountName=accountName,
                status=row_status,
                created_at=created_at,
                plan_id=plan_id,
            )
            for (userID, apiKeyID, accountName, row_status, created_at, plan_id) in rows
        ]
