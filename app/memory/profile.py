"""Patient profile read/write (TRD §9).

Profile is structured data the agent looks up by phone/email before
the LangGraph triage runs — it's where `patient_id` comes from.
"""

from __future__ import annotations

import logging
from typing import Any

from app.memory.db import get_pool

log = logging.getLogger(__name__)


async def resolve_by_phone(phone: str) -> dict[str, Any] | None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id, full_name, phone, email, preferences "
            "FROM patients WHERE phone = $1",
            phone,
        )
    return dict(row) if row else None


async def resolve_by_email(email: str) -> dict[str, Any] | None:
    """Look up a patient by email. Email isn't unique in the schema, so the
    oldest matching profile wins (deterministic). Returns None on no match —
    the email channel then runs without identity, like the web widget."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id, full_name, phone, email, preferences "
            "FROM patients WHERE email = $1 ORDER BY created_at LIMIT 1",
            email,
        )
    return dict(row) if row else None


async def upsert_profile(
    *,
    phone: str,
    full_name: str | None = None,
    email: str | None = None,
) -> str:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO patients (phone, full_name, email)
            VALUES ($1, $2, $3)
            ON CONFLICT (phone) DO UPDATE
              SET full_name = COALESCE(EXCLUDED.full_name, patients.full_name),
                  email = COALESCE(EXCLUDED.email, patients.email)
            RETURNING id
            """,
            phone,
            full_name,
            email,
        )
    return str(row["id"])
