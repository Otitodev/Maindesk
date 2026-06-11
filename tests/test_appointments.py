"""Tests for app/tools/appointments — status filter and double-booking guard."""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import asyncpg
import pytest

from app.gateway.schema import PatientMessage
from app.tools.appointments import book, suggest_slots


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
