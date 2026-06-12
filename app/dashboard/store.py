"""Escalation persistence for the staff dashboard (human-in-the-loop).

All writes are best-effort: the agent must never fail a patient turn
because the dashboard's database is unreachable.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from app.gateway.schema import PatientMessage
from app.memory.db import get_pool

log = logging.getLogger(__name__)

ACTION_TO_STATUS = {
    "approve": "approved",
    "redirect": "redirected",
    "close": "closed",
}


def _as_uuid(value: str | None) -> uuid.UUID | None:
    if not value:
        return None
    try:
        return uuid.UUID(value)
    except ValueError:
        return None


async def record_escalation(
    msg: PatientMessage, *, reason: str, delivered: bool
) -> str | None:
    """Insert an open escalation; returns its id, or None if DB is down."""
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "INSERT INTO escalations "
                "(session_id, reason, delivered, channel, patient_id, message_preview) "
                "VALUES ($1, $2, $3, $4, $5, $6) RETURNING id",
                msg.session_id,
                reason,
                delivered,
                msg.channel,
                _as_uuid(msg.patient_id),
                msg.content[:300],
            )
        return str(row["id"])
    except Exception:
        log.warning("could not persist escalation (dashboard will miss it)", exc_info=True)
        return None


async def list_escalations(*, limit: int = 25) -> list[dict[str, Any]]:
    """Open escalations first (oldest waiting on top), then recent resolved."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT e.id, e.session_id, e.reason, e.channel, e.message_preview, "
            "       e.status, e.note, e.created_at, e.resolved_at, p.full_name "
            "FROM escalations e LEFT JOIN patients p ON p.id = e.patient_id "
            "ORDER BY (e.status = 'open') DESC, "
            "         CASE WHEN e.status = 'open' THEN e.created_at END ASC, "
            "         e.resolved_at DESC "
            "LIMIT $1",
            limit,
        )
    return [dict(r) for r in rows]


async def resolve_escalation(esc_id: str, *, action: str, note: str = "") -> bool:
    """Apply a staff action to an open escalation. Returns False if already handled."""
    status = ACTION_TO_STATUS.get(action)
    if status is None or _as_uuid(esc_id) is None:
        return False
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "UPDATE escalations SET status = $2, note = NULLIF($3, ''), resolved_at = NOW() "
            "WHERE id = $1 AND status = 'open' RETURNING id",
            uuid.UUID(esc_id),
            status,
            note.strip(),
        )
    return row is not None


async def recent_bookings(*, limit: int = 8) -> list[dict[str, Any]]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT a.id, a.starts_at, a.status, a.created_at, p.full_name "
            "FROM appointments a LEFT JOIN patients p ON p.id = a.patient_id "
            "WHERE a.starts_at >= NOW() "
            "ORDER BY a.created_at DESC LIMIT $1",
            limit,
        )
    return [dict(r) for r in rows]
