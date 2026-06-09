"""Async Postgres pool for memory ops (TRD §9).

We use raw asyncpg rather than SQLAlchemy: queries are few, hot, and
all parameterised. Pool is created lazily and re-used.
"""

from __future__ import annotations

from typing import Optional

import asyncpg

from app.config import get_settings

_pool: Optional[asyncpg.Pool] = None


async def get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        s = get_settings()
        _pool = await asyncpg.create_pool(
            dsn=s.database_url,
            min_size=1,
            max_size=10,
        )
    return _pool


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None
