"""Tests for GoogleCalendarProvider with httpx + auth mocked (no network).

Verifies the Calendar v3 request shapes and response parsing: free/busy
intervals, event creation id, and idempotent (410-tolerant) cancel.
"""
from __future__ import annotations

from datetime import datetime, timezone

import httpx
import pytest

from app.tools.calendar.google import GoogleCalendarProvider


class _Creds:
    valid = True
    token = "tok"

    def refresh(self, request):  # pragma: no cover - never called when valid
        pass


class _Resp:
    def __init__(self, json_data=None, status_code=200):
        self._json = json_data or {}
        self.status_code = status_code

    def json(self):
        return self._json

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("error", request=None, response=None)


class _Client:
    """Stand-in for httpx.AsyncClient — records calls, returns scripted resp."""

    calls: list[tuple[str, str, dict]] = []

    def __init__(self, response):
        self._response = response

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def _record(self, method, url, **kw):
        _Client.calls.append((method, url, kw))
        return self._response

    async def post(self, url, **kw):
        return await self._record("POST", url, **kw)

    async def patch(self, url, **kw):
        return await self._record("PATCH", url, **kw)

    async def delete(self, url, **kw):
        return await self._record("DELETE", url, **kw)


def _patch_httpx(monkeypatch, response):
    _Client.calls = []
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: _Client(response))


def _provider():
    return GoogleCalendarProvider("clinic@group.calendar.google.com", _Creds())


async def test_busy_intervals_parsed(monkeypatch):
    resp = _Resp({"calendars": {"clinic@group.calendar.google.com": {"busy": [
        {"start": "2026-07-01T09:00:00Z", "end": "2026-07-01T09:30:00Z"},
    ]}}})
    _patch_httpx(monkeypatch, resp)
    start = datetime(2026, 7, 1, 8, tzinfo=timezone.utc)
    end = datetime(2026, 7, 1, 18, tzinfo=timezone.utc)
    busy = await _provider().busy_intervals(start, end)
    assert busy == [(
        datetime(2026, 7, 1, 9, 0, tzinfo=timezone.utc),
        datetime(2026, 7, 1, 9, 30, tzinfo=timezone.utc),
    )]
    method, url, _ = _Client.calls[0]
    assert method == "POST" and url.endswith("/freeBusy")


async def test_create_event_returns_id(monkeypatch):
    _patch_httpx(monkeypatch, _Resp({"id": "gcal-123"}))
    ts = datetime(2026, 7, 1, 9, tzinfo=timezone.utc)
    event_id = await _provider().create_event("p-1", ts, duration_minutes=30)
    assert event_id == "gcal-123"
    method, url, kw = _Client.calls[0]
    assert method == "POST" and url.endswith("/events")
    assert kw["json"]["start"]["dateTime"] == ts.isoformat()


async def test_cancel_event_tolerates_410(monkeypatch):
    # Already-deleted event → 410; must be treated as success, not raised.
    _patch_httpx(monkeypatch, _Resp(status_code=410))
    await _provider().cancel_event("gone-1")  # should not raise
    assert _Client.calls[0][0] == "DELETE"
