"""Appointment tool stubs.

The hackathon demo uses a Supabase-backed appointments table; full
calendar integration is out of scope. These are deterministic enough
for the demo and easy to swap for a real backend later.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from app.gateway.schema import PatientMessage
from app.memory.db import get_pool

log = logging.getLogger(__name__)


async def suggest_slots(_msg: PatientMessage, *, n: int = 3) -> dict[str, Any]:
    """Return the next `n` open 30-min slots starting tomorrow 09:00 local-UTC."""
    pool = await get_pool()
    base = (datetime.now(timezone.utc) + timedelta(days=1)).replace(
        hour=9, minute=0, second=0, microsecond=0
    )
    candidates = [base + timedelta(minutes=30 * i) for i in range(n * 4)]
    async with pool.acquire() as conn:
        taken = {
            r["starts_at"]
            for r in await conn.fetch(
                "SELECT starts_at FROM appointments WHERE starts_at = ANY($1::timestamptz[])",
                candidates,
            )
        }
    free = [c.isoformat() for c in candidates if c not in taken][:n]
    return {"tool": "suggest_slots", "slots": free}


async def find_existing(msg: PatientMessage) -> dict[str, Any]:
    if not msg.patient_id:
        return {"tool": "find_existing", "appointments": []}
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT id, starts_at, status FROM appointments "
            "WHERE patient_id = $1 AND starts_at >= NOW() ORDER BY starts_at LIMIT 5",
            msg.patient_id,
        )
    return {
        "tool": "find_existing",
        "appointments": [
            {"id": str(r["id"]), "starts_at": r["starts_at"].isoformat(), "status": r["status"]}
            for r in rows
        ],
    }


async def book(patient_id: str, starts_at: datetime) -> dict[str, Any]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "INSERT INTO appointments (patient_id, starts_at, status) "
            "VALUES ($1, $2, 'booked') RETURNING id",
            patient_id,
            starts_at,
        )
    return {"tool": "book", "id": str(row["id"]), "starts_at": starts_at.isoformat()}
