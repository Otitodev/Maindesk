"""Tests for runtime clinic config: defaults, DB overlay, save, prompt block."""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from app import clinic_config
from app.config import get_settings


@pytest.fixture
def mock_pool(monkeypatch):
    conn = AsyncMock()
    pool = MagicMock()
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)
    monkeypatch.setattr("app.clinic_config.get_pool", AsyncMock(return_value=pool))
    return conn


def test_current_returns_env_defaults_without_cache():
    cfg = clinic_config.current()
    assert cfg["timezone"] == get_settings().clinic_timezone
    assert cfg["answer_mode"] == "always"
    assert cfg["agent_name"] == "Danny"
    assert cfg["working_days"] == [1, 2, 3, 4, 5]


async def test_refresh_overlays_stored_over_defaults(mock_pool):
    mock_pool.fetchrow.return_value = {
        "config": {"clinic_name": "Harmony", "open_hour": 8, "answer_mode": "after_hours"}
    }
    cfg = await clinic_config.refresh()
    assert cfg["clinic_name"] == "Harmony"
    assert cfg["open_hour"] == 8
    assert cfg["answer_mode"] == "after_hours"
    # fields not in the stored blob keep their env defaults
    assert cfg["close_hour"] == get_settings().clinic_close_hour


async def test_refresh_falls_back_to_defaults_on_db_error(monkeypatch):
    monkeypatch.setattr(
        "app.clinic_config.get_pool", AsyncMock(side_effect=RuntimeError("db down"))
    )
    cfg = await clinic_config.refresh()
    assert cfg["answer_mode"] == "always"  # defaults, no crash


async def test_save_persists_editable_subset_and_refreshes(mock_pool):
    mock_pool.fetchrow.return_value = {"config": {"clinic_name": "Harmony"}}
    out = await clinic_config.save(
        {"clinic_name": "Harmony", "open_hour": 8, "not_editable": "x"}
    )
    assert mock_pool.execute.await_count == 1
    stored = json.loads(mock_pool.execute.await_args[0][1])
    assert stored["clinic_name"] == "Harmony"
    assert stored["open_hour"] == 8
    assert "not_editable" not in stored          # only EDITABLE_FIELDS persisted
    assert out["clinic_name"] == "Harmony"        # returns refreshed config


def test_knowledge_block_empty_by_default():
    assert clinic_config.knowledge_block() == ""


def test_knowledge_block_includes_persona_and_faqs():
    block = clinic_config.knowledge_block(
        {"clinic_name": "Harmony", "agent_name": "Ada", "faqs": "Parking on 5th St."}
    )
    assert "Ada" in block and "Harmony" in block and "Parking on 5th St." in block


def test_reasoner_system_injects_clinic_knowledge(monkeypatch):
    monkeypatch.setattr(
        clinic_config, "current",
        lambda: {**clinic_config._defaults(), "clinic_name": "Harmony", "faqs": "We accept Cigna."},
    )
    from app.agents.reasoner import _SYSTEM, build_reasoner_system
    built = build_reasoner_system()
    assert _SYSTEM in built
    assert "Cigna" in built and "Harmony" in built
