# tests/tests_postgres.py
import asyncio

from app.db.pool import get_pool, init_pool


async def test():
    await init_pool()
    pool = await get_pool()

    async with pool.acquire() as conn:
        one = await conn.fetchval("SELECT 1")
        print("SELECT 1 =", one)


asyncio.run(test())
