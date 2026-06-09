"""Memory write-back (TRD §9.4).

Called from the writer node via asyncio.create_task so the patient gets
their reply before this finishes. Failures are logged, never raised.
"""

from __future__ import annotations

import logging

from app.agents.qwen_client import complete, embed
from app.config import get_settings
from app.memory.db import get_pool

log = logging.getLogger(__name__)

_INSERT_SQL = """
INSERT INTO patient_memories
  (patient_id, content, memory_type, importance_score, source_session_id)
VALUES ($1, $2, $3, $4, $5)
RETURNING id
"""

_INSERT_EMBEDDING_SQL = """
UPDATE patient_memories SET embedding = $1::vector WHERE id = $2
"""

_SUMMARISE_SYSTEM = (
    "Summarise this clinic-patient exchange in one factual sentence the front "
    "desk should remember next time. No greetings, no apologies."
)


async def _summarise(user_text: str, assistant_text: str) -> str:
    s = get_settings()
    body = f"PATIENT: {user_text}\nDESK: {assistant_text}"
    try:
        return await complete(
            model=s.qwen_model_turbo,
            system=_SUMMARISE_SYSTEM,
            user=body,
            temperature=0.0,
            max_tokens=80,
        )
    except Exception:
        log.exception("summarise failed; storing raw exchange")
        return body[:500]


async def persist_turn(
    *,
    patient_id: str,
    session_id: str,
    user_text: str,
    assistant_text: str,
    importance: float,
    intent: str,
) -> None:
    try:
        summary = await _summarise(user_text, assistant_text)
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                _INSERT_SQL,
                patient_id,
                summary,
                intent,
                importance,
                session_id,
            )
            mem_id = row["id"]
        # Embed AFTER inserting so the row exists even if embedding fails.
        vec = await embed(summary)
        vec_literal = "[" + ",".join(repr(float(x)) for x in vec) + "]"
        async with pool.acquire() as conn:
            await conn.execute(_INSERT_EMBEDDING_SQL, vec_literal, mem_id)
    except Exception:
        log.exception("persist_turn failed (patient=%s)", patient_id)
