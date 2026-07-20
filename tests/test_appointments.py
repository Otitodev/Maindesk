"""Tests for app/tools/appointments — status filter and double-booking guard."""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import asyncpg
import pytest

from app.gateway.schema import PatientMessage
from app.tools.appointments import book, cancel, find_existing, reschedule, suggest_slots


def _txn_cm():
    """A mock async context manager standing in for conn.transaction()."""
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=None)
    cm.__aexit__ = AsyncMock(return_value=False)
    return cm


class _FakeProvider:
    """In-memory calendar provider for mirror/busy assertions — no network."""

    def __init__(self, busy=None, event_id="evt-1", fail=False):
        self.busy = busy or []
        self.event_id = event_id
        self.fail = fail
        self.created = []
        self.moved = []
        self.cancelled = []

    async def busy_intervals(self, start, end):
        return self.busy

    async def create_event(self, patient_id, starts_at, *, duration_minutes):
        if self.fail:
            raise RuntimeError("calendar down")
        self.created.append((patient_id, starts_at))
        return self.event_id

    async def move_event(self, event_id, new_starts_at, *, duration_minutes):
        if self.fail:
            raise RuntimeError("calendar down")
        self.moved.append((event_id, new_starts_at))

    async def cancel_event(self, event_id):
        if self.fail:
            raise RuntimeError("calendar down")
        self.cancelled.append(event_id)


def _use_provider(monkeypatch, provider):
    monkeypatch.setattr("app.tools.appointments.get_provider", lambda: provider)


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


def _candidates():
    """The slot stream suggest_slots draws from, computed the same way."""
    from zoneinfo import ZoneInfo
    from app import clinic_config
    from app.tools.appointments import _business_slots
    cfg = clinic_config.current()
    return _business_slots(cfg, ZoneInfo(cfg["timezone"])), cfg


async def test_suggest_slots_returns_free_slots(mock_pool):
    mock_pool.fetch.return_value = []
    result = await suggest_slots(_msg(), n=3)
    assert result["tool"] == "suggest_slots"
    assert len(result["slots"]) == 3


async def test_suggest_slots_within_business_hours():
    cands, cfg = _candidates()
    assert cands, "expected upcoming business slots"
    now = datetime.now(cands[0].tzinfo)
    for slot in cands[:50]:
        assert slot > now
        assert cfg["open_hour"] <= slot.hour < cfg["close_hour"]
        assert slot.isoweekday() in cfg["working_days"]


async def test_suggest_slots_excludes_taken(mock_pool):
    cands, _ = _candidates()
    first = cands[0]
    mock_pool.fetch.return_value = [{"starts_at": first}]  # first slot booked
    result = await suggest_slots(_msg(), n=3)
    assert first.isoformat() not in result["slots"]
    assert len(result["slots"]) == 3


async def test_suggest_slots_excludes_calendar_busy(mock_pool, monkeypatch):
    from datetime import timedelta
    cands, cfg = _candidates()
    first = cands[0]
    mock_pool.fetch.return_value = []  # nothing booked in Postgres
    # Calendar reports the first slot's window as busy (staff blocked).
    _use_provider(monkeypatch, _FakeProvider(
        busy=[(first, first + timedelta(minutes=cfg["slot_minutes"]))]
    ))
    result = await suggest_slots(_msg(), n=3)
    assert first.isoformat() not in result["slots"]
    assert len(result["slots"]) == 3


async def test_book_success(mock_pool):
    mock_pool.fetchrow.return_value = {"id": "uuid-1"}
    ts = datetime(2026, 7, 1, 9, 0, tzinfo=timezone.utc)
    result = await book("patient-1", ts)
    assert result["tool"] == "book"
    assert result["id"] == "uuid-1"
    assert "error" not in result


async def test_book_passes_reason_to_insert(mock_pool):
    mock_pool.fetchrow.return_value = {"id": "uuid-1"}
    ts = datetime(2026, 7, 1, 9, 0, tzinfo=timezone.utc)
    await book("patient-1", ts, reason="annual checkup")
    args = mock_pool.fetchrow.call_args[0]
    assert args[1] == "patient-1"
    assert args[2] == ts
    assert args[3] == "annual checkup"


async def test_book_without_reason_stores_none(mock_pool):
    mock_pool.fetchrow.return_value = {"id": "uuid-1"}
    ts = datetime(2026, 7, 1, 9, 0, tzinfo=timezone.utc)
    await book("patient-1", ts)
    args = mock_pool.fetchrow.call_args[0]
    assert args[3] is None


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


async def test_find_existing_includes_reason(mock_pool):
    ts = datetime(2026, 7, 1, 9, 0, tzinfo=timezone.utc)
    mock_pool.fetch.return_value = [
        {"id": "a1", "starts_at": ts, "status": "booked", "notes": "annual checkup"}
    ]
    msg = PatientMessage(
        message_id="m1", session_id="s1", patient_id="patient-1",
        channel="web", content="book appt",
    )
    result = await find_existing(msg)
    assert result["appointments"][0]["reason"] == "annual checkup"


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


async def test_reschedule_carries_reason_to_new_slot(mock_pool):
    """The reason-for-visit is the same visit, just moved — carry it over."""
    mock_pool.transaction = MagicMock(return_value=_txn_cm())
    mock_pool.fetchrow.side_effect = [
        {"id": "old-1", "calendar_event_id": None, "notes": "sore throat"},
        {"id": "new-1"},
    ]
    mock_pool.execute = AsyncMock()
    ts = datetime(2026, 7, 1, 10, 0, tzinfo=timezone.utc)
    await reschedule("patient-1", "old-1", ts)
    insert_args = mock_pool.fetchrow.call_args_list[1][0]
    assert insert_args[3] == "sore throat"


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


# ── calendar mirroring (best-effort; never fails a booking) ──────────────

async def test_book_mirrors_to_calendar(mock_pool, monkeypatch):
    provider = _FakeProvider(event_id="gcal-1")
    _use_provider(monkeypatch, provider)
    mock_pool.fetchrow.return_value = {"id": "uuid-1"}
    ts = datetime(2026, 7, 1, 9, 0, tzinfo=timezone.utc)
    result = await book("patient-1", ts)
    assert result["id"] == "uuid-1"
    assert provider.created == [("patient-1", ts)]
    # event id written back onto the appointment row
    mock_pool.execute.assert_awaited_with(
        "UPDATE appointments SET calendar_event_id = $1 WHERE id = $2", "gcal-1", "uuid-1"
    )


async def test_book_mirror_failure_is_nonfatal(mock_pool, monkeypatch):
    _use_provider(monkeypatch, _FakeProvider(fail=True))
    mock_pool.fetchrow.return_value = {"id": "uuid-1"}
    ts = datetime(2026, 7, 1, 9, 0, tzinfo=timezone.utc)
    result = await book("patient-1", ts)
    # Booking still succeeds even though the calendar mirror raised.
    assert result["id"] == "uuid-1"
    assert "error" not in result


async def test_cancel_mirrors_calendar_delete(mock_pool, monkeypatch):
    provider = _FakeProvider()
    _use_provider(monkeypatch, provider)
    ts = datetime(2026, 7, 1, 9, 0, tzinfo=timezone.utc)
    mock_pool.fetchrow.return_value = {
        "id": "appt-1", "starts_at": ts, "calendar_event_id": "gcal-9"
    }
    result = await cancel("patient-1", "appt-1")
    assert result["status"] == "cancelled"
    assert provider.cancelled == ["gcal-9"]


async def test_reschedule_mirrors_calendar_move(mock_pool, monkeypatch):
    provider = _FakeProvider()
    _use_provider(monkeypatch, provider)
    mock_pool.transaction = MagicMock(return_value=_txn_cm())
    mock_pool.fetchrow.side_effect = [
        {"id": "old-1", "calendar_event_id": "gcal-7"},  # SELECT existing
        {"id": "new-1"},                                  # INSERT new slot
    ]
    mock_pool.execute = AsyncMock()
    ts = datetime(2026, 7, 1, 10, 0, tzinfo=timezone.utc)
    result = await reschedule("patient-1", "old-1", ts)
    assert result["id"] == "new-1"
    assert provider.moved == [("gcal-7", ts)]  # same event moved, not recreated
