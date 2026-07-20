"""Tests for /health/gateways — in particular the voice phone/web split.

Voice has two independent paths that share STT/TTS/LLM credentials but
diverge on telephony: the browser widget (self-hosted WebRTC, no vendor
creds needed) and the Twilio phone number (needs Twilio creds on top).
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

import app.main as main_mod
from app.config import get_settings


@pytest.fixture
def client(monkeypatch):
    async def fake_build_graph(_state):
        return object()

    monkeypatch.setattr(main_mod, "build_graph", fake_build_graph)
    monkeypatch.setattr("app.clinic_config.get_pool", AsyncMock(side_effect=RuntimeError("no db")))
    with TestClient(main_mod.app) as c:
        yield c


def _set_voice_core(monkeypatch):
    monkeypatch.setenv("DEEPGRAM_API_KEY", "dg-key")
    monkeypatch.setenv("ELEVENLABS_API_KEY", "el-key")
    monkeypatch.setenv("DASHSCOPE_API_KEY", "ds-key")
    monkeypatch.setenv("HEALTHDESK_VOICE", "true")


def test_voice_web_ready_without_twilio_creds(monkeypatch, client):
    _set_voice_core(monkeypatch)
    monkeypatch.setenv("TWILIO_ACCOUNT_SID", "")
    monkeypatch.setenv("TWILIO_AUTH_TOKEN", "")
    get_settings.cache_clear()

    body = client.get("/health/gateways").json()
    assert body["voice"]["web"] is True
    assert body["voice"]["phone"] is False
    assert body["voice"]["live"] is True
    assert isinstance(body["voice"]["web"], bool)
    assert isinstance(body["voice"]["phone"], bool)
    assert isinstance(body["voice"]["live"], bool)


def test_voice_phone_ready_with_twilio_creds(monkeypatch, client):
    _set_voice_core(monkeypatch)
    monkeypatch.setenv("TWILIO_ACCOUNT_SID", "AC123")
    monkeypatch.setenv("TWILIO_AUTH_TOKEN", "secret")
    get_settings.cache_clear()

    body = client.get("/health/gateways").json()
    assert body["voice"]["web"] is True
    assert body["voice"]["phone"] is True
    assert body["voice"]["live"] is True


def test_voice_not_ready_when_disabled(monkeypatch, client):
    _set_voice_core(monkeypatch)
    monkeypatch.setenv("HEALTHDESK_VOICE", "false")
    monkeypatch.setenv("TWILIO_ACCOUNT_SID", "AC123")
    monkeypatch.setenv("TWILIO_AUTH_TOKEN", "secret")
    get_settings.cache_clear()

    body = client.get("/health/gateways").json()
    assert body["voice"]["web"] is False
    assert body["voice"]["phone"] is False
    assert body["voice"]["live"] is False


def test_voice_not_ready_without_core_creds(monkeypatch, client):
    monkeypatch.setenv("DEEPGRAM_API_KEY", "")
    monkeypatch.setenv("ELEVENLABS_API_KEY", "")
    monkeypatch.setenv("DASHSCOPE_API_KEY", "")
    monkeypatch.setenv("HEALTHDESK_VOICE", "true")
    monkeypatch.setenv("TWILIO_ACCOUNT_SID", "AC123")
    monkeypatch.setenv("TWILIO_AUTH_TOKEN", "secret")
    get_settings.cache_clear()

    body = client.get("/health/gateways").json()
    assert body["voice"]["web"] is False
    assert body["voice"]["phone"] is False
    assert body["voice"]["live"] is False


def test_summary_counts_four_channels(monkeypatch, client):
    _set_voice_core(monkeypatch)
    get_settings.cache_clear()
    body = client.get("/health/gateways").json()
    assert body["summary"]["total"] == 4
    assert 0 <= body["summary"]["live"] <= 4
