# tests/test_db_roundtrip.py
import asyncio
from pprint import pprint

from app.db.pool import get_pool, init_pool


async def main() -> None:
    await init_pool()
    pool = await get_pool()

    # Pick a unique user id so reruns are predictable
    user_id = "test-user-1"
    api_key = "test-api-key-1"
    account_name = "Test Account"

    async with pool.acquire() as conn:
        # Make sure the schema exists before running this test.
        # (If tables don't exist, you'll get a "relation does not exist" error.)

        # 1) Ensure the default plan exists (expects your seed data OR we insert it)
        # If your migrations already seed plans, this does nothing.
        await conn.execute(
            """
            INSERT INTO plans (id, tier, status, allow_live, description)
            VALUES (1, 'free', 'active', false, 'Free tier')
            ON CONFLICT (id) DO NOTHING
            """
        )
        await conn.execute(
            """
            INSERT INTO plan_limits (plan_id, max_n, max_k, existential_only,
             rate_limit, rate_window)
            VALUES (1, 256, 16, true, 60, 60)
            ON CONFLICT (plan_id) DO NOTHING
            """
        )

        # 2) Upsert subject + ensure subject_plan exists
        # NOTE: If your columns are snake_case, change "userID"/"apiKey"/"accountName"
        #  accordingly.
        await conn.execute(
            """
            INSERT INTO subjects ("userID", "apiKey", "accountName", status)
            VALUES ($1, $2, $3, 'active')
            ON CONFLICT ("userID") DO UPDATE SET
              "apiKey" = EXCLUDED."apiKey",
              "accountName" = EXCLUDED."accountName",
              status = EXCLUDED.status
            """,
            user_id,
            api_key,
            account_name,
        )

        await conn.execute(
            """
            INSERT INTO subject_plan (subject_id, plan_id)
            VALUES ($1, 1)
            ON CONFLICT (subject_id) DO NOTHING
            """,
            user_id,
        )

        # 3) Print the rows we just wrote
        print("\n--- subjects row ---")
        subj = await conn.fetchrow(
            """SELECT "userID", "apiKey", "accountName", status, created_at
               FROM subjects
               WHERE "userID" = $1
            """,
            user_id,
        )
        pprint(dict(subj) if subj else None)

        print("\n--- subject_plan row ---")
        sp = await conn.fetchrow(
            """SELECT subject_id, plan_id
               FROM subject_plan
               WHERE subject_id = $1
            """,
            user_id,
        )
        pprint(dict(sp) if sp else None)

        print("\n--- effective entitlements (joined) ---")
        eff = await conn.fetchrow(
            """
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
            """,
            user_id,
        )
        pprint(dict(eff) if eff else None)

        # 4) (Optional) Print a quick "DB snapshot"
        print("\n--- DB snapshot (top 10 subjects) ---")
        rows = await conn.fetch(
            """SELECT "userID", "accountName", status, created_at
               FROM subjects
               ORDER BY created_at DESC
               LIMIT 10
            """
        )
        for r in rows:
            pprint(dict(r))

        # 5) Cleanup so reruns are clean
        # This cascades subject_plan and subject_plan_limits due to FK ON
        #  DELETE CASCADE.
        await conn.execute("""DELETE FROM subjects WHERE "userID" = $1""", user_id)
        print("\n(cleaned up test subject)\n")


if __name__ == "__main__":
    asyncio.run(main())
