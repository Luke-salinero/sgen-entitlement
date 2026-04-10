from __future__ import annotations

from collections.abc import AsyncGenerator

import asyncpg

from app.db.pool import get_pool


async def get_db_conn() -> AsyncGenerator[asyncpg.Connection, None]:
    pool = await get_pool()
    async with pool.acquire() as conn, conn.transaction():
        yield conn
