"""Appointment tools.

Postgres is the booking ledger and the authoritative no-double-booking guard
(partial unique index on status='booked'). A pluggable calendar provider
(app.tools.calendar) supplies real availability (free/busy) and a best-effort
staff-visible mirror of every booking. Mirror calls never fail a booking —
Postgres remains the source of truth.

The public functions (suggest_slots / find_existing / history / book / cancel /
reschedule) keep their signatures and dict return shapes, so the LangGraph
tools node, the voice worker, and the MCP server are unaffected.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import asyncpg

from app import clinic_config
from app.gateway.schema import PatientMessage
from app.memory.db import get_pool
from app.tools.calendar import get_provider

log = logging.getLogger(__name__)


def _business_slots(cfg: dict, tz: ZoneInfo) -> list[datetime]:
    """Upcoming slot start times within the clinic's working days and hours,
    strictly in the future, ordered soonest-first. `cfg` is a clinic-config
    dict (see app.clinic_config)."""
    now = datetime.now(tz)
    slot_minutes = cfg["slot_minutes"]
    out: list[datetime] = []
    for day_offset in range(cfg["search_days"]):
        day = (now + timedelta(days=day_offset)).date()
        if day.isoweekday() not in cfg["working_days"]:
            continue
        t = datetime(day.year, day.month, day.day, cfg["open_hour"], 0, tzinfo=tz)
        close = datetime(day.year, day.month, day.day, cfg["close_hour"], 0, tzinfo=tz)
        while t < close:
            if t > now:
                out.append(t)
            t += timedelta(minutes=slot_minutes)
    return out


async def suggest_slots(_msg: PatientMessage, *, n: int = 3) -> dict[str, Any]:
    """Return the next `n` open slots within the clinic's business hours,
    excluding both Postgres-booked times and calendar busy intervals."""
    cfg = clinic_config.current()
    tz = ZoneInfo(cfg["timezone"])
    slot_minutes = cfg["slot_minutes"]

    candidates = _business_slots(cfg, tz)
    if not candidates:
        return {"tool": "suggest_slots", "slots": []}
    # Only check a bounded window — enough to find n free slots after exclusions.
    window = candidates[: max(n * 8, n)]

    pool = await get_pool()
    async with pool.acquire() as conn:
        taken = {
            r["starts_at"]
            for r in await conn.fetch(
                "SELECT starts_at FROM appointments "
                "WHERE starts_at = ANY($1::timestamptz[]) AND status = 'booked'",
                window,
            )
        }

    busy: list[tuple[datetime, datetime]] = []
    try:
        busy = await get_provider().busy_intervals(
            window[0], window[-1] + timedelta(minutes=slot_minutes)
        )
    except Exception:
        log.warning("calendar busy lookup failed; using DB availability only", exc_info=True)

    def _is_busy(slot: datetime) -> bool:
        slot_end = slot + timedelta(minutes=slot_minutes)
        return any(slot < b_end and b_start < slot_end for b_start, b_end in busy)

    free = [c.isoformat() for c in window if c not in taken and not _is_busy(c)][:n]
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


async def history(patient_id: str, *, limit: int = 10) -> dict[str, Any]:
    """Upcoming and past appointments for a patient (MCP + dashboard)."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        upcoming = await conn.fetch(
            "SELECT id, starts_at, status FROM appointments "
            "WHERE patient_id = $1 AND starts_at >= NOW() ORDER BY starts_at ASC LIMIT $2",
            patient_id,
            limit,
        )
        past = await conn.fetch(
            "SELECT id, starts_at, status FROM appointments "
            "WHERE patient_id = $1 AND starts_at < NOW() ORDER BY starts_at DESC LIMIT $2",
            patient_id,
            limit,
        )

    def _rows(rows):
        return [
            {"id": str(r["id"]), "starts_at": r["starts_at"].isoformat(), "status": r["status"]}
            for r in rows
        ]

    return {"tool": "history", "upcoming": _rows(upcoming), "past": _rows(past)}


# ── Calendar mirroring (best-effort; never fails a booking) ──────────────────


async def _set_event_id(appointment_id: str, event_id: str) -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE appointments SET calendar_event_id = $1 WHERE id = $2",
            event_id,
            appointment_id,
        )


async def _mirror_create(appointment_id: str, patient_id: str, starts_at: datetime) -> None:
    duration = clinic_config.current()["slot_minutes"]
    try:
        event_id = await get_provider().create_event(
            patient_id, starts_at, duration_minutes=duration
        )
        if event_id:
            await _set_event_id(appointment_id, event_id)
    except Exception:
        log.warning("calendar mirror (create) failed appt=%s", appointment_id, exc_info=True)


async def _mirror_move(
    appointment_id: str, old_event_id: str | None, patient_id: str, new_starts_at: datetime
) -> None:
    duration = clinic_config.current()["slot_minutes"]
    try:
        provider = get_provider()
        if old_event_id:
            await provider.move_event(
                old_event_id, new_starts_at, duration_minutes=duration
            )
            event_id = old_event_id
        else:
            event_id = await provider.create_event(
                patient_id, new_starts_at, duration_minutes=duration
            )
        if event_id:
            await _set_event_id(appointment_id, event_id)
    except Exception:
        log.warning("calendar mirror (move) failed appt=%s", appointment_id, exc_info=True)


async def _mirror_cancel(event_id: str | None) -> None:
    if not event_id:
        return
    try:
        await get_provider().cancel_event(event_id)
    except Exception:
        log.warning("calendar mirror (cancel) failed event=%s", event_id, exc_info=True)


# ── Mutations ────────────────────────────────────────────────────────────────


async def book(patient_id: str, starts_at: datetime) -> dict[str, Any]:
    pool = await get_pool()
    try:
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "INSERT INTO appointments (patient_id, starts_at, status) "
                "VALUES ($1, $2, 'booked') RETURNING id",
                patient_id,
                starts_at,
            )
    except asyncpg.UniqueViolationError:
        log.warning("double-booking attempted patient=%s starts_at=%s", patient_id, starts_at)
        return {"tool": "book", "error": "slot_taken", "starts_at": starts_at.isoformat()}
    appointment_id = str(row["id"])
    await _mirror_create(appointment_id, patient_id, starts_at)
    return {"tool": "book", "id": appointment_id, "starts_at": starts_at.isoformat()}


async def cancel(patient_id: str, appointment_id: str) -> dict[str, Any]:
    """Cancel a booked appointment. Scoped by patient_id so one caller can
    never cancel another patient's slot. Idempotent-ish: a row that is not
    found or already cancelled returns an explicit not_found error rather
    than silently succeeding."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "UPDATE appointments SET status = 'cancelled' "
            "WHERE id = $1 AND patient_id = $2 AND status = 'booked' "
            "RETURNING id, starts_at, calendar_event_id",
            appointment_id,
            patient_id,
        )
    if row is None:
        return {"tool": "cancel", "error": "not_found", "appointment_id": appointment_id}
    await _mirror_cancel(row.get("calendar_event_id"))
    return {
        "tool": "cancel",
        "id": str(row["id"]),
        "starts_at": row["starts_at"].isoformat(),
        "status": "cancelled",
    }


async def reschedule(
    patient_id: str, appointment_id: str, new_starts_at: datetime
) -> dict[str, Any]:
    """Atomically move a booked appointment to a new time.

    The new slot is secured *before* the old one is released, both inside a
    single transaction: if the replacement slot clashes (partial unique index
    on booked rows) the whole thing rolls back, so we never cancel the
    original without having booked its replacement."""
    pool = await get_pool()
    try:
        async with pool.acquire() as conn:
            async with conn.transaction():
                existing = await conn.fetchrow(
                    "SELECT id, calendar_event_id FROM appointments "
                    "WHERE id = $1 AND patient_id = $2 AND status = 'booked' "
                    "FOR UPDATE",
                    appointment_id,
                    patient_id,
                )
                if existing is None:
                    return {
                        "tool": "reschedule",
                        "error": "not_found",
                        "appointment_id": appointment_id,
                    }
                new_row = await conn.fetchrow(
                    "INSERT INTO appointments (patient_id, starts_at, status) "
                    "VALUES ($1, $2, 'booked') RETURNING id",
                    patient_id,
                    new_starts_at,
                )
                await conn.execute(
                    "UPDATE appointments SET status = 'cancelled' WHERE id = $1",
                    appointment_id,
                )
    except asyncpg.UniqueViolationError:
        log.warning(
            "reschedule slot taken patient=%s new=%s", patient_id, new_starts_at
        )
        return {
            "tool": "reschedule",
            "error": "slot_taken",
            "starts_at": new_starts_at.isoformat(),
        }
    new_id = str(new_row["id"])
    await _mirror_move(new_id, existing.get("calendar_event_id"), patient_id, new_starts_at)
    return {
        "tool": "reschedule",
        "id": new_id,
        "old_appointment_id": appointment_id,
        "starts_at": new_starts_at.isoformat(),
    }
