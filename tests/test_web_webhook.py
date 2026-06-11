"""End-to-end test for /webhooks/web with the graph stubbed.

We monkeypatch `build_graph` in app.main before constructing TestClient
so the lifespan picks up the stub instead of trying to connect to
Postgres / DashScope.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import app.main as main_mod
from app.config import get_settings
from app.gateway.schema import PatientReply


class StubGraph:
    """Mimics a compiled LangGraph: only `ainvoke` is called."""

    def __init__(self, reply_text: str = "Hi! Sure, I can help."):
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


@pytest.fixture
def stub_graph(monkeypatch):
    graph = StubGraph()

    async def fake_build_graph(_app_state):
        return graph

    monkeypatch.setattr(main_mod, "build_graph", fake_build_graph)
    return graph


def test_web_webhook_returns_redacted_reply(stub_graph):
    stub_graph._reply_text = "Your SSN 123-45-6789 is on file."
    with TestClient(main_mod.app) as client:
        r = client.post(
            "/webhooks/web",
            json={"session_id": "abc", "content": "Hi there"},
        )
    assert r.status_code == 200
    body = r.json()
    assert body["session_id"] == "web:abc"
    assert "[REDACTED:SSN]" in body["content"]
    assert "123-45-6789" not in body["content"]


def test_web_webhook_rejects_empty_content(stub_graph):
    with TestClient(main_mod.app) as client:
        r = client.post(
            "/webhooks/web",
            json={"session_id": "abc", "content": "   "},
        )
    assert r.status_code == 422


def test_web_webhook_session_id_namespaced(stub_graph):
    with TestClient(main_mod.app) as client:
        client.post("/webhooks/web", json={"session_id": "xyz", "content": "hi"})
    assert stub_graph.calls
    msg = stub_graph.calls[0]["state"]["message"]
    assert msg.session_id == "web:xyz"
    assert msg.channel == "web"


def test_health_endpoint(stub_graph):
    with TestClient(main_mod.app) as client:
        r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_web_webhook_rejects_missing_api_key(stub_graph, monkeypatch):
    monkeypatch.setenv("WEB_API_KEY", "secret-key")
    get_settings.cache_clear()
    with TestClient(main_mod.app) as client:
        r = client.post("/webhooks/web", json={"session_id": "x", "content": "hi"})
    assert r.status_code == 401
    get_settings.cache_clear()


def test_web_webhook_accepts_valid_api_key(stub_graph, monkeypatch):
    monkeypatch.setenv("WEB_API_KEY", "secret-key")
    get_settings.cache_clear()
    with TestClient(main_mod.app) as client:
        r = client.post(
            "/webhooks/web",
            json={"session_id": "x", "content": "hi"},
            headers={"X-API-Key": "secret-key"},
        )
    assert r.status_code == 200
    get_settings.cache_clear()


def test_web_webhook_no_key_configured_allows_all(stub_graph, monkeypatch):
    monkeypatch.setenv("WEB_API_KEY", "")
    get_settings.cache_clear()
    with TestClient(main_mod.app) as client:
        r = client.post("/webhooks/web", json={"session_id": "x", "content": "hi"})
    assert r.status_code == 200
    get_settings.cache_clear()
