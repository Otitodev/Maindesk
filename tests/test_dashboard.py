"""Tests for the /staff human-in-the-loop dashboard."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

import app.dashboard.store as store_mod
import app.main as main_mod
from app.config import get_settings
from app.dashboard import events
from app.gateway.schema import PatientMessage, PatientReply
from app.tools.escalation import notify_staff

ESC_ID = uuid.UUID("11111111-2222-3333-4444-555555555555")


class StubGraph:
    async def ainvoke(self, state, config=None):
        msg = state["message"]
        return {"reply": PatientReply(session_id=msg.session_id, channel=msg.channel, content="ok")}


@pytest.fixture
def client(monkeypatch):
    async def fake_build_graph(_app_state):
        return StubGraph()

    monkeypatch.setattr(main_mod, "build_graph", fake_build_graph)
    # Isolate from whatever DB happens to be reachable in this environment:
    # clinic_config.refresh() runs at app startup regardless of these tests'
    # own store-level FakePool mocking, and a real, live Postgres would leak
    # its connection pool across the (function-scoped) event loops these
    # tests run under.
    monkeypatch.setattr("app.clinic_config.get_pool", AsyncMock(side_effect=RuntimeError("no db")))
    with TestClient(main_mod.app) as c:
        yield c


class FakeConn:
    """Canned-response asyncpg connection. Records every query."""

    def __init__(self, fetch_rows=None, fetchrow_row=None):
        self.fetch_rows = fetch_rows or []
        self.fetchrow_row = fetchrow_row
        self.queries: list[tuple] = []

    async def fetch(self, query, *args):
        self.queries.append((query, args))
        return self.fetch_rows

    async def fetchrow(self, query, *args):
        self.queries.append((query, args))
        return self.fetchrow_row


class FakePool:
    def __init__(self, conn):
        self._conn = conn

    def acquire(self):
        conn = self._conn

        class _Ctx:
            async def __aenter__(self):
                return conn

            async def __aexit__(self, *exc):
                return False

        return _Ctx()


def _patch_pool(monkeypatch, conn):
    async def fake_get_pool():
        return FakePool(conn)

    monkeypatch.setattr(store_mod, "get_pool", fake_get_pool)
    return conn


def _open_escalation_row():
    return {
        "id": ESC_ID,
        "session_id": "whatsapp:+23480000",
        "reason": "patient asked for a human",
        "channel": "whatsapp",
        "message_preview": "<script>alert(1)</script> I need help",
        "status": "open",
        "note": None,
        "created_at": datetime(2026, 6, 12, 9, 30, tzinfo=timezone.utc),
        "resolved_at": None,
        "full_name": "Adaeze Okafor",
    }


def test_staff_index_serves_page(client):
    r = client.get("/staff")
    assert r.status_code == 200
    assert "MainDesk — Overview" in r.text
    assert "sse-connect" in r.text


def test_queue_renders_open_escalation_with_actions(client, monkeypatch):
    _patch_pool(monkeypatch, FakeConn(fetch_rows=[_open_escalation_row()]))
    r = client.get("/staff/queue")
    assert r.status_code == 200
    assert "Adaeze Okafor" in r.text
    assert "patient asked for a human" in r.text
    for label in ("Approve", "Redirect to doctor", "Close"):
        assert label in r.text


def test_queue_escapes_patient_content(client, monkeypatch):
    _patch_pool(monkeypatch, FakeConn(fetch_rows=[_open_escalation_row()]))
    r = client.get("/staff/queue")
    assert "<script>" not in r.text
    assert "&lt;script&gt;" in r.text


def test_queue_survives_db_down(client, monkeypatch):
    async def boom():
        raise OSError("no postgres")

    monkeypatch.setattr(store_mod, "get_pool", boom)
    r = client.get("/staff/queue")
    assert r.status_code == 200
    assert "not reachable" in r.text


def test_action_resolves_and_returns_queue(client, monkeypatch):
    conn = _patch_pool(
        monkeypatch, FakeConn(fetch_rows=[], fetchrow_row={"id": ESC_ID})
    )
    r = client.post(
        f"/staff/escalations/{ESC_ID}",
        content="action=approve&note=called+the+patient",
        headers={"content-type": "application/x-www-form-urlencoded"},
    )
    assert r.status_code == 200
    # resolve_escalation wraps the UPDATE in a CTE (`WITH updated AS (UPDATE ...)`)
    # so it can join patient contact info in the same round trip — match on
    # substring, not prefix.
    update = next(q for q in conn.queries if "UPDATE escalations" in q[0])
    assert update[1][0] == ESC_ID
    assert update[1][1] == "approved"
    assert update[1][2] == "called the patient"


def test_action_rejects_unknown_action(client):
    r = client.post(
        f"/staff/escalations/{ESC_ID}",
        content="action=delete_everything",
        headers={"content-type": "application/x-www-form-urlencoded"},
    )
    assert r.status_code == 422


def test_dashboard_key_enforced(client, monkeypatch):
    monkeypatch.setenv("STAFF_DASHBOARD_KEY", "s3cret")
    get_settings.cache_clear()
    try:
        assert client.get("/staff").status_code == 401
        assert client.get("/staff/queue").status_code == 401
        assert client.get("/staff?key=s3cret").status_code == 200
        assert client.get("/staff/queue", headers={"x-staff-key": "s3cret"}).status_code == 200
    finally:
        get_settings.cache_clear()


@pytest.mark.asyncio
async def test_notify_staff_records_and_publishes(monkeypatch):
    conn = FakeConn(fetchrow_row={"id": ESC_ID})
    _patch_pool(monkeypatch, conn)
    q = events.subscribe()
    try:
        msg = PatientMessage(
            message_id="m1", session_id="web:abc", channel="web", content="help me"
        )
        result = await notify_staff(msg, reason="urgent")
        assert result["escalation_id"] == str(ESC_ID)
        insert = next(c for c in conn.queries if c[0].startswith("INSERT INTO escalations"))
        assert insert[1][0] == "web:abc"
        assert q.get_nowait() == str(ESC_ID)
    finally:
        events.unsubscribe(q)


@pytest.mark.asyncio
async def test_record_escalation_nonfatal_without_db(monkeypatch):
    async def boom():
        raise OSError("no postgres")

    monkeypatch.setattr(store_mod, "get_pool", boom)
    msg = PatientMessage(message_id="m1", session_id="web:abc", channel="web", content="hi")
    result = await notify_staff(msg, reason="urgent")
    assert result["tool"] == "escalate"
    assert result["escalation_id"] is None
