# app/db/pool.py
from __future__ import annotations

import asyncpg

from app.core.config import get_settings

settings = get_settings()

_pool: asyncpg.Pool | None = None


def _normalize_asyncpg_dsn(url: str) -> str:
    """
    If you already use `postgresql+asyncpg://...` for SQLAlchemy, asyncpg wants `postgresql://...`.
    If your url is already `postgresql://...`, this is a no-op.
    """
    return url.replace("postgresql+asyncpg://", "postgresql://", 1)


async def init_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        dsn = _normalize_asyncpg_dsn(settings.database_url)
        _pool = await asyncpg.create_pool(
            dsn=dsn,
            min_size=1,
            max_size=10,
            command_timeout=30,
        )
    return _pool


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


async def get_pool() -> asyncpg.Pool:
    if _pool is None:
        return await init_pool()
    return _pool
