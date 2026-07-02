"""End-to-end tests for /webhooks/email with the graph + provider stubbed.

Like the web webhook test, we monkeypatch build_graph before constructing the
TestClient so the lifespan picks up a stub graph (no Postgres / DashScope), and
we stub identity resolution + outbound send so nothing leaves the process.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

import app.gateway.adapters.email as email_mod
import app.main as main_mod
from app.config import get_settings
from app.gateway.schema import PatientReply


class StubGraph:
    def __init__(self, reply_text: str = "Sure, happy to help."):
        self._reply_text = reply_text
        self.calls: list[dict] = []

    async def ainvoke(self, state: dict, config: dict | None = None):
        self.calls.append({"state": state, "config": config})
        msg = state["message"]
        return {
            "reply": PatientReply(
                session_id=msg.session_id, channel=msg.channel, content=self._reply_text
            ),
            "session_cache": "stub-cache",
        }


_INBOUND = {
    "FromFull": {"Email": "Patient@Example.com"},
    "Subject": "Appointment question",
    "TextBody": "Hi, can I book?",
    "StrippedTextReply": "Hi, can I book?",
    "MessageID": "inbound-1",
    "Headers": [{"Name": "Message-ID", "Value": "<orig@mail.example>"}],
}


@pytest.fixture
def stub_graph(monkeypatch):
    graph = StubGraph()

    async def fake_build_graph(_app_state):
        return graph

    monkeypatch.setattr(main_mod, "build_graph", fake_build_graph)
    return graph


@pytest.fixture
def stub_send(monkeypatch):
    send = AsyncMock(return_value=True)
    monkeypatch.setattr(email_mod, "send_email", send)
    return send


@pytest.fixture(autouse=True)
def stub_identity(monkeypatch):
    # No DB in tests — unknown sender (proceeds without patient_id).
    monkeypatch.setattr(email_mod, "resolve_by_email", AsyncMock(return_value=None))


def test_email_webhook_sends_redacted_threaded_reply(stub_graph, stub_send):
    stub_graph._reply_text = "Your SSN 123-45-6789 is on file."
    with TestClient(main_mod.app) as client:
        r = client.post("/webhooks/email", json=_INBOUND)
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}
    stub_send.assert_awaited_once()
    kw = stub_send.await_args.kwargs
    assert kw["to"] == "patient@example.com"           # normalised lowercase
    assert kw["subject"] == "Re: Appointment question"  # threaded subject
    assert kw["in_reply_to"] == "<orig@mail.example>"   # threads under original
    assert "[REDACTED:SSN]" in kw["text"]
    assert "123-45-6789" not in kw["text"]


def test_email_webhook_namespaces_session_and_channel(stub_graph, stub_send):
    with TestClient(main_mod.app) as client:
        client.post("/webhooks/email", json=_INBOUND)
    assert stub_graph.calls
    msg = stub_graph.calls[0]["state"]["message"]
    assert msg.channel == "email"
    assert msg.session_id == "email:patient@example.com"


def test_email_webhook_ignores_empty_body(stub_graph, stub_send):
    payload = {**_INBOUND, "TextBody": "", "StrippedTextReply": ""}
    with TestClient(main_mod.app) as client:
        r = client.post("/webhooks/email", json=payload)
    assert r.status_code == 200
    assert r.json() == {"status": "ignored"}
    stub_send.assert_not_awaited()
    assert stub_graph.calls == []  # graph never invoked


def test_email_webhook_rejects_bad_secret(stub_graph, stub_send, monkeypatch):
    monkeypatch.setenv("EMAIL_WEBHOOK_SECRET", "s3cret")
    get_settings.cache_clear()
    with TestClient(main_mod.app) as client:
        r = client.post("/webhooks/email", json=_INBOUND, headers={"X-Webhook-Secret": "wrong"})
    assert r.status_code == 401
    stub_send.assert_not_awaited()
    get_settings.cache_clear()


def test_email_webhook_accepts_valid_secret(stub_graph, stub_send, monkeypatch):
    monkeypatch.setenv("EMAIL_WEBHOOK_SECRET", "s3cret")
    get_settings.cache_clear()
    with TestClient(main_mod.app) as client:
        r = client.post("/webhooks/email", json=_INBOUND, headers={"X-Webhook-Secret": "s3cret"})
    assert r.status_code == 200
    stub_send.assert_awaited_once()
    get_settings.cache_clear()


def test_email_webhook_no_secret_configured_allows_all(stub_graph, stub_send, monkeypatch):
    monkeypatch.setenv("EMAIL_WEBHOOK_SECRET", "")
    get_settings.cache_clear()
    with TestClient(main_mod.app) as client:
        r = client.post("/webhooks/email", json=_INBOUND)
    assert r.status_code == 200
    get_settings.cache_clear()
