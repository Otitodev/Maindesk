"""Tests for app/tools/appointments — status filter and double-booking guard."""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import asyncpg
import pytest

from app.gateway.schema import PatientMessage
from app.tools.appointments import book, cancel, reschedule, suggest_slots


def _txn_cm():
    """A mock async context manager standing in for conn.transaction()."""
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=None)
    cm.__aexit__ = AsyncMock(return_value=False)
    return cm


def _msg() -> PatientMessage:
    return PatientMessage(
        message_id="m1", session_id="s1", channel="web", content="book appt"
    )


@pytest.fixture
def mock_pool(monkeypatch):
    conn = AsyncMock()
    pool = MagicMock()
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)
    monkeypatch.setattr("app.tools.appointments.get_pool", AsyncMock(return_value=pool))
    return conn


async def test_suggest_slots_sql_filters_only_booked(mock_pool):
    mock_pool.fetch.return_value = []
    await suggest_slots(_msg(), n=3)
    sql = mock_pool.fetch.call_args[0][0]
    assert "status = 'booked'" in sql


async def test_suggest_slots_returns_free_slots(mock_pool):
    mock_pool.fetch.return_value = []
    result = await suggest_slots(_msg(), n=3)
    assert result["tool"] == "suggest_slots"
    assert len(result["slots"]) == 3


async def test_suggest_slots_excludes_taken(mock_pool):
    from datetime import timedelta
    from zoneinfo import ZoneInfo
    from app.config import get_settings
    tz = ZoneInfo(get_settings().clinic_timezone)
    base = (datetime.now(tz) + timedelta(days=1)).replace(
        hour=9, minute=0, second=0, microsecond=0
    )
    first_slot = base
    mock_pool.fetch.return_value = [{"starts_at": first_slot}]
    result = await suggest_slots(_msg(), n=3)
    assert first_slot.isoformat() not in result["slots"]
    assert len(result["slots"]) == 3


async def test_book_success(mock_pool):
    mock_pool.fetchrow.return_value = {"id": "uuid-1"}
    ts = datetime(2026, 7, 1, 9, 0, tzinfo=timezone.utc)
    result = await book("patient-1", ts)
    assert result["tool"] == "book"
    assert result["id"] == "uuid-1"
    assert "error" not in result


async def test_book_slot_taken_returns_error(mock_pool):
    mock_pool.fetchrow.side_effect = asyncpg.UniqueViolationError()
    ts = datetime(2026, 7, 1, 9, 0, tzinfo=timezone.utc)
    result = await book("patient-1", ts)
    assert result["tool"] == "book"
    assert result["error"] == "slot_taken"
    assert result["starts_at"] == ts.isoformat()


async def test_suggest_slots_cancelled_slot_is_available(mock_pool):
    """A cancelled appointment at a given time must not block suggest_slots
    from offering that slot — consistent with the partial unique index which
    only enforces uniqueness for status='booked' rows."""
    mock_pool.fetch.return_value = []  # no booked rows — cancelled row not returned
    result = await suggest_slots(_msg(), n=3)
    # All 3 slots are available because cancelled rows are excluded from the query
    assert len(result["slots"]) == 3


# ── cancel ──────────────────────────────────────────────────────────────

async def test_cancel_success(mock_pool):
    ts = datetime(2026, 7, 1, 9, 0, tzinfo=timezone.utc)
    mock_pool.fetchrow.return_value = {"id": "appt-1", "starts_at": ts}
    result = await cancel("patient-1", "appt-1")
    assert result["tool"] == "cancel"
    assert result["status"] == "cancelled"
    assert result["id"] == "appt-1"
    # Scoped by patient_id and only touches booked rows.
    sql = mock_pool.fetchrow.call_args[0][0]
    assert "patient_id = $2" in sql
    assert "status = 'booked'" in sql


async def test_cancel_not_found(mock_pool):
    mock_pool.fetchrow.return_value = None
    result = await cancel("patient-1", "missing")
    assert result["error"] == "not_found"


# ── reschedule (atomic: book-new-then-cancel-old) ───────────────────────

async def test_reschedule_success(mock_pool):
    mock_pool.transaction = MagicMock(return_value=_txn_cm())
    # 1st fetchrow: SELECT existing (found); 2nd: INSERT new slot.
    mock_pool.fetchrow.side_effect = [{"id": "old-1"}, {"id": "new-1"}]
    mock_pool.execute = AsyncMock()
    ts = datetime(2026, 7, 1, 10, 0, tzinfo=timezone.utc)
    result = await reschedule("patient-1", "old-1", ts)
    assert result["tool"] == "reschedule"
    assert result["id"] == "new-1"
    assert result["old_appointment_id"] == "old-1"
    assert result["starts_at"] == ts.isoformat()
    assert "error" not in result
    mock_pool.execute.assert_awaited_once()  # old row cancelled


async def test_reschedule_not_found(mock_pool):
    mock_pool.transaction = MagicMock(return_value=_txn_cm())
    mock_pool.fetchrow.return_value = None  # SELECT existing → not found
    mock_pool.execute = AsyncMock()
    ts = datetime(2026, 7, 1, 10, 0, tzinfo=timezone.utc)
    result = await reschedule("patient-1", "missing", ts)
    assert result["error"] == "not_found"
    mock_pool.execute.assert_not_awaited()  # never cancelled the old row


async def test_reschedule_slot_taken_keeps_original(mock_pool):
    """If the new slot clashes, the INSERT raises and the whole transaction
    rolls back — the original appointment is never cancelled."""
    mock_pool.transaction = MagicMock(return_value=_txn_cm())
    mock_pool.fetchrow.side_effect = [{"id": "old-1"}, asyncpg.UniqueViolationError()]
    mock_pool.execute = AsyncMock()
    ts = datetime(2026, 7, 1, 10, 0, tzinfo=timezone.utc)
    result = await reschedule("patient-1", "old-1", ts)
    assert result["error"] == "slot_taken"
    mock_pool.execute.assert_not_awaited()
