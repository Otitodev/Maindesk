"""Voice agent unit tests.

These tests do not need LiveKit infrastructure running. They exercise:
- HealthDeskAgent.__init__ shape
- _voice_msg PatientMessage wrapping
- llm_node memory injection (with recall_memories monkeypatched)
- All four @function_tool methods (with their underlying tool implementations monkeypatched)
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pytest
from livekit.agents import llm

import app.voice.agent_worker as voice_mod
from app.voice.agent_worker import HealthDeskAgent


# ── Helpers ─────────────────────────────────────────────────────────────

def _make_agent(patient_id: str | None = "p-1", phone: str | None = "234555") -> HealthDeskAgent:
    return HealthDeskAgent(patient_id=patient_id, patient_phone=phone)


def _user_ctx(text: str = "I want to book") -> llm.ChatContext:
    ctx = llm.ChatContext()
    ctx.items.append(llm.ChatMessage(role="user", content=[text]))
    return ctx


# ── __init__ + session id shape ─────────────────────────────────────────

def test_session_id_includes_phone():
    a = _make_agent(patient_id="abc", phone="234555")
    assert a._session_id == "voice:234555"


def test_session_id_without_phone_marks_unknown():
    a = _make_agent(patient_id=None, phone=None)
    assert a._session_id == "voice:unknown"


# ── _voice_msg PatientMessage wrapping ──────────────────────────────────

def test_voice_msg_carries_channel_and_patient_id():
    a = _make_agent(patient_id="abc-123", phone="234555")
    msg = a._voice_msg("any content")
    assert msg.channel == "voice"
    assert msg.patient_id == "abc-123"
    assert msg.session_id == "voice:234555"
    assert msg.content == "any content"


# ── llm_node memory injection ───────────────────────────────────────────

class _SentinelDelegate:
    """Stand-in for Agent.default.llm_node so tests don't hit a real LLM."""

    def __init__(self) -> None:
        self.called_with_ctx: llm.ChatContext | None = None

    def llm_node(self, agent, chat_ctx, tools, model_settings):
        self.called_with_ctx = chat_ctx
        return "SENTINEL"


@pytest.fixture
def patched_default(monkeypatch):
    sentinel = _SentinelDelegate()
    # voice_mod imports Agent at module load; patch Agent.default there.
    monkeypatch.setattr(voice_mod.Agent, "default", sentinel, raising=True)
    return sentinel


async def test_llm_node_skips_recall_when_no_patient(monkeypatch, patched_default):
    called = []

    async def fake_recall(**_):
        called.append(_)
        return []

    monkeypatch.setattr(voice_mod, "recall_memories", fake_recall)
    a = _make_agent(patient_id=None)
    ctx = _user_ctx()
    await a.llm_node(ctx, [], None)
    assert called == []  # recall never invoked
    assert patched_default.called_with_ctx is ctx


async def test_llm_node_skips_when_last_message_is_not_user(monkeypatch, patched_default):
    called = []

    async def fake_recall(**_):
        called.append(_)
        return []

    monkeypatch.setattr(voice_mod, "recall_memories", fake_recall)
    a = _make_agent()
    ctx = llm.ChatContext()
    ctx.items.append(llm.ChatMessage(role="system", content=["boot"]))
    await a.llm_node(ctx, [], None)
    assert called == []


async def test_llm_node_injects_memories_before_user_message(monkeypatch, patched_default):
    async def fake_recall(*, patient_id, query, top_k):
        assert patient_id == "p-1"
        assert query == "I want to book"
        return [
            {"content": "Prefers afternoons", "score": 0.9},
            {"content": "Allergic to penicillin", "score": 0.8},
        ]

    monkeypatch.setattr(voice_mod, "recall_memories", fake_recall)
    a = _make_agent()
    ctx = _user_ctx("I want to book")
    result = await a.llm_node(ctx, [], None)

    # The injected memo lives at items[-2]; the user msg stays last so
    # the LLM treats it as the freshest input.
    assert result == "SENTINEL"
    assert len(ctx.items) == 2
    injected = ctx.items[-2]
    assert isinstance(injected, llm.ChatMessage)
    assert injected.role == "system"
    body = injected.content[0] if isinstance(injected.content, list) else injected.content
    assert "Prefers afternoons" in body
    assert "Allergic to penicillin" in body


async def test_llm_node_no_memories_does_not_insert(monkeypatch, patched_default):
    async def fake_recall(**_):
        return []

    monkeypatch.setattr(voice_mod, "recall_memories", fake_recall)
    a = _make_agent()
    ctx = _user_ctx()
    await a.llm_node(ctx, [], None)
    # Only the original user message remains.
    assert len(ctx.items) == 1


async def test_llm_node_recall_failure_is_swallowed(monkeypatch, patched_default):
    async def boom(**_):
        raise RuntimeError("pgvector died")

    monkeypatch.setattr(voice_mod, "recall_memories", boom)
    a = _make_agent()
    ctx = _user_ctx()
    # Must not raise — voice turn keeps going without memory rather than
    # leaving the caller in dead silence.
    result = await a.llm_node(ctx, [], None)
    assert result == "SENTINEL"


# ── @function_tool: find_open_slots ─────────────────────────────────────

async def test_find_open_slots_passes_through(monkeypatch):
    captured: dict[str, Any] = {}

    async def fake_suggest_slots(msg):
        captured["msg"] = msg
        return {"slots": ["2026-06-12T15:00:00+00:00", "2026-06-12T15:30:00+00:00"]}

    monkeypatch.setattr(voice_mod, "suggest_slots", fake_suggest_slots)
    a = _make_agent()
    out = await a.find_open_slots(date="2026-06-12")
    assert "2026-06-12T15:00:00+00:00" in out
    assert captured["msg"].channel == "voice"


async def test_find_open_slots_handles_empty(monkeypatch):
    async def fake_suggest_slots(_msg):
        return {"slots": []}

    monkeypatch.setattr(voice_mod, "suggest_slots", fake_suggest_slots)
    a = _make_agent()
    out = await a.find_open_slots(date="2099-01-01")
    assert "No open slots" in out


# ── @function_tool: book_appointment ────────────────────────────────────

async def test_book_appointment_refuses_without_patient_id():
    a = _make_agent(patient_id=None, phone=None)
    out = await a.book_appointment(slot_iso="2026-06-12T15:00:00+00:00")
    assert "have not identified" in out.lower()


async def test_book_appointment_handles_unparseable_iso():
    a = _make_agent()
    out = await a.book_appointment(slot_iso="not-a-date")
    assert "did not parse" in out.lower()


async def test_book_appointment_calls_book(monkeypatch):
    captured: dict[str, Any] = {}

    async def fake_book(patient_id, ts):
        captured["patient_id"] = patient_id
        captured["ts"] = ts
        return {"tool": "book", "id": "appt-1", "starts_at": ts.isoformat()}

    monkeypatch.setattr(voice_mod, "book", fake_book)
    a = _make_agent(patient_id="p-1")
    out = await a.book_appointment(slot_iso="2026-06-12T15:00:00+00:00")
    assert "Booked" in out
    assert captured["patient_id"] == "p-1"
    assert captured["ts"] == datetime(2026, 6, 12, 15, 0, tzinfo=timezone.utc)


# ── @function_tool: find_my_appointments ────────────────────────────────

async def test_find_my_appointments_refuses_without_patient():
    a = _make_agent(patient_id=None, phone=None)
    out = await a.find_my_appointments()
    assert "do not have" in out.lower() or "on file" in out.lower()


async def test_find_my_appointments_empty(monkeypatch):
    async def fake_find_existing(_msg):
        return {"appointments": []}

    monkeypatch.setattr(voice_mod, "find_existing", fake_find_existing)
    a = _make_agent()
    out = await a.find_my_appointments()
    assert "No upcoming" in out


async def test_find_my_appointments_lists(monkeypatch):
    async def fake_find_existing(_msg):
        return {
            "appointments": [
                {"id": "a-1", "starts_at": "2026-06-12T15:00:00+00:00", "status": "booked"},
                {"id": "a-2", "starts_at": "2026-06-19T10:00:00+00:00", "status": "booked"},
            ]
        }

    monkeypatch.setattr(voice_mod, "find_existing", fake_find_existing)
    a = _make_agent()
    out = await a.find_my_appointments()
    assert "2026-06-12T15:00:00+00:00" in out
    assert "2026-06-19T10:00:00+00:00" in out


# ── @function_tool: escalate_to_staff ───────────────────────────────────

async def test_escalate_to_staff_notifies(monkeypatch):
    captured: dict[str, Any] = {}

    async def fake_notify(msg, *, reason):
        captured["msg"] = msg
        captured["reason"] = reason
        return {"tool": "escalate", "delivered": True, "reason": reason}

    monkeypatch.setattr(voice_mod, "notify_staff", fake_notify)
    a = _make_agent()
    out = await a.escalate_to_staff(reason="chest pain")
    assert "notified staff" in out.lower()
    assert captured["reason"] == "chest pain"
    assert captured["msg"].channel == "voice"
    assert captured["msg"].content == "chest pain"
