# app/db/repo.py
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

import asyncpg


@dataclass(frozen=True)
class PlanWithLimits:
    plan_id: int
    tier: str
    status: str
    allow_live: bool
    description: Optional[str]
    created_at: str
    updated_at: str

    max_n: int
    max_k: int
    existential_only: bool
    rate_limit: int
    rate_window: int
    limits_updated_at: str


@dataclass(frozen=True)
class SubjectEffectiveEntitlementsRow:
    userID: str
    apiKey: str
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
    def __init__(self, conn: asyncpg.Connection) -> None:
        self._conn = conn

    async def get_planLimits(self, tier: str) -> Optional[PlanWithLimits]:
        sql = """
        SELECT
            p.id AS plan_id,
            p.tier,
            p.status,
            p.allow_live,
            p.description,
            p.created_at,
            p.updated_at,
            l.max_n,
            l.max_k,
            l.existential_only,
            l.rate_limit,
            l.rate_window,
            l.updated_at AS limits_updated_at
        FROM plans p
        JOIN plan_limits l ON l.plan_id = p.id
        WHERE p.tier = $1
        LIMIT 1
        """
        row = await self._conn.fetchrow(sql, tier)
        if row is None:
            return None

        return PlanWithLimits(
            plan_id=int(row["plan_id"]),
            tier=str(row["tier"]),
            status=str(row["status"]),
            allow_live=bool(row["allow_live"]),
            description=row["description"],
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
            max_n=int(row["max_n"]),
            max_k=int(row["max_k"]),
            existential_only=bool(row["existential_only"]),
            rate_limit=int(row["rate_limit"]),
            rate_window=int(row["rate_window"]),
            limits_updated_at=str(row["limits_updated_at"]),
        )

    async def get_planLimitsID(self, plan_id: int) -> Optional[PlanWithLimits]:
        sql = """
        SELECT
            p.id AS plan_id,
            p.tier,
            p.status,
            p.allow_live,
            p.description,
            p.created_at,
            p.updated_at,
            l.max_n,
            l.max_k,
            l.existential_only,
            l.rate_limit,
            l.rate_window,
            l.updated_at AS limits_updated_at
        FROM plans p
        JOIN plan_limits l ON l.plan_id = p.id
        WHERE p.id = $1
        LIMIT 1
        """
        row = await self._conn.fetchrow(sql, plan_id)
        if row is None:
            return None

        return PlanWithLimits(
            plan_id=int(row["plan_id"]),
            tier=str(row["tier"]),
            status=str(row["status"]),
            allow_live=bool(row["allow_live"]),
            description=row["description"],
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
            max_n=int(row["max_n"]),
            max_k=int(row["max_k"]),
            existential_only=bool(row["existential_only"]),
            rate_limit=int(row["rate_limit"]),
            rate_window=int(row["rate_window"]),
            limits_updated_at=str(row["limits_updated_at"]),
        )

    async def list_activeUsers(
        self, status: str
    ) -> List[SubjectEffectiveEntitlementsRow]:
        sql = """
        SELECT
          s."userID"      AS "userID",
          s."apiKey"      AS "apiKey",
          s."accountName" AS "accountName",
          s.status        AS subject_status,

          p.id            AS plan_id,
          p.tier          AS tier,
          p.status        AS plan_status,
          p.allow_live    AS allow_live,
          p.description   AS plan_description,

          COALESCE(spl.max_n, pl.max_n) AS max_n,
          COALESCE(spl.max_k, pl.max_k) AS max_k,
          COALESCE(spl.existential_only, pl.existential_only) AS existential_only,
          COALESCE(spl.rate_limit, pl.rate_limit) AS rate_limit,
          COALESCE(spl.rate_window, pl.rate_window) AS rate_window
        FROM subjects s
        JOIN subject_plan sp ON sp.subject_id = s."userID"
        JOIN plans p ON p.id = sp.plan_id
        JOIN plan_limits pl ON pl.plan_id = p.id
        LEFT JOIN subject_plan_limits spl ON spl.subject_id = s."userID"
        WHERE s.status = $1
        """
        rows = await self._conn.fetch(sql, status)

        out: List[SubjectEffectiveEntitlementsRow] = []
        for row in rows:
            out.append(
                SubjectEffectiveEntitlementsRow(
                    userID=str(row["userID"]),
                    apiKey=str(row["apiKey"]),
                    accountName=str(row["accountName"]),
                    subject_status=str(row["subject_status"]),
                    plan_id=int(row["plan_id"]),
                    tier=str(row["tier"]),
                    plan_status=str(row["plan_status"]),
                    allow_live=bool(row["allow_live"]),
                    plan_description=row["plan_description"],
                    max_n=int(row["max_n"]),
                    max_k=int(row["max_k"]),
                    existential_only=bool(row["existential_only"]),
                    rate_limit=int(row["rate_limit"]),
                    rate_window=int(row["rate_window"]),
                )
            )
        return out

    async def get_subject_effective_entitlements(
        self, user_id: str
    ) -> Optional[SubjectEffectiveEntitlementsRow]:
        sql = """
        SELECT
          s."userID"      AS "userID",
          s."apiKey"      AS "apiKey",
          s."accountName" AS "accountName",
          s.status        AS subject_status,

          p.id            AS plan_id,
          p.tier          AS tier,
          p.status        AS plan_status,
          p.allow_live    AS allow_live,
          p.description   AS plan_description,

          COALESCE(spl.max_n, pl.max_n) AS max_n,
          COALESCE(spl.max_k, pl.max_k) AS max_k,
          COALESCE(spl.existential_only, pl.existential_only) AS existential_only,
          COALESCE(spl.rate_limit, pl.rate_limit) AS rate_limit,
          COALESCE(spl.rate_window, pl.rate_window) AS rate_window
        FROM subjects s
        JOIN subject_plan sp ON sp.subject_id = s."userID"
        JOIN plans p ON p.id = sp.plan_id
        JOIN plan_limits pl ON pl.plan_id = p.id
        LEFT JOIN subject_plan_limits spl ON spl.subject_id = s."userID"
        WHERE s."userID" = $1
        LIMIT 1
        """
        row = await self._conn.fetchrow(sql, user_id)
        if row is None:
            return None

        return SubjectEffectiveEntitlementsRow(
            userID=str(row["userID"]),
            apiKey=str(row["apiKey"]),
            accountName=str(row["accountName"]),
            subject_status=str(row["subject_status"]),
            plan_id=int(row["plan_id"]),
            tier=str(row["tier"]),
            plan_status=str(row["plan_status"]),
            allow_live=bool(row["allow_live"]),
            plan_description=row["plan_description"],
            max_n=int(row["max_n"]),
            max_k=int(row["max_k"]),
            existential_only=bool(row["existential_only"]),
            rate_limit=int(row["rate_limit"]),
            rate_window=int(row["rate_window"]),
        )

    async def upsert_subject(
        self,
        *,
        user_id: str,
        api_key: str,
        account_name: str,
        status: str = "active",
    ) -> None:
        sql = """
        INSERT INTO subjects ("userID", "apiKey", "accountName", status)
        VALUES ($1, $2, $3, $4)
        ON CONFLICT ("userID") DO UPDATE SET
          "apiKey"      = EXCLUDED."apiKey",
          "accountName" = EXCLUDED."accountName",
          status        = EXCLUDED.status
        """
        await self._conn.execute(sql, user_id, api_key, account_name, status)

    async def ensure_subject_default_plan(
        self,
        *,
        user_id: str,
        default_tier: str = "free",
    ) -> None:
        plan_id = await self._conn.fetchval(
            "SELECT id FROM plans WHERE tier = $1 LIMIT 1",
            default_tier,
        )
        if plan_id is None:
            raise ValueError(f"Default plan tier not found: {default_tier}")

        sql = """
        INSERT INTO subject_plan (subject_id, plan_id)
        VALUES ($1, $2)
        ON CONFLICT (subject_id) DO NOTHING
        """
        await self._conn.execute(sql, user_id, int(plan_id))
