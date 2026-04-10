# tests/tests_postgres.py
import asyncio

from app.db.deps import get_db_conn
from app.db.pool import init_pool


async def test():
    await init_pool()

    async for conn in get_db_conn():
        one = await conn.fetchval("SELECT 1")
        print("SELECT 1 =", one)


asyncio.run(test())
