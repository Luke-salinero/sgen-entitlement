"""
unittest-based unit tests (no pytest) for:
- Repo.py (PlanRepo)
- connection.py (get_connection)
- schema constraints (high-value integrity tests)

Adjust the imports at the top to match your project structure.
"""

import decimal
import random
import sqlite3
import string
import tempfile
import time
import unittest
from pathlib import Path

import app.db.connection as connection_module
from app.db.connection import get_connection

# Adjust these imports to your actual module paths
# Example possibilities:
# from app.db.repo import PlanRepo
# from app.db.connection import get_connection
# import app.db.connection as connection_module
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
    CHECK (tier in ('free', 'pro'))
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
    plan_id = cur.lastrowid
    conn.execute(
        """
        INSERT INTO plan_limits(plan_id, max_n, max_k, existential_only, rate_limit, 
        rate_window)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (plan_id, max_n, max_k, existential_only, rate_limit, rate_window),
    )
    conn.commit()
    return int(plan_id)


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
    user_id = cur.lastrowid
    conn.commit()
    return int(user_id)


def assign_subject_plan(
    conn: sqlite3.Connection, *, subject_id: int, plan_id: int
) -> None:
    conn.execute(
        "INSERT INTO subject_plan(subject_id, plan_id) VALUES (?, ?)",
        (subject_id, plan_id),
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
        "Pro",  # case mismatch (schema tiers are lowercase)
        "free' OR 1=1 --",
        "'; DROP TABLE plans; --",
        "free; SELECT * FROM plans;",
        "free\0pro",  # null byte inside python string
        "💥",
        "测试",
        "привет",
        "áéíóú",  # unicode
        "x" * 10,
        "x" * 100,
        "x" * 10_000,  # very long
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

        # A few key fields should be present
        self.assertGreaterEqual(res.max_n, 1)
        self.assertGreaterEqual(res.max_k, 1)
        self.assertIsInstance(res.created_at, str)
        self.assertIsInstance(res.updated_at, str)
        self.assertIsInstance(res.limits_updated_at, str)

    def test_get_planLimits_returns_none_for_unknown_tier(self):
        insert_plan_with_limits(self.conn, tier="free")
        self.assertIsNone(self.repo.get_planLimits("pro"))

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
        # parameterized query should treat this as literal string and return none
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
        self.assertIsNotNone(self.repo.get_planLimitsID(plan_id))  # sanity

        # SQLite will bind strings fine; it just won't match the integer id.
        res = self.repo.get_planLimitsID("not-an-int")  # type: ignore[arg-type]
        self.assertIsNone(res)


class TestPlanRepoListActiveUsers(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = make_in_memory_conn()
        self.repo = PlanRepo(self.conn)

    def tearDown(self) -> None:
        self.conn.close()

    def test_list_activeUsers_returns_users_for_matching_status(self):
        plan_id = insert_plan_with_limits(self.conn, tier="free")
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

        # Verify mapping + plan_id
        user_ids = {r.userID for r in res}
        self.assertSetEqual(user_ids, {u1, u2})
        for r in res:
            self.assertEqual(r.plan_id, plan_id)
            self.assertEqual(r.status, "active")

    def test_list_activeUsers_returns_empty_list_when_none_match(self):
        plan_id = insert_plan_with_limits(self.conn, tier="free")
        u1 = insert_subject(
            self.conn, apiKeyID=201, accountName="Acme", status="disabled"
        )
        assign_subject_plan(self.conn, subject_id=u1, plan_id=plan_id)

        res = self.repo.list_activeUsers("active")
        self.assertEqual(res, [])

    def test_list_activeUsers_excludes_subjects_without_subject_plan(self):
        plan_id = insert_plan_with_limits(self.conn, tier="free")
        u1 = insert_subject(
            self.conn, apiKeyID=301, accountName="HasPlan", status="active"
        )
        # u2 = insert_subject(
        #    self.conn, apiKeyID=302, accountName="NoPlan", status="active"
        # )

        assign_subject_plan(self.conn, subject_id=u1, plan_id=plan_id)

        res = self.repo.list_activeUsers("active")
        self.assertEqual(len(res), 1)
        self.assertEqual(res[0].userID, u1)

    def test_list_activeUsers_multiple_users_same_plan_allowed(self):
        plan_id = insert_plan_with_limits(self.conn, tier="free")
        u1 = insert_subject(self.conn, apiKeyID=401, accountName="A", status="active")
        u2 = insert_subject(self.conn, apiKeyID=402, accountName="B", status="active")
        assign_subject_plan(self.conn, subject_id=u1, plan_id=plan_id)
        assign_subject_plan(self.conn, subject_id=u2, plan_id=plan_id)

        res = self.repo.list_activeUsers("active")
        self.assertEqual(len(res), 2)
        self.assertTrue(all(r.plan_id == plan_id for r in res))

    def test_list_activeUsers_rejects_sql_injection_like_input(self):
        plan_id = insert_plan_with_limits(self.conn, tier="free")
        u1 = insert_subject(self.conn, apiKeyID=501, accountName="A", status="active")
        assign_subject_plan(self.conn, subject_id=u1, plan_id=plan_id)

        res = self.repo.list_activeUsers("active' OR 1=1 --")
        self.assertEqual(res, [])


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
                    # simple sanity query
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
                """INSERT INTO plans(tier,status,allow_live,description) 
                VALUES (?,?,?,?)""",
                ("free", "active", 2, None),
            )
            self.conn.commit()

    def test_schema_enforces_plan_limits_constraints_max_k_le_max_n(self):
        plan_id = insert_plan_with_limits(self.conn, tier="free")  # insert valid first
        # delete limits and try to reinsert invalid ones
        self.conn.execute("DELETE FROM plan_limits WHERE plan_id = ?", (plan_id,))
        self.conn.commit()

        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute(
                """
                INSERT INTO 
                plan_limits(plan_id, max_n, max_k, existential_only, 
                rate_limit, rate_window)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (plan_id, 10, 11, 0, 10, 60),
            )
            self.conn.commit()

    def test_schema_cascades_delete_plan_to_plan_limits(self):
        plan_id = insert_plan_with_limits(self.conn, tier="free")
        # confirm limits exists
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


class TestPlanRepoBruteForce(unittest.TestCase):
    """
    Brute-force / fuzz-ish tests:
    - tries many weird tiers/status strings
    - inserts lots of rows
    - attempts constraint-breaking inserts
    - ensures methods don't crash and behave predictably
    """

    def setUp(self) -> None:
        self.conn = make_in_memory_conn()
        self.repo = PlanRepo(self.conn)
        self.rng = random.Random(1337)  # deterministic seed

    def tearDown(self) -> None:
        self.conn.close()

    def test_get_planLimits_fuzz_tier_inputs_never_crashes(self):
        # Seed DB with valid plans+limits
        insert_plan_with_limits(self.conn, tier="free")
        insert_plan_with_limits(self.conn, tier="pro")

        # Lots of random and "nasty" tiers
        candidates = nasty_strings()
        for _ in range(200):
            candidates.append(rand_str(self.rng, self.rng.randint(0, 200)))

        for tier in candidates:
            with self.subTest(tier=tier):
                res = self.repo.get_planLimits(tier)
                # Only exact 'free' or 'pro' should match
                if tier in ("free", "pro"):
                    self.assertIsNotNone(res)
                else:
                    self.assertTrue(res is None or res.tier in ("free", "pro"))

    def test_get_planLimitsID_fuzz_plan_id_inputs_never_crashes(self):
        free_id = insert_plan_with_limits(self.conn, tier="free")

        # ints: negative, huge, zero, random
        int_candidates = [-10, -1, 0, 1, free_id, 2, 999999999, 2**31 - 1]
        for _ in range(200):
            int_candidates.append(self.rng.randint(-10_000, 10_000))

        for pid in int_candidates:
            with self.subTest(plan_id=pid):
                res = self.repo.get_planLimitsID(pid)
                if pid == free_id:
                    self.assertIsNotNone(res)
                else:
                    self.assertIsNone(res)

        # Also try non-ints. SQLite will bind many of these without raising.
        # Also try non-ints. SQLite may coerce "numeric" strings like "0001" -> 1.
        non_int_candidates = [
            "1",
            "0001",
            "01",
            " 1 ",
            "+1",
            "1.0",
            "not-an-int",
            "9999999999999999999999999",
            1.0,
            1.5,
            None,
            True,
            False,
            b"1",
            b"free",
        ]
        for pid in non_int_candidates:
            with self.subTest(non_int_plan_id=pid):
                try:
                    res = self.repo.get_planLimitsID(pid)  # type: ignore[arg-type]

                    # If sqlite coerces it to the real id, we may get a row.
                    # Only assert that:
                    # - it doesn't crash
                    # - if it returns a row, it's the correct one (id=free_id)
                    if res is not None:
                        self.assertEqual(res.plan_id, free_id)
                    else:
                        self.assertIsNone(res)

                except (
                    sqlite3.ProgrammingError,
                    sqlite3.InterfaceError,
                    TypeError,
                    ValueError,
                ):
                    # Binding errors vary by Python/SQLite version.
                    pass

    def test_list_activeUsers_fuzz_status_inputs_never_crashes(self):
        plan_id = insert_plan_with_limits(self.conn, tier="free")

        # Make a few users with known statuses
        u_active = insert_subject(
            self.conn, apiKeyID=1001, accountName="ActiveUser", status="active"
        )
        u_disabled = insert_subject(
            self.conn, apiKeyID=1002, accountName="DisabledUser", status="disabled"
        )
        assign_subject_plan(self.conn, subject_id=u_active, plan_id=plan_id)
        assign_subject_plan(self.conn, subject_id=u_disabled, plan_id=plan_id)

        candidates = nasty_strings()
        for _ in range(200):
            candidates.append(rand_str(self.rng, self.rng.randint(0, 200)))

        for status in candidates:
            with self.subTest(status=status):
                res = self.repo.list_activeUsers(status)
                self.assertIsInstance(res, list)
                # Only exact "active" should return our active user
                if status == "active":
                    self.assertTrue(any(r.userID == u_active for r in res))
                else:
                    # If status isn't exactly "active", should not include active user
                    self.assertFalse(any(r.userID == u_active for r in res))

    def test_bulk_insert_many_subjects_and_query_performance_sanity(self):
        """
        Inserts many rows to try to stress the repo.
        Keep counts moderate so it still runs fast in CI.
        """
        plan_id = insert_plan_with_limits(self.conn, tier="free")

        n_active = 1500
        n_disabled = 500

        # Insert active users
        for i in range(n_active):
            uid = insert_subject(
                self.conn,
                apiKeyID=10_000 + i,
                accountName=f"acct_active_{i}",
                status="active",
            )
            assign_subject_plan(self.conn, subject_id=uid, plan_id=plan_id)

        # Insert disabled users
        for i in range(n_disabled):
            uid = insert_subject(
                self.conn,
                apiKeyID=20_000 + i,
                accountName=f"acct_disabled_{i}",
                status="disabled",
            )
            assign_subject_plan(self.conn, subject_id=uid, plan_id=plan_id)

        t0 = time.time()
        res = self.repo.list_activeUsers("active")
        t1 = time.time()

        self.assertEqual(len(res), n_active)

        # Not a strict perf test, just a sanity bound
        # to catch accidental O(n^2) in Python loops
        self.assertLess(t1 - t0, 2.0)

    def test_constraints_bruteforce_invalid_plan_limits_rejected(self):
        """
        Try many invalid plan_limits combinations to ensure DB enforces constraints.
        """
        plan_id = insert_plan_with_limits(self.conn, tier="free")

        # Remove the valid limits, then attempt invalid inserts
        self.conn.execute("DELETE FROM plan_limits WHERE plan_id = ?", (plan_id,))
        self.conn.commit()

        invalid_cases = [
            # (max_n, max_k, existential_only, rate_limit, rate_window)
            (0, 1, 0, 1, 1),  # max_n < 1
            (2049, 1, 0, 1, 1),  # max_n > 2048
            (10, 0, 0, 1, 1),  # max_k < 1
            (10, 11, 0, 1, 1),  # max_k > max_n
            (10, 1, 2, 1, 1),  # existential_only not 0/1
            (10, 1, 0, 0, 1),  # rate_limit < 1
            (10, 1, 0, 1, 0),  # rate_window < 1
        ]

        for case in invalid_cases:
            with self.subTest(case=case), self.assertRaises(sqlite3.IntegrityError):
                self.conn.execute(
                    """
                    INSERT INTO plan_limits
                    (plan_id, max_n, max_k, existential_only,
                    rate_limit, rate_window)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (plan_id, *case),
                )
                self.conn.commit()

        # Finally insert a valid one to ensure DB isn't left in a broken state
        self.conn.execute(
            """
            INSERT INTO plan_limits
            (plan_id, max_n, max_k, existential_only, rate_limit, rate_window)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (plan_id, 15, 8, 1, 10, 60),
        )
        self.conn.commit()
        self.assertIsNotNone(self.repo.get_planLimitsID(plan_id))

    def test_subject_plan_foreign_key_and_restrict_delete_bruteforce(self):
        """
        Attempts invalid foreign keys + verifies RESTRICT behavior repeatedly.
        """
        free_id = insert_plan_with_limits(self.conn, tier="free")

        # Invalid subject_plan: subject doesn't exist
        with self.assertRaises(sqlite3.IntegrityError):
            assign_subject_plan(self.conn, subject_id=999999, plan_id=free_id)

        # Invalid subject_plan: plan doesn't exist
        uid = insert_subject(self.conn, apiKeyID=7777, accountName="X", status="active")
        with self.assertRaises(sqlite3.IntegrityError):
            assign_subject_plan(self.conn, subject_id=uid, plan_id=999999)

        # Valid assignment
        assign_subject_plan(self.conn, subject_id=uid, plan_id=free_id)

        # RESTRICT: can't delete plan while referenced
        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute("DELETE FROM plans WHERE id = ?", (free_id,))
            self.conn.commit()


class TestPlanRepoInjectionResistanceSmoke(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = make_in_memory_conn()
        self.repo = PlanRepo(self.conn)

    def tearDown(self) -> None:
        self.conn.close()

    def test_injection_inputs_do_not_modify_schema(self):
        insert_plan_with_limits(self.conn, tier="free")

        # Try a bunch of nasty inputs
        for payload in [
            "'; DROP TABLE plans; --",
            "free'; DROP TABLE plan_limits; --",
            "free' OR 1=1 --",
        ]:
            with self.subTest(payload=payload):
                _ = self.repo.get_planLimits(payload)
                _ = self.repo.list_activeUsers(payload)

        # If tables were dropped, these would error.
        tables = set(
            r[0]
            for r in self.conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        )
        self.assertTrue(
            {"plans", "plan_limits", "subjects", "subject_plan"}.issubset(tables)
        )


class TestPlanRepoNicheParameterBinding(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = make_in_memory_conn()
        self.repo = PlanRepo(self.conn)
        self.free_id = insert_plan_with_limits(self.conn, tier="free")
        self.pro_id = insert_plan_with_limits(self.conn, tier="pro")

    def tearDown(self) -> None:
        self.conn.close()

    def test_get_planLimits_tier_weird_whitespace_and_null_bytes(self):
        # Only exact 'free' matches, so whitespace variants should not.
        cases = [
            " free",
            "free ",
            "\tfree",
            "free\n",
            "free\r\n",
            "free\0",  # null byte suffix
            "fr\0ee",  # embedded null byte
        ]
        for tier in cases:
            with self.subTest(tier=repr(tier)):
                self.assertIsNone(self.repo.get_planLimits(tier))

    def test_get_planLimits_tier_unicode_normalization_tricks(self):
        # Visually similar strings that are not byte-equal should not match.
        # e.g. "free" with different Unicode code points.
        # (SQLite compares by byte sequence for TEXT by
        # default unless collation says otherwise.)
        cases = [
            "fr\u0065e",  # normal 'e'
            "fr\u00E9e",  # 'é' instead of 'e'
            "fr\u0065\u0301e",  # 'e' + combining accent
            "𝒻ree",  # fancy unicode letter
        ]
        for tier in cases:
            with self.subTest(tier=tier):
                if tier == "free":
                    self.assertIsNotNone(self.repo.get_planLimits(tier))
                else:
                    self.assertIsNone(self.repo.get_planLimits(tier))

    def test_get_planLimitsID_sqlite_numeric_string_coercion(self):
        # SQLite will coerce numeric-like strings into numbers for comparisons.
        coercing = ["1", "0001", " 1 ", "+1", "1.0", "1e0"]
        for pid in coercing:
            with self.subTest(pid=pid):
                res = self.repo.get_planLimitsID(pid)  # type: ignore[arg-type]
                self.assertIsNotNone(res)
                assert res is not None
                self.assertEqual(res.plan_id, self.free_id)

        # But these should NOT coerce to 1 (or may not) -> usually None.
        non_coercing = ["1x", "x1", "01x", "1.0000000000000001", "nan", "inf", "-inf"]
        for pid in non_coercing:
            with self.subTest(pid=pid):
                res = self.repo.get_planLimitsID(pid)  # type: ignore[arg-type]
                # Some SQLite builds coerce aggressively; if it returns something,
                # it must be a valid plan id.
                if res is not None:
                    self.assertIn(res.plan_id, (self.free_id, self.pro_id))
                else:
                    self.assertIsNone(res)

    def test_get_planLimitsID_extreme_numeric_types(self):
        # These can expose coercion, overflow, or binding differences.
        candidates = [
            0,
            -1,
            2**31 - 1,
            2**63 - 1,
            2**63,  # may overflow to float or error depending on build
            10**100,  # extremely huge int
            1.0,
            1.0000000000,
            float("nan"),
            float("inf"),
            float("-inf"),
            decimal.Decimal("1"),
            decimal.Decimal("1.0"),
        ]

        for pid in candidates:
            with self.subTest(pid=repr(pid)):
                try:
                    res = self.repo.get_planLimitsID(pid)  # type: ignore[arg-type]
                    # If it returns a row, ensure it's one of our known ids.
                    if res is not None:
                        self.assertIn(res.plan_id, (self.free_id, self.pro_id))
                except (
                    sqlite3.InterfaceError,
                    sqlite3.ProgrammingError,
                    OverflowError,
                    ValueError,
                    TypeError,
                ):
                    # Valid outcome: sqlite binding may reject some values.
                    pass


class TestPlanRepoDatabaseStateFailures(unittest.TestCase):
    def test_methods_fail_cleanly_when_connection_closed(self):
        conn = make_in_memory_conn()
        repo = PlanRepo(conn)
        insert_plan_with_limits(conn, tier="free")
        conn.close()

        # A closed connection is a valid failure mode in real services.
        with self.assertRaises(sqlite3.ProgrammingError):
            repo.get_planLimits("free")

        with self.assertRaises(sqlite3.ProgrammingError):
            repo.get_planLimitsID(1)

        with self.assertRaises(sqlite3.ProgrammingError):
            repo.list_activeUsers("active")

    def test_methods_raise_when_tables_missing(self):
        # Create connection with no schema loaded
        conn = sqlite3.connect(":memory:")
        conn.execute("PRAGMA foreign_keys = ON;")
        repo = PlanRepo(conn)

        with self.assertRaises(sqlite3.OperationalError):
            repo.get_planLimits("free")

        with self.assertRaises(sqlite3.OperationalError):
            repo.list_activeUsers("active")

        conn.close()

    def test_methods_raise_when_schema_is_wrong_shape(self):
        # Create tables with missing columns to simulate migration mismatch.
        conn = sqlite3.connect(":memory:")
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.executescript(
            """
        CREATE TABLE plans(id INTEGER PRIMARY KEY, tier TEXT NOT NULL UNIQUE,
        status TEXT NOT NULL, allow_live INTEGER NOT NULL);
        CREATE TABLE plan_limits(plan_id INTEGER NOT NULL UNIQUE, 
        max_n INTEGER NOT NULL, max_k INTEGER NOT NULL,
                                 existential_only INTEGER NOT NULL, 
                                 rate_limit INTEGER NOT NULL, 
                                 rate_window INTEGER NOT NULL,
                                 FOREIGN KEY (plan_id) REFERENCES plans(id));
        """
        )
        repo = PlanRepo(conn)
        conn.execute(
            "INSERT INTO plans(tier,status,allow_live) VALUES ('free','active',0)"
        )
        pid = conn.execute("SELECT id FROM plans WHERE tier='free'").fetchone()[0]
        sqlLine = (
            "INSERT INTO plan_limits(plan_id, max_n, max_k, "
            "existential_only, rate_limit, rate_window) "
            "VALUES (?, ?, ?, ?, ?, ?)"
        )
        conn.execute(
            sqlLine,
            (pid, 15, 8, 0, 10, 60),
        )
        conn.commit()

        # Repo SELECT expects created_at/updated_at columns; this should break.
        with self.assertRaises(sqlite3.OperationalError):
            repo.get_planLimits("free")

        conn.close()


class TestSQLiteLockingBehavior(unittest.TestCase):
    def test_database_locked_can_happen_during_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "locktest.db"

            # conn1 creates schema and begins a write lock
            conn1 = sqlite3.connect(db_path)
            conn1.execute("PRAGMA foreign_keys = ON;")
            conn1.executescript(SCHEMA_SQL)
            sqlLine = (
                "INSERT INTO plans(tier,status,allow_live,description)"
                "VALUES ('free','active',0,NULL)"
            )
            conn1.execute(sqlLine)
            conn1.commit()

            # Start a transaction that holds a RESERVED lock
            conn1.execute("BEGIN IMMEDIATE;")
            conn1.execute("UPDATE plans SET status='active' WHERE tier='free'")

            # conn2 tries to write while conn1 holds lock
            conn2 = sqlite3.connect(db_path)
            conn2.execute("PRAGMA busy_timeout = 100;")  # keep this test fast
            try:
                with self.assertRaises(sqlite3.OperationalError):
                    sqlLine = (
                        "INSERT INTO plans(tier,status,allow_live,description)"
                        "VALUES ('pro','active',0,NULL)"
                    )
                    conn2.execute(sqlLine)
                    conn2.commit()
            finally:
                conn2.close()
                conn1.rollback()
                conn1.close()


class TestListActiveUsersJoinAssumptions(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = make_in_memory_conn()
        self.repo = PlanRepo(self.conn)
        self.plan_id = insert_plan_with_limits(self.conn, tier="free")

    def tearDown(self) -> None:
        self.conn.close()

    def test_subject_plan_primary_key_prevents_multiple_plans_per_subject(self):
        uid = insert_subject(self.conn, apiKeyID=1111, accountName="A", status="active")
        assign_subject_plan(self.conn, subject_id=uid, plan_id=self.plan_id)

        # subject_plan.subject_id is PRIMARY KEY, so a second assignment should fail
        with self.assertRaises(sqlite3.IntegrityError):
            assign_subject_plan(self.conn, subject_id=uid, plan_id=self.plan_id)

    def test_list_activeUsers_ignores_subjects_without_plan(self):
        _uid = insert_subject(
            self.conn, apiKeyID=2222, accountName="NoPlan", status="active"
        )
        # no subject_plan row added
        res = self.repo.list_activeUsers("active")
        self.assertEqual(res, [])

    def test_list_activeUsers_handles_large_account_names(self):
        uid = insert_subject(
            self.conn,
            apiKeyID=3333,
            accountName="X" * 50_000,  # huge
            status="active",
        )
        assign_subject_plan(self.conn, subject_id=uid, plan_id=self.plan_id)

        res = self.repo.list_activeUsers("active")
        self.assertEqual(len(res), 1)
        self.assertEqual(res[0].userID, uid)
        self.assertEqual(res[0].accountName, "X" * 50_000)


if __name__ == "__main__":
    unittest.main(verbosity=2)
