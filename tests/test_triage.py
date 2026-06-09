"""Triage node tests — patches `complete` so no network is required."""

from __future__ import annotations

import pytest

from app.agents import triage as triage_mod
from app.gateway.schema import PatientMessage


def _msg(text: str = "Hi") -> PatientMessage:
    return PatientMessage(
        message_id="t1", session_id="web:t1", channel="web", content=text
    )


async def test_triage_parses_clean_json(monkeypatch):
    async def fake_complete(**_kwargs):
        return '{"intent": "book_appointment", "confidence": 0.92}'

    monkeypatch.setattr(triage_mod, "complete", fake_complete)
    out = await triage_mod.triage_node({"message": _msg("book Tue please")})
    assert out["intent"] == "book_appointment"
    assert out["intent_confidence"] == pytest.approx(0.92)


async def test_triage_handles_malformed_json(monkeypatch):
    async def fake_complete(**_kwargs):
        return "not json at all"

    monkeypatch.setattr(triage_mod, "complete", fake_complete)
    out = await triage_mod.triage_node({"message": _msg()})
    assert out["intent"] == "unknown"
    assert out["intent_confidence"] == 0.0


async def test_triage_handles_missing_keys(monkeypatch):
    async def fake_complete(**_kwargs):
        return '{"something_else": 1}'

    monkeypatch.setattr(triage_mod, "complete", fake_complete)
    out = await triage_mod.triage_node({"message": _msg()})
    assert out["intent"] == "unknown"


async def test_triage_handles_llm_exception(monkeypatch):
    async def fake_complete(**_kwargs):
        raise RuntimeError("upstream timeout")

    monkeypatch.setattr(triage_mod, "complete", fake_complete)
    with pytest.raises(RuntimeError):
        # The current implementation only catches JSON/Value/Key errors;
        # upstream failures propagate. This test pins that behaviour so
        # we notice if we ever change it (e.g. wrap in try/except).
        await triage_mod.triage_node({"message": _msg()})
