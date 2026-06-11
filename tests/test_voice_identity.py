"""Caller-identity resolution for the voice agent.

`_resolve_caller(ctx)` derives (patient_id, patient_phone) from either
room metadata or the HEALTHDESK_DEMO_PATIENT_PHONE fallback, then maps
the phone to a patient via resolve_by_phone / upsert_profile.

These tests stub the LiveKit JobContext shape (only `room.metadata` is
touched) and monkeypatch the memory.profile functions.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

import app.voice.agent_worker as voice_mod
from app.config import get_settings


class _StubRoom:
    def __init__(self, metadata: str) -> None:
        self.metadata = metadata


class _StubCtx:
    def __init__(self, metadata: str = "") -> None:
        self.room = _StubRoom(metadata)


@pytest.fixture
def settings_demo_phone(monkeypatch):
    """Set HEALTHDESK_DEMO_PATIENT_PHONE + HEALTHDESK_ENV=demo for one test."""
    monkeypatch.setenv("HEALTHDESK_DEMO_PATIENT_PHONE", "2340000000000")
    monkeypatch.setenv("HEALTHDESK_ENV", "demo")
    get_settings.cache_clear()
    yield "2340000000000"
    get_settings.cache_clear()


@pytest.fixture
def settings_no_demo_phone(monkeypatch):
    monkeypatch.setenv("HEALTHDESK_DEMO_PATIENT_PHONE", "")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def stub_resolve_by_phone(monkeypatch):
    calls: list[str] = []
    profile: dict[str, Any] | None = {"id": "patient-abc", "phone": "234555"}

    async def fake_resolve(phone: str):
        calls.append(phone)
        return profile

    monkeypatch.setattr(voice_mod, "resolve_by_phone", fake_resolve)
    return calls, lambda p: profile.__setitem__("id", p) if profile else None


@pytest.fixture
def stub_upsert_profile(monkeypatch):
    calls: list[dict[str, Any]] = []

    async def fake_upsert(**kwargs):
        calls.append(kwargs)
        return "new-patient-id"

    monkeypatch.setattr(voice_mod, "upsert_profile", fake_upsert)
    return calls


# ── Metadata parsing ────────────────────────────────────────────────────

async def test_resolves_from_patient_phone_metadata(monkeypatch, stub_resolve_by_phone, settings_no_demo_phone):
    ctx = _StubCtx(metadata=json.dumps({"patient_phone": "234123456"}))
    pid, phone = await voice_mod._resolve_caller(ctx)
    assert phone == "234123456"
    assert pid == "patient-abc"


async def test_resolves_from_alternate_phone_key(monkeypatch, stub_resolve_by_phone, settings_no_demo_phone):
    ctx = _StubCtx(metadata=json.dumps({"phone": "234999"}))
    _pid, phone = await voice_mod._resolve_caller(ctx)
    assert phone == "234999"


async def test_invalid_json_metadata_falls_back_to_demo(monkeypatch, stub_resolve_by_phone, settings_demo_phone):
    ctx = _StubCtx(metadata="this is not json")
    _pid, phone = await voice_mod._resolve_caller(ctx)
    assert phone == settings_demo_phone


async def test_empty_metadata_falls_back_to_demo(monkeypatch, stub_resolve_by_phone, settings_demo_phone):
    ctx = _StubCtx(metadata="")
    _pid, phone = await voice_mod._resolve_caller(ctx)
    assert phone == settings_demo_phone


async def test_no_phone_anywhere_returns_none(monkeypatch, stub_resolve_by_phone, settings_no_demo_phone):
    ctx = _StubCtx(metadata="")
    pid, phone = await voice_mod._resolve_caller(ctx)
    assert pid is None and phone is None


# ── Profile resolution / upsert ─────────────────────────────────────────

async def test_existing_patient_returns_their_id(monkeypatch, settings_no_demo_phone):
    async def fake_resolve(phone: str):
        return {"id": "existing-uuid", "phone": phone}

    async def fake_upsert(**kwargs):
        raise AssertionError("should not upsert when profile already exists")

    monkeypatch.setattr(voice_mod, "resolve_by_phone", fake_resolve)
    monkeypatch.setattr(voice_mod, "upsert_profile", fake_upsert)

    ctx = _StubCtx(metadata=json.dumps({"patient_phone": "234"}))
    pid, _ = await voice_mod._resolve_caller(ctx)
    assert pid == "existing-uuid"


async def test_unknown_phone_upserts_new_profile(monkeypatch, settings_no_demo_phone, stub_upsert_profile):
    async def fake_resolve(_phone: str):
        return None  # no existing profile

    monkeypatch.setattr(voice_mod, "resolve_by_phone", fake_resolve)
    ctx = _StubCtx(metadata=json.dumps({"patient_phone": "234"}))
    pid, _ = await voice_mod._resolve_caller(ctx)
    assert pid == "new-patient-id"
    assert stub_upsert_profile == [{"phone": "234"}]


async def test_demo_fallback_blocked_in_production(monkeypatch, stub_resolve_by_phone):
    monkeypatch.setenv("HEALTHDESK_DEMO_PATIENT_PHONE", "2340000000000")
    monkeypatch.setenv("HEALTHDESK_ENV", "production")
    get_settings.cache_clear()
    ctx = _StubCtx(metadata="")
    pid, phone = await voice_mod._resolve_caller(ctx)
    assert pid is None
    assert phone is None
    get_settings.cache_clear()


async def test_db_failure_returns_none_id_but_keeps_phone(monkeypatch, settings_no_demo_phone):
    async def fake_resolve(_phone: str):
        raise RuntimeError("db unreachable")

    monkeypatch.setattr(voice_mod, "resolve_by_phone", fake_resolve)
    ctx = _StubCtx(metadata=json.dumps({"patient_phone": "234"}))
    pid, phone = await voice_mod._resolve_caller(ctx)
    # Identity resolution failed but we still know who we *think* we're
    # talking to — better than dropping the whole call.
    assert pid is None
    assert phone == "234"
