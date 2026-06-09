"""Recall pipeline (TRD §9.2-9.3).

Pulls top-k×2 by raw cosine from pgvector, re-ranks with the decay
score, and fires an async access-bump that does NOT block the reply.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from app.agents.qwen_client import embed
from app.memory.db import get_pool
from app.memory.score import compute_memory_score

log = logging.getLogger(__name__)

_RECALL_SQL = """
SELECT id, patient_id, content, memory_type, importance_score,
       access_count, last_accessed_at,
       1 - (embedding <=> $1::vector) AS similarity
FROM patient_memories
WHERE patient_id = $2
ORDER BY embedding <=> $1::vector
LIMIT $3
"""

_BUMP_SQL = """
UPDATE patient_memories
SET access_count = access_count + 1,
    last_accessed_at = NOW()
WHERE id = ANY($1::uuid[])
"""


async def _bump_access(ids: list[str]) -> None:
    if not ids:
        return
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute(_BUMP_SQL, ids)
    except Exception:
        log.exception("memory access bump failed")


async def recall_memories(
    patient_id: str,
    query: str,
    top_k: int = 5,
) -> list[dict[str, Any]]:
    vec = await embed(query)
    # asyncpg would send list[float] as real[] which can't cast to vector;
    # pgvector accepts its text repr `[v1,v2,…]` which $1::vector then parses.
    vec_literal = "[" + ",".join(repr(float(x)) for x in vec) + "]"
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(_RECALL_SQL, vec_literal, patient_id, top_k * 2)

    scored = []
    for r in rows:
        s = compute_memory_score(
            similarity=float(r["similarity"]),
            importance=float(r["importance_score"] or 0.0),
            access_count=int(r["access_count"] or 0),
            last_accessed=r["last_accessed_at"],
        )
        scored.append((s, r))

    scored.sort(key=lambda t: t[0], reverse=True)
    top = scored[:top_k]

    # Fire-and-forget access bump — never block the reply on this.
    asyncio.create_task(_bump_access([str(r["id"]) for _, r in top]))

    return [
        {
            "id": str(r["id"]),
            "content": r["content"],
            "memory_type": r["memory_type"],
            "score": s,
        }
        for s, r in top
    ]
