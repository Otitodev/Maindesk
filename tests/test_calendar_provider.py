"""Tests for the calendar provider factory — selection and safe fallback."""
from __future__ import annotations

import pytest

from app.config import get_settings
from app.tools import calendar as cal
from app.tools.calendar.stub import StubCalendarProvider


def _reset_caches():
    get_settings.cache_clear()
    cal.get_provider.cache_clear()


async def test_falls_back_to_stub_without_creds(monkeypatch):
    monkeypatch.delenv("GOOGLE_CALENDAR_ID", raising=False)
    monkeypatch.delenv("GOOGLE_SERVICE_ACCOUNT_JSON", raising=False)
    _reset_caches()
    assert isinstance(cal.get_provider(), StubCalendarProvider)
    _reset_caches()


async def test_falls_back_to_stub_on_bad_creds(monkeypatch):
    # Calendar id set but the service-account value is unusable → must not
    # crash the app; fall back to the stub so scheduling still works.
    monkeypatch.setenv("GOOGLE_CALENDAR_ID", "clinic@group.calendar.google.com")
    monkeypatch.setenv("GOOGLE_SERVICE_ACCOUNT_JSON", "{not valid json")
    _reset_caches()
    assert isinstance(cal.get_provider(), StubCalendarProvider)
    _reset_caches()


async def test_stub_reports_nothing_busy_and_no_events():
    stub = StubCalendarProvider()
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    assert await stub.busy_intervals(now, now) == []
    assert await stub.create_event("p-1", now, duration_minutes=30) is None
    assert await stub.move_event("e", now, duration_minutes=30) is None
    assert await stub.cancel_event("e") is None
