"""Tests for the /onboarding wizard router."""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

import app.main as main_mod
from app import clinic_config
from app.config import get_settings


@pytest.fixture
def client(monkeypatch):
    async def fake_build_graph(_state):
        return object()

    monkeypatch.setattr(main_mod, "build_graph", fake_build_graph)
    # No DB in tests: clinic_config.refresh swallows the error and uses defaults.
    monkeypatch.setattr("app.clinic_config.get_pool", AsyncMock(side_effect=RuntimeError("no db")))
    with TestClient(main_mod.app) as c:
        yield c


def test_get_form_renders_prefilled(client):
    r = client.get("/onboarding")
    assert r.status_code == 200
    assert "Clinic setup" in r.text
    assert "HealthDesk" in r.text  # default agent name prefilled


def test_post_saves_parsed_config(client, monkeypatch):
    captured = {}

    async def fake_save(patch):
        captured.update(patch)
        return {**clinic_config.current(), **patch}

    monkeypatch.setattr("app.clinic_config.save", fake_save)
    r = client.post("/onboarding", data={
        "clinic_name": "Harmony", "agent_name": "Ada", "timezone": "UTC",
        "open_hour": "8", "close_hour": "18", "working_days": ["1", "2", "3"],
        "answer_mode": "after_hours", "faqs": "Parking on 5th St.",
    })
    assert r.status_code == 200
    assert "Saved" in r.text
    assert captured["clinic_name"] == "Harmony"
    assert captured["open_hour"] == 8                    # coerced to int
    assert captured["working_days"] == [1, 2, 3]
    assert captured["answer_mode"] == "after_hours"


def test_post_rejects_inverted_hours(client):
    r = client.post("/onboarding", data={
        "timezone": "UTC", "open_hour": "18", "close_hour": "9",
        "working_days": ["1"], "answer_mode": "always",
    })
    assert r.status_code == 422


def test_post_rejects_no_working_days(client):
    r = client.post("/onboarding", data={
        "timezone": "UTC", "open_hour": "9", "close_hour": "17",
        "answer_mode": "always",
    })
    assert r.status_code == 422


def test_auth_enforced_when_key_set(client, monkeypatch):
    monkeypatch.setenv("STAFF_DASHBOARD_KEY", "k")
    get_settings.cache_clear()
    assert client.get("/onboarding").status_code == 401
    assert client.get("/onboarding?key=k").status_code == 200
    get_settings.cache_clear()
