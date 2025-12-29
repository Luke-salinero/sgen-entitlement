"""
unittest-based unit tests (no pytest) for:
- repo.py (PlanRepo)
- connection.py (get_connection)
- schema constraints (high-value integrity tests)

Adjust the imports at the top to match your project structure.
"""

import random
import sqlite3
import string
import tempfile
import time
import unittest
from pathlib import Path

import app.db.connection as connection_module
from app.db.connection import get_connection
from app.db.repo import PlanRepo

SCHEMA_SQL = """
-- Defines available subscription plans and their high-level access flags.
CREATE TABLE plans(
    id          INTEGER PRIMARY KEY,
    tier        TEXT NOT NULL UNIQUE,
    status      TEXT NOT NULL,
    allow_live  INTEGER NOT NULL,
    description TEXT,
    created_at  TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at  TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (allow_live IN (0, 1)),
    -- If your real schema differs, update this list accordingly.
    CHECK (tier in ('free', 'pro', 'custom'))
);

-- Defines enforceable limits and constraints for each plan (1:1 with plans).
CREATE TABLE plan_limits(
    plan_id     INTEGER NOT NULL UNIQUE,
    max_n       INTEGER NOT NULL,
    max_k       INTEGER NOT NULL,
    existential_only INTEGER NOT NULL,
    rate_limit  INTEGER NOT NULL,
    rate_window INTEGER NOT NULL,
    updated_at  TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (existential_only in (0,1)),
    CHECK (max_n >= 1),
    CHECK (max_n <= 2048),
    CHECK (max_k <= max_n),
    CHECK (max_k >= 1),
    CHECK (rate_limit >=1),
    CHECK (rate_window >=1),

    FOREIGN KEY (plan_id) REFERENCES plans(id) ON DELETE CASCADE
);

CREATE TABLE subjects(
    userID      INTEGER PRIMARY KEY,
    apiKeyID    INTEGER NOT NULL UNIQUE,
    accountName TEXT NOT NULL,
    status      TEXT NOT NULL,
    created_at  TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE subject_plan(
    subject_id  INTEGER PRIMARY KEY,
    plan_id     INTEGER NOT NULL,

    FOREIGN KEY (subject_id) REFERENCES subjects(userID) on DELETE CASCADE,
    FOREIGN KEY (plan_id) REFERENCES plans(id) on DELETE RESTRICT
);

-- NEW: Subject-specific override limits (nullable columns allowed).
-- Required by PlanRepo.list_activeUsers() and get_subject_effective_entitlements().
CREATE TABLE subject_plan_limits(
    subject_id INTEGER PRIMARY KEY,
    max_n INTEGER,
    max_k INTEGER,
    existential_only INTEGER,
    rate_limit INTEGER,
    rate_window INTEGER,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CHECK (existential_only IS NULL OR existential_only IN (0,1)),
    CHECK (max_n IS NULL OR (max_n >= 1 AND max_n <= 2048)),
    CHECK (max_k IS NULL OR (max_k >= 1)),
    CHECK ((max_k IS NULL) OR (max_n IS NULL) OR (max_k <= max_n)),
    CHECK (rate_limit IS NULL OR rate_limit >= 1),
    CHECK (rate_window IS NULL OR rate_window >= 1),

    FOREIGN KEY (subject_id) REFERENCES subjects(userID) ON DELETE CASCADE
);
"""


def make_in_memory_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.executescript(SCHEMA_SQL)
    return conn


def insert_plan_with_limits(
    conn: sqlite3.Connection,
    *,
    tier: str = "free",
    status: str = "active",
    allow_live: int = 0,
    description=None,
    max_n: int = 15,
    max_k: int = 8,
    existential_only: int = 0,
    rate_limit: int = 10,
    rate_window: int = 60,
) -> int:
    cur = conn.execute(
        """
        INSERT INTO plans(tier, status, allow_live, description)
        VALUES (?, ?, ?, ?)
        """,
        (tier, status, allow_live, description),
    )
    plan_id = int(cur.lastrowid)

    conn.execute(
        """
        INSERT INTO plan_limits(plan_id, max_n, max_k, existential_only, 
        rate_limit, rate_window)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (plan_id, max_n, max_k, existential_only, rate_limit, rate_window),
    )
    conn.commit()
    return plan_id


def insert_subject(
    conn: sqlite3.Connection,
    *,
    apiKeyID: int,
    accountName: str,
    status: str,
) -> int:
    cur = conn.execute(
        """
        INSERT INTO subjects(apiKeyID, accountName, status)
        VALUES (?, ?, ?)
        """,
        (apiKeyID, accountName, status),
    )
    user_id = int(cur.lastrowid)
    conn.commit()
    return user_id


def assign_subject_plan(
    conn: sqlite3.Connection, *, subject_id: int, plan_id: int
) -> None:
    conn.execute(
        "INSERT INTO subject_plan(subject_id, plan_id) VALUES (?, ?)",
        (subject_id, plan_id),
    )
    conn.commit()


def insert_subject_plan_limits(
    conn: sqlite3.Connection,
    *,
    subject_id: int,
    max_n: int | None = None,
    max_k: int | None = None,
    existential_only: int | None = None,
    rate_limit: int | None = None,
    rate_window: int | None = None,
) -> None:
    conn.execute(
        """
        INSERT INTO subject_plan_limits
        (subject_id, max_n, max_k, existential_only, rate_limit, rate_window)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (subject_id, max_n, max_k, existential_only, rate_limit, rate_window),
    )
    conn.commit()


def rand_str(rng: random.Random, n: int) -> str:
    alphabet = (
        string.ascii_letters + string.digits + " _-./\\'\";:()[]{}!@#$%^&*+=|?,<>~"
    )
    return "".join(rng.choice(alphabet) for _ in range(n))


def nasty_strings() -> list[str]:
    return [
        "",
        " ",
        "   ",
        "free",
        "pro",
        "FREE",
        "Pro",
        "free' OR 1=1 --",
        "'; DROP TABLE plans; --",
        "free; SELECT * FROM plans;",
        "free\0pro",
        "💥",
        "测试",
        "привет",
        "áéíóú",
        "x" * 10,
        "x" * 100,
        "x" * 10_000,
        "\n\t\r",
    ]


class TestPlanRepoGetPlanLimits(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = make_in_memory_conn()
        self.repo = PlanRepo(self.conn)

    def tearDown(self) -> None:
        self.conn.close()

    def test_get_planLimits_returns_plan_with_limits_for_valid_tier(self):
        plan_id = insert_plan_with_limits(
            self.conn, tier="free", allow_live=0, existential_only=0
        )
        res = self.repo.get_planLimits("free")
        self.assertIsNotNone(res)
        assert res is not None

        self.assertEqual(res.plan_id, plan_id)
        self.assertEqual(res.tier, "free")
        self.assertIs(res.allow_live, False)
        self.assertIs(res.existential_only, False)

        self.assertGreaterEqual(res.max_n, 1)
        self.assertGreaterEqual(res.max_k, 1)
        self.assertIsInstance(res.created_at, str)
        self.assertIsInstance(res.updated_at, str)
        self.assertIsInstance(res.limits_updated_at, str)

    def test_get_planLimits_returns_none_for_unknown_tier(self):
        insert_plan_with_limits(self.conn, tier="free")
        self.assertIsNone(self.repo.get_planLimits("does-not-exist"))

    def test_get_planLimits_returns_none_when_plan_exists_but_limits_missing(self):
        self.conn.execute(
            "INSERT INTO plans(tier, status, allow_live, description) VALUES (?,?,?,?)",
            ("free", "active", 0, None),
        )
        self.conn.commit()
        self.assertIsNone(self.repo.get_planLimits("free"))

    def test_get_planLimits_bool_casting_for_allow_live_and_existential_only(self):
        insert_plan_with_limits(
            self.conn, tier="free", allow_live=1, existential_only=1
        )
        res = self.repo.get_planLimits("free")
        self.assertIsNotNone(res)
        assert res is not None
        self.assertIs(res.allow_live, True)
        self.assertIs(res.existential_only, True)

    def test_get_planLimits_handles_nullable_description(self):
        insert_plan_with_limits(self.conn, tier="free", description=None)
        res = self.repo.get_planLimits("free")
        self.assertIsNotNone(res)
        assert res is not None
        self.assertIsNone(res.description)

    def test_get_planLimits_rejects_sql_injection_like_input(self):
        insert_plan_with_limits(self.conn, tier="free")
        self.assertIsNone(self.repo.get_planLimits("free' OR 1=1 --"))


class TestPlanRepoGetPlanLimitsID(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = make_in_memory_conn()
        self.repo = PlanRepo(self.conn)

    def tearDown(self) -> None:
        self.conn.close()

    def test_get_planLimitsID_returns_plan_with_limits_for_valid_id(self):
        plan_id = insert_plan_with_limits(
            self.conn, tier="free", allow_live=1, existential_only=0
        )
        res = self.repo.get_planLimitsID(plan_id)
        self.assertIsNotNone(res)
        assert res is not None

        self.assertEqual(res.plan_id, plan_id)
        self.assertEqual(res.tier, "free")
        self.assertIs(res.allow_live, True)
        self.assertIs(res.existential_only, False)

    def test_get_planLimitsID_returns_none_for_unknown_id(self):
        insert_plan_with_limits(self.conn, tier="free")
        self.assertIsNone(self.repo.get_planLimitsID(999999))

    def test_get_planLimitsID_returns_none_when_limits_missing(self):
        cur = self.conn.execute(
            "INSERT INTO plans(tier, status, allow_live, description) VALUES (?,?,?,?)",
            ("free", "active", 0, None),
        )
        self.conn.commit()
        plan_id = int(cur.lastrowid)
        self.assertIsNone(self.repo.get_planLimitsID(plan_id))

    def test_get_planLimitsID_returns_none_for_non_int_param(self):
        plan_id = insert_plan_with_limits(self.conn, tier="free")
        self.assertIsNotNone(self.repo.get_planLimitsID(plan_id))

        res = self.repo.get_planLimitsID("not-an-int")  # type: ignore[arg-type]
        self.assertIsNone(res)


class TestPlanRepoListActiveUsers(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = make_in_memory_conn()
        self.repo = PlanRepo(self.conn)

    def tearDown(self) -> None:
        self.conn.close()

    def test_list_activeUsers_returns_users_for_matching_status(self):
        plan_id = insert_plan_with_limits(self.conn, tier="free", status="active")
        u1 = insert_subject(
            self.conn, apiKeyID=101, accountName="Acme", status="active"
        )
        u2 = insert_subject(
            self.conn, apiKeyID=102, accountName="Beta", status="active"
        )
        u3 = insert_subject(
            self.conn, apiKeyID=103, accountName="Gamma", status="disabled"
        )

        assign_subject_plan(self.conn, subject_id=u1, plan_id=plan_id)
        assign_subject_plan(self.conn, subject_id=u2, plan_id=plan_id)
        assign_subject_plan(self.conn, subject_id=u3, plan_id=plan_id)

        res = self.repo.list_activeUsers("active")
        self.assertEqual(len(res), 2)

        user_ids = {r.userID for r in res}
        self.assertSetEqual(user_ids, {u1, u2})

        for r in res:
            self.assertEqual(r.subject_status, "active")
            self.assertEqual(r.plan_id, plan_id)
            self.assertEqual(r.plan_status, "active")
            self.assertEqual(r.tier, "free")

    def test_list_activeUsers_uses_subject_plan_limits_overrides_when_present(self):
        # Base plan limits
        plan_id = insert_plan_with_limits(
            self.conn,
            tier="free",
            max_n=15,
            max_k=8,
            existential_only=0,
            rate_limit=10,
            rate_window=60,
        )

        uid = insert_subject(
            self.conn, apiKeyID=2001, accountName="OverrideUser", status="active"
        )
        assign_subject_plan(self.conn, subject_id=uid, plan_id=plan_id)

        # Override only some fields; others should fall back to plan limits via COALESCE
        insert_subject_plan_limits(
            self.conn,
            subject_id=uid,
            max_n=99,
            max_k=7,
            existential_only=1,
            rate_limit=None,
            rate_window=None,
        )

        res = self.repo.list_activeUsers("active")
        self.assertEqual(len(res), 1)
        row = res[0]

        self.assertEqual(row.userID, uid)
        self.assertEqual(row.max_n, 99)  # overridden
        self.assertEqual(row.max_k, 7)  # overridden
        self.assertIs(row.existential_only, True)  # overridden (1 -> True)
        self.assertEqual(row.rate_limit, 10)  # fallback
        self.assertEqual(row.rate_window, 60)  # fallback

    def test_list_activeUsers_returns_empty_list_when_none_match(self):
        plan_id = insert_plan_with_limits(self.conn, tier="free")
        u1 = insert_subject(
            self.conn, apiKeyID=201, accountName="Acme", status="disabled"
        )
        assign_subject_plan(self.conn, subject_id=u1, plan_id=plan_id)

        res = self.repo.list_activeUsers("active")
        self.assertEqual(res, [])

    def test_list_activeUsers_excludes_subjects_without_subject_plan(self):
        insert_plan_with_limits(self.conn, tier="free")
        _u1 = insert_subject(
            self.conn, apiKeyID=301, accountName="NoPlan", status="active"
        )
        res = self.repo.list_activeUsers("active")
        self.assertEqual(res, [])

    def test_list_activeUsers_rejects_sql_injection_like_input(self):
        plan_id = insert_plan_with_limits(self.conn, tier="free")
        u1 = insert_subject(self.conn, apiKeyID=501, accountName="A", status="active")
        assign_subject_plan(self.conn, subject_id=u1, plan_id=plan_id)

        res = self.repo.list_activeUsers("active' OR 1=1 --")
        self.assertEqual(res, [])


class TestPlanRepoGetSubjectEffectiveEntitlements(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = make_in_memory_conn()
        self.repo = PlanRepo(self.conn)

    def tearDown(self) -> None:
        self.conn.close()

    def test_get_subject_effective_entitlements_returns_none_when_missing(self):
        insert_plan_with_limits(self.conn, tier="free")
        self.assertIsNone(self.repo.get_subject_effective_entitlements(999999))

    def test_get_subject_effective_entitlements_returns_row_with_fallback_limits(self):
        plan_id = insert_plan_with_limits(
            self.conn,
            tier="free",
            max_n=15,
            max_k=8,
            existential_only=0,
            rate_limit=10,
            rate_window=60,
        )
        uid = insert_subject(
            self.conn, apiKeyID=9001, accountName="Acme", status="active"
        )
        assign_subject_plan(self.conn, subject_id=uid, plan_id=plan_id)

        row = self.repo.get_subject_effective_entitlements(uid)
        self.assertIsNotNone(row)
        assert row is not None

        self.assertEqual(row.userID, uid)
        self.assertEqual(row.subject_status, "active")
        self.assertEqual(row.plan_id, plan_id)
        self.assertEqual(row.tier, "free")
        self.assertEqual(row.max_n, 15)
        self.assertEqual(row.max_k, 8)
        self.assertIs(row.existential_only, False)

    def test_get_subject_effective_entitlements_uses_subject_overrides(self):
        plan_id = insert_plan_with_limits(
            self.conn,
            tier="free",
            max_n=15,
            max_k=8,
            existential_only=0,
            rate_limit=10,
            rate_window=60,
        )
        uid = insert_subject(
            self.conn, apiKeyID=9002, accountName="Override", status="active"
        )
        assign_subject_plan(self.conn, subject_id=uid, plan_id=plan_id)
        insert_subject_plan_limits(
            self.conn, subject_id=uid, max_n=123, existential_only=1
        )

        row = self.repo.get_subject_effective_entitlements(uid)
        self.assertIsNotNone(row)
        assert row is not None

        self.assertEqual(row.max_n, 123)  # overridden
        self.assertIs(row.existential_only, True)  # overridden
        self.assertEqual(row.max_k, 8)  # fallback
        self.assertEqual(row.rate_limit, 10)  # fallback
        self.assertEqual(row.rate_window, 60)  # fallback


class TestConnectionGetConnection(unittest.TestCase):
    def test_get_connection_creates_parent_directory_if_missing(self):
        old_db_path = connection_module.DB_PATH
        try:
            with tempfile.TemporaryDirectory() as tmp:
                tmp_dir = Path(tmp)
                custom_db_path = tmp_dir / "runtime" / "entitlements.db"
                connection_module.DB_PATH = custom_db_path

                self.assertFalse(custom_db_path.parent.exists())
                conn = get_connection()
                try:
                    self.assertTrue(custom_db_path.parent.exists())
                    conn.execute("SELECT 1;").fetchone()
                finally:
                    conn.close()
        finally:
            connection_module.DB_PATH = old_db_path

    def test_get_connection_enables_foreign_keys(self):
        old_db_path = connection_module.DB_PATH
        try:
            with tempfile.TemporaryDirectory() as tmp:
                connection_module.DB_PATH = Path(tmp) / "entitlements.db"
                conn = get_connection()
                try:
                    fk = conn.execute("PRAGMA foreign_keys;").fetchone()[0]
                    self.assertEqual(fk, 1)
                finally:
                    conn.close()
        finally:
            connection_module.DB_PATH = old_db_path

    def test_get_connection_sets_busy_timeout(self):
        old_db_path = connection_module.DB_PATH
        try:
            with tempfile.TemporaryDirectory() as tmp:
                connection_module.DB_PATH = Path(tmp) / "entitlements.db"
                conn = get_connection()
                try:
                    timeout = conn.execute("PRAGMA busy_timeout;").fetchone()[0]
                    self.assertEqual(timeout, 5000)
                finally:
                    conn.close()
        finally:
            connection_module.DB_PATH = old_db_path

    def test_get_connection_creates_db_file_on_disk(self):
        old_db_path = connection_module.DB_PATH
        try:
            with tempfile.TemporaryDirectory() as tmp:
                db_path = Path(tmp) / "entitlements.db"
                connection_module.DB_PATH = db_path
                self.assertFalse(db_path.exists())
                conn = get_connection()
                conn.close()
                self.assertTrue(db_path.exists())
        finally:
            connection_module.DB_PATH = old_db_path


class TestSchemaConstraints(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = make_in_memory_conn()

    def tearDown(self) -> None:
        self.conn.close()

    def test_schema_rejects_invalid_allow_live_values(self):
        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute(
                """INSERT"" INTO plans(tier,status,allow_live,description) 
                VALUES (?,?,?,?)""",
                ("free", "active", 2, None),
            )
            self.conn.commit()

    def test_schema_enforces_plan_limits_constraints_max_k_le_max_n(self):
        plan_id = insert_plan_with_limits(self.conn, tier="free")
        self.conn.execute("DELETE FROM plan_limits WHERE plan_id = ?", (plan_id,))
        self.conn.commit()

        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute(
                """
                INSERT INTO plan_limits(plan_id, max_n, max_k, existential_only, 
                rate_limit, rate_window)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (plan_id, 10, 11, 0, 10, 60),
            )
            self.conn.commit()

    def test_schema_cascades_delete_plan_to_plan_limits(self):
        plan_id = insert_plan_with_limits(self.conn, tier="free")
        before = self.conn.execute(
            "SELECT COUNT(*) FROM plan_limits WHERE plan_id = ?", (plan_id,)
        ).fetchone()[0]
        self.assertEqual(before, 1)

        self.conn.execute("DELETE FROM plans WHERE id = ?", (plan_id,))
        self.conn.commit()

        after = self.conn.execute(
            "SELECT COUNT(*) FROM plan_limits WHERE plan_id = ?", (plan_id,)
        ).fetchone()[0]
        self.assertEqual(after, 0)

    def test_schema_restricts_deleting_plan_if_referenced_by_subject_plan(self):
        plan_id = insert_plan_with_limits(self.conn, tier="free")
        user_id = insert_subject(
            self.conn, apiKeyID=9001, accountName="Acme", status="active"
        )
        assign_subject_plan(self.conn, subject_id=user_id, plan_id=plan_id)

        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute("DELETE FROM plans WHERE id = ?", (plan_id,))
            self.conn.commit()

    def test_subject_plan_limits_cascades_on_subject_delete(self):
        plan_id = insert_plan_with_limits(self.conn, tier="free")
        uid = insert_subject(self.conn, apiKeyID=5555, accountName="X", status="active")
        assign_subject_plan(self.conn, subject_id=uid, plan_id=plan_id)
        insert_subject_plan_limits(self.conn, subject_id=uid, max_n=99)

        before = self.conn.execute(
            "SELECT COUNT(*) FROM subject_plan_limits WHERE subject_id = ?", (uid,)
        ).fetchone()[0]
        self.assertEqual(before, 1)

        self.conn.execute("DELETE FROM subjects WHERE userID = ?", (uid,))
        self.conn.commit()

        after = self.conn.execute(
            "SELECT COUNT(*) FROM subject_plan_limits WHERE subject_id = ?", (uid,)
        ).fetchone()[0]
        self.assertEqual(after, 0)


class TestPlanRepoDatabaseStateFailures(unittest.TestCase):
    def test_methods_fail_cleanly_when_connection_closed(self):
        conn = make_in_memory_conn()
        repo = PlanRepo(conn)
        insert_plan_with_limits(conn, tier="free")
        conn.close()

        with self.assertRaises(sqlite3.ProgrammingError):
            repo.get_planLimits("free")

        with self.assertRaises(sqlite3.ProgrammingError):
            repo.get_planLimitsID(1)

        with self.assertRaises(sqlite3.ProgrammingError):
            repo.list_activeUsers("active")

        with self.assertRaises(sqlite3.ProgrammingError):
            repo.get_subject_effective_entitlements(1)


class TestSQLiteLockingBehavior(unittest.TestCase):
    def test_database_locked_can_happen_during_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "locktest.db"

            conn1 = sqlite3.connect(db_path)
            conn1.execute("PRAGMA foreign_keys = ON;")
            conn1.executescript(SCHEMA_SQL)
            conn1.execute(
                """INSERT INTO plans(tier,status,allow_live,description) 
                VALUES ('free','active',0,NULL)"""
            )
            conn1.commit()

            conn1.execute("BEGIN IMMEDIATE;")
            conn1.execute("UPDATE plans SET status='active' WHERE tier='free'")

            conn2 = sqlite3.connect(db_path)
            conn2.execute("PRAGMA busy_timeout = 100;")
            try:
                with self.assertRaises(sqlite3.OperationalError):
                    conn2.execute(
                        """INSERT INTO plans(tier,status,allow_live,description) 
                        VALUES ('pro','active',0,NULL)"""
                    )
                    conn2.commit()
            finally:
                conn2.close()
                conn1.rollback()
                conn1.close()


# ============================
# BULK / STRESS TESTS
# Paste below your existing tests
# ============================


BULK_SUBJECTS = 3000
BULK_OVERRIDES = 900
BULK_PLANS = 3
BULK_PERF_SECONDS = 2.5
BULK_ACTIVE_RATIO = 0.9


class TestBulkEffectiveEntitlementsConsistency(unittest.TestCase):
    """
    High-volume consistency tests:
    - create multiple plans
    - create thousands of subjects assigned to plans
    - apply randomized subject_plan_limits overrides (partial overrides!)
    - verify list_activeUsers('active') rows match
    get_subject_effective_entitlements(userID)
    """

    def setUp(self) -> None:
        self.conn = make_in_memory_conn()
        self.repo = PlanRepo(self.conn)
        self.rng = random.Random(20250101)

        # Create multiple plans with distinct limits so we can verify
        # fallback vs override.
        self.plan_ids: list[int] = []
        for i in range(BULK_PLANS):
            tier = f"tier_{i}"
            # NOTE: if your schema CHECK(tier in (...)) doesn't allow tier_*,
            # set BULK_PLANS=2 and use tiers ('free','pro') or update schema constraint.
            # For safety in many schemas, we stick to 'free','pro','custom'
            # if BULK_PLANS<=3.
            if BULK_PLANS <= 3:
                tier = ["free", "pro", "custom"][i]
            pid = insert_plan_with_limits(
                self.conn,
                tier=tier,
                status="active",
                allow_live=(i % 2),
                max_n=15 + i,
                max_k=8,
                existential_only=(i % 2),
                rate_limit=10 + i,
                rate_window=60,
            )
            self.plan_ids.append(pid)

        self.subject_ids: list[int] = []
        self.active_subject_ids: list[int] = []

        n_subjects = BULK_SUBJECTS
        n_active = int(n_subjects * BULK_ACTIVE_RATIO)

        # Insert subjects
        for i in range(n_subjects):
            status = "active" if i < n_active else "disabled"
            uid = insert_subject(
                self.conn,
                apiKeyID=100_000 + i,
                accountName=f"acct_{i}",
                status=status,
            )
            self.subject_ids.append(uid)
            if status == "active":
                self.active_subject_ids.append(uid)

            # Assign to a plan (skewed distribution is fine)
            pid = self.plan_ids[i % len(self.plan_ids)]
            assign_subject_plan(self.conn, subject_id=uid, plan_id=pid)

        # Apply overrides to a subset of subjects (random pick)
        override_subjects = self.rng.sample(
            self.subject_ids, k=min(BULK_OVERRIDES, len(self.subject_ids))
        )
        for uid in override_subjects:
            # Partial overrides: some fields None to test COALESCE fallback.
            # Also keep overrides valid (respect max_k<=max_n when both set).
            max_n = self.rng.choice([None, 31, 63, 127, 255])
            if max_n is None:
                max_k = self.rng.choice([None, 1, 2, 4, 8])
            else:
                max_k = self.rng.choice([None, 1, min(8, max_n), min(16, max_n)])
            existential_only = self.rng.choice([None, 0, 1])
            rate_limit = self.rng.choice([None, 5, 10, 20, 50])
            rate_window = self.rng.choice([None, 60, 120, 300])

            # Ensure if both max_n and max_k set, max_k <= max_n
            if max_n is not None and max_k is not None and max_k > max_n:
                max_k = max_n

            insert_subject_plan_limits(
                self.conn,
                subject_id=uid,
                max_n=max_n,
                max_k=max_k,
                existential_only=existential_only,
                rate_limit=rate_limit,
                rate_window=rate_window,
            )

    def tearDown(self) -> None:
        self.conn.close()

    def test_list_activeUsers_matches_get_subject_effective_entitlements_for_all_active(
        self,
    ):
        t0 = time.time()
        rows = self.repo.list_activeUsers("active")
        t1 = time.time()

        self.assertEqual(len(rows), len(self.active_subject_ids))

        # Quick perf sanity: this is mostly a DB join;
        # should be fast even with thousands.
        self.assertLess(t1 - t0, BULK_PERF_SECONDS)

        # Compare each row to the per-user query result (consistency check)
        # NOTE: This is O(n) DB calls; still fine at a few thousand.
        for r in rows:
            with self.subTest(userID=r.userID):
                single = self.repo.get_subject_effective_entitlements(r.userID)
                self.assertIsNotNone(single)
                assert single is not None

                # Fields must match exactly (these are "effective entitlements")
                self.assertEqual(r.userID, single.userID)
                self.assertEqual(r.apiKeyID, single.apiKeyID)
                self.assertEqual(r.accountName, single.accountName)
                self.assertEqual(r.subject_status, single.subject_status)

                self.assertEqual(r.plan_id, single.plan_id)
                self.assertEqual(r.tier, single.tier)
                self.assertEqual(r.plan_status, single.plan_status)
                self.assertEqual(r.allow_live, single.allow_live)
                self.assertEqual(r.plan_description, single.plan_description)

                self.assertEqual(r.max_n, single.max_n)
                self.assertEqual(r.max_k, single.max_k)
                self.assertEqual(r.existential_only, single.existential_only)
                self.assertEqual(r.rate_limit, single.rate_limit)
                self.assertEqual(r.rate_window, single.rate_window)

    def test_repo_effective_entitlements_equal_db_coalesce_ground_truth(self):
        """
        Ground-truth test: compute expected effective limits via SQL COALESCE,
        then ensure repo returns the same values.
        """
        sql = """
        SELECT
          s.userID,
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
        WHERE s.status = 'active'
        """
        truth = {
            int(uid): (
                int(max_n),
                int(max_k),
                bool(exist_only),
                int(rate_limit),
                int(rate_window),
            )
            for (
                uid,
                max_n,
                max_k,
                exist_only,
                rate_limit,
                rate_window,
            ) in self.conn.execute(sql).fetchall()
        }

        rows = self.repo.list_activeUsers("active")
        self.assertEqual(len(rows), len(truth))

        for r in rows:
            with self.subTest(userID=r.userID):
                expected = truth.get(r.userID)
                self.assertIsNotNone(expected)
                assert expected is not None
                self.assertEqual(
                    (r.max_n, r.max_k, r.existential_only, r.rate_limit, r.rate_window),
                    expected,
                )


class TestBulkMutationsAndIntegrity(unittest.TestCase):
    """
    Bulk write/delete/update tests to flush out edge cases:
    - update plan_limits and verify effect
    - update subject overrides and verify effect
    - delete subjects and verify override cascade
    - verify RESTRICT for plans referenced by subject_plan
    """

    def setUp(self) -> None:
        self.conn = make_in_memory_conn()
        self.repo = PlanRepo(self.conn)
        self.rng = random.Random(20251229)

        # Use safe tiers if your schema enforces tier list
        self.plan_free = insert_plan_with_limits(
            self.conn,
            tier="free",
            status="active",
            allow_live=0,
            max_n=15,
            max_k=8,
            existential_only=0,
            rate_limit=10,
            rate_window=60,
        )
        self.plan_pro = insert_plan_with_limits(
            self.conn,
            tier="pro",
            status="active",
            allow_live=1,
            max_n=31,
            max_k=16,
            existential_only=1,
            rate_limit=20,
            rate_window=60,
        )

        self.subjects: list[int] = []
        for i in range(1200):
            status = "active" if i % 3 != 0 else "disabled"
            uid = insert_subject(
                self.conn,
                apiKeyID=200_000 + i,
                accountName=f"user_{i}",
                status=status,
            )
            self.subjects.append(uid)
            pid = self.plan_free if (i % 2 == 0) else self.plan_pro
            assign_subject_plan(self.conn, subject_id=uid, plan_id=pid)

        # Give overrides to ~half
        self.override_subjects = self.rng.sample(
            self.subjects, k=len(self.subjects) // 2
        )
        for uid in self.override_subjects:
            insert_subject_plan_limits(
                self.conn,
                subject_id=uid,
                max_n=99,
                max_k=9,
                existential_only=1,
                rate_limit=None,
                rate_window=None,
            )

    def tearDown(self) -> None:
        self.conn.close()

    def test_bulk_update_plan_limits_propagates_to_effective_entitlements(self):
        # Update plan_free plan_limits
        # (fallback path should change for users without overrides)
        self.conn.execute(
            "UPDATE plan_limits SET max_n = ?, max_k = ? WHERE plan_id = ?",
            (123, 12, self.plan_free),
        )
        self.conn.commit()

        rows = self.repo.list_activeUsers("active")

        # For active users on free plan:
        # - if they have overrides max_n/max_k fixed at 99/9, they remain
        # - else fallback should now be 123/12
        # We'll sample a subset to keep test fast.
        sample = self.rng.sample(rows, k=min(250, len(rows)))
        for r in sample:
            if r.plan_id != self.plan_free:
                continue
            with self.subTest(userID=r.userID):
                has_override = r.userID in set(self.override_subjects)
                if has_override:
                    self.assertEqual(r.max_n, 99)
                    self.assertEqual(r.max_k, 9)
                else:
                    self.assertEqual(r.max_n, 123)
                    self.assertEqual(r.max_k, 12)

    def test_bulk_update_subject_overrides_propagates(self):
        # Pick 50 override subjects and change their overrides
        chosen = self.rng.sample(self.override_subjects, k=50)
        for uid in chosen:
            self.conn.execute(
                """
                UPDATE subject_plan_limits
                SET max_n = ?, max_k = ?, existential_only = ?, 
                rate_limit = ?, rate_window = ?
                WHERE subject_id = ?
                """,
                (777, 7, 0, 33, 120, uid),
            )
        self.conn.commit()

        for uid in chosen:
            with self.subTest(userID=uid):
                row = self.repo.get_subject_effective_entitlements(uid)
                self.assertIsNotNone(row)
                assert row is not None
                self.assertEqual(row.max_n, 777)
                self.assertEqual(row.max_k, 7)
                self.assertIs(row.existential_only, False)
                self.assertEqual(row.rate_limit, 33)
                self.assertEqual(row.rate_window, 120)

    def test_bulk_delete_subjects_cascades_subject_plan_limits(self):
        # Delete 100 subjects; any subject_plan_limits should cascade
        to_delete = self.rng.sample(self.subjects, k=100)
        for uid in to_delete:
            self.conn.execute("DELETE FROM subjects WHERE userID = ?", (uid,))
        self.conn.commit()

        # Verify no dangling overrides
        dangling = self.conn.execute(
            """
            SELECT COUNT(*) FROM subject_plan_limits spl
            LEFT JOIN subjects s ON s.userID = spl.subject_id
            WHERE s.userID IS NULL
            """
        ).fetchone()[0]
        self.assertEqual(dangling, 0)

        # Verify repo returns None for deleted
        for uid in to_delete[:20]:  # sample
            with self.subTest(userID=uid):
                self.assertIsNone(self.repo.get_subject_effective_entitlements(uid))

    def test_restrict_delete_plan_when_referenced_by_subject_plan_bulk(self):
        # Both plans are referenced by many subject_plan rows.
        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute("DELETE FROM plans WHERE id = ?", (self.plan_free,))
            self.conn.commit()

        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute("DELETE FROM plans WHERE id = ?", (self.plan_pro,))
            self.conn.commit()


class TestBulkConstraintRejectionOnOverrides(unittest.TestCase):
    """
    Pound on subject_plan_limits constraints:
    - invalid existential_only values
    - invalid ranges for max_n/max_k
    - invalid max_k > max_n when both provided
    - invalid rate_limit / rate_window
    """

    def setUp(self) -> None:
        self.conn = make_in_memory_conn()
        self.repo = PlanRepo(self.conn)

        self.plan_id = insert_plan_with_limits(self.conn, tier="free")
        self.uid = insert_subject(
            self.conn, apiKeyID=333_333, accountName="X", status="active"
        )
        assign_subject_plan(self.conn, subject_id=self.uid, plan_id=self.plan_id)

    def tearDown(self) -> None:
        self.conn.close()

    def test_bulk_invalid_override_inserts_rejected(self):
        invalid_rows = [
            # (max_n, max_k, existential_only, rate_limit, rate_window)
            (0, None, None, None, None),  # max_n < 1
            (2049, None, None, None, None),  # max_n > 2048
            (None, 0, None, None, None),  # max_k < 1
            (10, 11, None, None, None),  # max_k > max_n (both set)
            (None, None, 2, None, None),  # existential_only invalid
            (None, None, None, 0, None),  # rate_limit < 1
            (None, None, None, None, 0),  # rate_window < 1
        ]

        for i, (max_n, max_k, existential_only, rate_limit, rate_window) in enumerate(
            invalid_rows
        ):
            with self.subTest(case=i), self.assertRaises(sqlite3.IntegrityError):
                self.conn.execute(
                    """
                        INSERT INTO subject_plan_limits
                        (subject_id, max_n, max_k, existential_only,
                         rate_limit, rate_window)
                        VALUES (?, ?, ?, ?, ?, ?)
                        """,
                    (
                        self.uid,
                        max_n,
                        max_k,
                        existential_only,
                        rate_limit,
                        rate_window,
                    ),
                )
                self.conn.commit()

    def test_bulk_invalid_override_updates_rejected(self):
        # Insert a valid override first
        insert_subject_plan_limits(self.conn, subject_id=self.uid, max_n=20, max_k=10)

        bad_updates = [
            ("max_n = 0", ()),
            ("max_n = 999999", ()),
            ("max_k = 0", ()),
            ("existential_only = 3", ()),
            ("rate_limit = 0", ()),
            ("rate_window = 0", ()),
            # max_k > max_n when both non-null
            ("max_n = 10, max_k = 11", ()),
        ]

        for i, (set_clause, params) in enumerate(bad_updates):
            with (
                self.subTest(case=i, set_clause=set_clause),
                self.assertRaises(sqlite3.IntegrityError),
            ):
                self.conn.execute(
                    f"""UPDATE subject_plan_limits SET {set_clause} 
                        WHERE subject_id = ?""",
                    (*params, self.uid),
                )
                self.conn.commit()


class TestBulkWeirdAccountNames(unittest.TestCase):
    """
    Bulk stress on big/unicode/odd strings for accountName:
    Ensures joins and mappings don't choke on large TEXT payloads.
    """

    def setUp(self) -> None:
        self.conn = make_in_memory_conn()
        self.repo = PlanRepo(self.conn)
        self.plan_id = insert_plan_with_limits(self.conn, tier="free")

    def tearDown(self) -> None:
        self.conn.close()

    def test_bulk_weird_account_names_roundtrip(self):
        weird_names = [
            "💥" * 50,
            "测试" * 100,
            "привет" * 80,
            "a" * 100_000,  # huge
            "line1\nline2\r\nline3\tend",
            "quote'\"semi;--",
            "nullbyte?\0stillstring",  # python allows, sqlite may store
        ]

        uids: list[int] = []
        for i, name in enumerate(weird_names):
            uid = insert_subject(
                self.conn,
                apiKeyID=444_000 + i,
                accountName=name,
                status="active",
            )
            assign_subject_plan(self.conn, subject_id=uid, plan_id=self.plan_id)
            uids.append(uid)

        rows = self.repo.list_activeUsers("active")
        by_id = {r.userID: r for r in rows}

        for uid, expected in zip(uids, weird_names, strict=False):
            with self.subTest(userID=uid):
                self.assertIn(uid, by_id)
                self.assertEqual(by_id[uid].accountName, expected)

                single = self.repo.get_subject_effective_entitlements(uid)
                self.assertIsNotNone(single)
                assert single is not None
                self.assertEqual(single.accountName, expected)


if __name__ == "__main__":
    unittest.main(verbosity=2)
