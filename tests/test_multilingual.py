"""Multilingual support: triage language detection + reasoner reply language."""

from __future__ import annotations

import pytest

from app.agents import reasoner as reasoner_mod
from app.agents import triage as triage_mod
from app.gateway.schema import PatientMessage


def _msg(text: str = "Hi") -> PatientMessage:
    return PatientMessage(
        message_id="t1", session_id="web:t1", channel="web", content=text
    )


# ── Triage detection ─────────────────────────────────────────────────────


async def test_triage_returns_detected_language(monkeypatch):
    async def fake_complete(**_kwargs):
        return '{"intent": "book_appointment", "confidence": 0.9, "language": "ar"}'

    monkeypatch.setattr(triage_mod, "complete", fake_complete)
    out = await triage_mod.triage_node({"message": _msg("أريد حجز موعد")})
    assert out["language"] == "ar"


async def test_triage_defaults_language_to_english(monkeypatch):
    async def fake_complete(**_kwargs):
        return '{"intent": "smalltalk", "confidence": 0.8}'

    monkeypatch.setattr(triage_mod, "complete", fake_complete)
    out = await triage_mod.triage_node({"message": _msg()})
    assert out["language"] == "en"


@pytest.mark.parametrize("weird", ['"Arabic"', '"a"', "42", "null", '" ZH "'])
async def test_triage_normalises_language_values(monkeypatch, weird):
    async def fake_complete(**_kwargs):
        return f'{{"intent": "smalltalk", "confidence": 0.8, "language": {weird}}}'

    monkeypatch.setattr(triage_mod, "complete", fake_complete)
    out = await triage_mod.triage_node({"message": _msg()})
    assert out["language"] == ("zh" if "ZH" in weird else "en")


async def test_triage_malformed_json_still_sets_language(monkeypatch):
    async def fake_complete(**_kwargs):
        return "not json"

    monkeypatch.setattr(triage_mod, "complete", fake_complete)
    out = await triage_mod.triage_node({"message": _msg()})
    assert out["language"] == "en"


# ── Reasoner reply language ──────────────────────────────────────────────


async def test_reasoner_instructs_reply_language(monkeypatch):
    captured: dict = {}

    async def fake_complete(**kwargs):
        captured.update(kwargs)
        return "حسناً"

    monkeypatch.setattr(reasoner_mod, "complete", fake_complete)
    state = {
        "message": _msg("أريد حجز موعد"),
        "intent": "book_appointment",
        "intent_confidence": 0.9,
        "language": "ar",
    }
    out = await reasoner_mod.reasoner_node(state)
    assert "(ISO code: ar)" in captured["system"]
    assert out["reply"].content == "حسناً"


async def test_reasoner_no_language_instruction_for_english(monkeypatch):
    captured: dict = {}

    async def fake_complete(**kwargs):
        captured.update(kwargs)
        return "Sure!"

    monkeypatch.setattr(reasoner_mod, "complete", fake_complete)
    state = {
        "message": _msg("book me in"),
        "intent": "book_appointment",
        "intent_confidence": 0.9,
        "language": "en",
    }
    await reasoner_mod.reasoner_node(state)
    assert "ISO code" not in captured["system"]


async def test_escalation_message_localised():
    state = {
        "message": _msg("ساعدوني"),
        "intent": "escalate",
        "intent_confidence": 0.95,
        "language": "ar",
    }
    out = await reasoner_mod.reasoner_node(state)
    assert out["escalated"] is True
    assert out["reply"].content == reasoner_mod._ESCALATION_TEXT["ar"]


async def test_escalation_message_falls_back_to_english():
    state = {
        "message": _msg("help"),
        "intent": "escalate",
        "intent_confidence": 0.95,
        "language": "fi",  # no canned Finnish line
    }
    out = await reasoner_mod.reasoner_node(state)
    assert out["reply"].content == reasoner_mod._ESCALATION_TEXT["en"]
