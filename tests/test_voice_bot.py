"""Voice pipeline unit tests (app.voice.bot).

These tests do not need Twilio or a running Pipecat pipeline. They exercise:
- CallSession shape (session_id, voice_msg wrapping)
- All six tool functions (direct-function style, called with a hand-built
  FunctionCallParams and their underlying app.tools.* implementations
  monkeypatched)
- MemoryRecallProcessor's context injection, called directly since
  FrameProcessor.process_frame()/push_frame() are safe to invoke on a
  processor that was never linked into a running pipeline (push_frame just
  no-ops when the processor hasn't been started)
- _persist_session's write-back gating
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pytest
from pipecat.frames.frames import LLMContextFrame
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.frame_processor import FrameDirection
from pipecat.services.llm_service import FunctionCallParams

import app.voice.bot as voice_mod
from app.voice.bot import CallSession, MemoryRecallProcessor


# ── Helpers ─────────────────────────────────────────────────────────────

def _session(patient_id: str | None = "p-1", phone: str | None = "234555") -> CallSession:
    return CallSession(patient_id=patient_id, patient_phone=phone)


def _call_params(session: CallSession, **arguments: Any) -> tuple[FunctionCallParams, dict]:
    captured: dict[str, Any] = {}

    async def result_callback(result: Any) -> None:
        captured["result"] = result

    params = FunctionCallParams(
        function_name="test",
        tool_call_id="tc-1",
        arguments=arguments,
        llm=None,
        pipeline_worker=None,
        context=None,
        result_callback=result_callback,
        app_resources=session,
    )
    return params, captured


# ── CallSession shape ────────────────────────────────────────────────────

def test_session_id_includes_phone():
    s = _session(patient_id="abc", phone="234555")
    assert s.session_id == "voice:234555"


def test_session_id_without_phone_marks_unknown():
    s = _session(patient_id=None, phone=None)
    assert s.session_id == "voice:unknown"


def test_voice_msg_carries_channel_and_patient_id():
    s = _session(patient_id="abc-123", phone="234555")
    msg = s.voice_msg("any content")
    assert msg.channel == "voice"
    assert msg.patient_id == "abc-123"
    assert msg.session_id == "voice:234555"
    assert msg.content == "any content"


# ── find_open_slots ──────────────────────────────────────────────────────

async def test_find_open_slots_passes_through(monkeypatch):
    captured_msg: dict[str, Any] = {}

    async def fake_suggest_slots(msg):
        captured_msg["msg"] = msg
        return {"slots": ["2026-06-12T15:00:00+00:00", "2026-06-12T15:30:00+00:00"]}

    monkeypatch.setattr(voice_mod, "suggest_slots", fake_suggest_slots)
    params, captured = _call_params(_session(), date="2026-06-12")
    await voice_mod.find_open_slots(params, date="2026-06-12")
    assert "2026-06-12T15:00:00+00:00" in captured["result"]
    assert captured_msg["msg"].channel == "voice"


async def test_find_open_slots_handles_empty(monkeypatch):
    async def fake_suggest_slots(_msg):
        return {"slots": []}

    monkeypatch.setattr(voice_mod, "suggest_slots", fake_suggest_slots)
    params, captured = _call_params(_session(), date="2099-01-01")
    await voice_mod.find_open_slots(params, date="2099-01-01")
    assert "No open slots" in captured["result"]


# ── book_appointment ─────────────────────────────────────────────────────

async def test_book_appointment_refuses_without_patient_id():
    params, captured = _call_params(_session(patient_id=None, phone=None))
    await voice_mod.book_appointment(params, slot_iso="2026-06-12T15:00:00+00:00")
    assert "have not identified" in captured["result"].lower()


async def test_book_appointment_handles_unparseable_iso():
    params, captured = _call_params(_session())
    await voice_mod.book_appointment(params, slot_iso="not-a-date")
    assert "did not parse" in captured["result"].lower()


async def test_book_appointment_calls_book(monkeypatch):
    call_args: dict[str, Any] = {}

    async def fake_book(patient_id, ts):
        call_args["patient_id"] = patient_id
        call_args["ts"] = ts
        return {"tool": "book", "id": "appt-1", "starts_at": ts.isoformat()}

    monkeypatch.setattr(voice_mod, "book", fake_book)
    params, captured = _call_params(_session(patient_id="p-1"))
    await voice_mod.book_appointment(params, slot_iso="2026-06-12T15:00:00+00:00")
    assert "Booked" in captured["result"]
    assert call_args["patient_id"] == "p-1"
    assert call_args["ts"] == datetime(2026, 6, 12, 15, 0, tzinfo=timezone.utc)


async def test_book_appointment_slot_taken_does_not_confirm_booking(monkeypatch):
    """When book() returns slot_taken, the caller must NOT hear 'Booked for...'."""
    async def fake_book_taken(patient_id, ts):
        return {"tool": "book", "error": "slot_taken", "starts_at": ts.isoformat()}

    monkeypatch.setattr(voice_mod, "book", fake_book_taken)
    params, captured = _call_params(_session(patient_id="p-1"))
    await voice_mod.book_appointment(params, slot_iso="2026-06-12T15:00:00+00:00")
    assert "Booked" not in captured["result"]
    assert "taken" in captured["result"].lower() or "sorry" in captured["result"].lower()


# ── find_my_appointments ─────────────────────────────────────────────────

async def test_find_my_appointments_refuses_without_patient():
    params, captured = _call_params(_session(patient_id=None, phone=None))
    await voice_mod.find_my_appointments(params)
    assert "do not have" in captured["result"].lower() or "on file" in captured["result"].lower()


async def test_find_my_appointments_empty(monkeypatch):
    async def fake_find_existing(_msg):
        return {"appointments": []}

    monkeypatch.setattr(voice_mod, "find_existing", fake_find_existing)
    params, captured = _call_params(_session())
    await voice_mod.find_my_appointments(params)
    assert "No upcoming" in captured["result"]


async def test_find_my_appointments_lists(monkeypatch):
    async def fake_find_existing(_msg):
        return {
            "appointments": [
                {"id": "a-1", "starts_at": "2026-06-12T15:00:00+00:00", "status": "booked"},
                {"id": "a-2", "starts_at": "2026-06-19T10:00:00+00:00", "status": "booked"},
            ]
        }

    monkeypatch.setattr(voice_mod, "find_existing", fake_find_existing)
    params, captured = _call_params(_session())
    await voice_mod.find_my_appointments(params)
    assert "2026-06-12T15:00:00+00:00" in captured["result"]
    assert "2026-06-19T10:00:00+00:00" in captured["result"]


# ── escalate_to_staff ────────────────────────────────────────────────────

async def test_escalate_to_staff_notifies(monkeypatch):
    call_args: dict[str, Any] = {}

    async def fake_notify(msg, *, reason):
        call_args["msg"] = msg
        call_args["reason"] = reason
        return {"tool": "escalate", "delivered": True, "reason": reason}

    monkeypatch.setattr(voice_mod, "notify_staff", fake_notify)
    params, captured = _call_params(_session())
    await voice_mod.escalate_to_staff(params, reason="chest pain")
    assert "notified staff" in captured["result"].lower()
    assert call_args["reason"] == "chest pain"
    assert call_args["msg"].channel == "voice"
    assert call_args["msg"].content == "chest pain"


# ── cancel_appointment ───────────────────────────────────────────────────

async def test_cancel_appointment_refuses_without_patient():
    params, captured = _call_params(_session(patient_id=None, phone=None))
    await voice_mod.cancel_appointment(params, starts_at_iso="2026-06-12T15:00:00+00:00")
    assert "on file" in captured["result"].lower()


async def test_cancel_appointment_not_found(monkeypatch):
    async def fake_find_existing(_msg):
        return {"appointments": []}

    monkeypatch.setattr(voice_mod, "find_existing", fake_find_existing)
    params, captured = _call_params(_session(patient_id="p-1"))
    await voice_mod.cancel_appointment(params, starts_at_iso="2026-06-12T15:00:00+00:00")
    assert "could not find" in captured["result"].lower()


async def test_cancel_appointment_cancels_matched_row(monkeypatch):
    call_args: dict[str, Any] = {}

    async def fake_find_existing(_msg):
        return {"appointments": [
            {"id": "appt-9", "starts_at": "2026-06-12T15:00:00+00:00", "status": "booked"}
        ]}

    async def fake_cancel(patient_id, appointment_id):
        call_args["args"] = (patient_id, appointment_id)
        return {"tool": "cancel", "id": appointment_id, "status": "cancelled",
                "starts_at": "2026-06-12T15:00:00+00:00"}

    monkeypatch.setattr(voice_mod, "find_existing", fake_find_existing)
    monkeypatch.setattr(voice_mod, "cancel", fake_cancel)
    params, captured = _call_params(_session(patient_id="p-1"))
    await voice_mod.cancel_appointment(params, starts_at_iso="2026-06-12T15:00:00+00:00")
    assert "cancelled" in captured["result"].lower()
    assert call_args["args"] == ("p-1", "appt-9")


# ── reschedule_appointment ───────────────────────────────────────────────

async def test_reschedule_appointment_refuses_without_patient():
    params, captured = _call_params(_session(patient_id=None, phone=None))
    await voice_mod.reschedule_appointment(
        params,
        current_starts_at_iso="2026-06-12T15:00:00+00:00",
        new_starts_at_iso="2026-06-13T09:00:00+00:00",
    )
    assert "on file" in captured["result"].lower()


async def test_reschedule_appointment_moves_to_new_slot(monkeypatch):
    call_args: dict[str, Any] = {}

    async def fake_find_existing(_msg):
        return {"appointments": [
            {"id": "appt-9", "starts_at": "2026-06-12T15:00:00+00:00", "status": "booked"}
        ]}

    async def fake_reschedule(patient_id, appointment_id, new_ts):
        call_args["args"] = (patient_id, appointment_id, new_ts)
        return {"tool": "reschedule", "id": "new-1", "old_appointment_id": appointment_id,
                "starts_at": new_ts.isoformat()}

    monkeypatch.setattr(voice_mod, "find_existing", fake_find_existing)
    monkeypatch.setattr(voice_mod, "reschedule", fake_reschedule)
    params, captured = _call_params(_session(patient_id="p-1"))
    await voice_mod.reschedule_appointment(
        params,
        current_starts_at_iso="2026-06-12T15:00:00+00:00",
        new_starts_at_iso="2026-06-13T09:00:00+00:00",
    )
    assert "moved" in captured["result"].lower()
    assert call_args["args"][0] == "p-1"
    assert call_args["args"][1] == "appt-9"
    assert call_args["args"][2] == datetime(2026, 6, 13, 9, 0, tzinfo=timezone.utc)


async def test_reschedule_appointment_slot_taken_does_not_confirm(monkeypatch):
    async def fake_find_existing(_msg):
        return {"appointments": [
            {"id": "appt-9", "starts_at": "2026-06-12T15:00:00+00:00", "status": "booked"}
        ]}

    async def fake_reschedule_taken(patient_id, appointment_id, new_ts):
        return {"tool": "reschedule", "error": "slot_taken", "starts_at": new_ts.isoformat()}

    monkeypatch.setattr(voice_mod, "find_existing", fake_find_existing)
    monkeypatch.setattr(voice_mod, "reschedule", fake_reschedule_taken)
    params, captured = _call_params(_session(patient_id="p-1"))
    await voice_mod.reschedule_appointment(
        params,
        current_starts_at_iso="2026-06-12T15:00:00+00:00",
        new_starts_at_iso="2026-06-13T09:00:00+00:00",
    )
    assert "moved" not in captured["result"].lower()
    assert "taken" in captured["result"].lower()


# ── MemoryRecallProcessor ─────────────────────────────────────────────────

def _context_frame(messages: list[dict]) -> LLMContextFrame:
    return LLMContextFrame(context=LLMContext(messages=messages))


async def test_memory_recall_skips_when_no_patient(monkeypatch):
    called = []

    async def fake_recall(**kwargs):
        called.append(kwargs)
        return []

    monkeypatch.setattr(voice_mod, "recall_memories", fake_recall)
    proc = MemoryRecallProcessor(_session(patient_id=None))
    frame = _context_frame([{"role": "user", "content": "I want to book"}])
    await proc.process_frame(frame, FrameDirection.DOWNSTREAM)
    assert called == []
    assert len(frame.context.get_messages()) == 1


async def test_memory_recall_skips_when_last_message_not_user(monkeypatch):
    called = []

    async def fake_recall(**kwargs):
        called.append(kwargs)
        return []

    monkeypatch.setattr(voice_mod, "recall_memories", fake_recall)
    proc = MemoryRecallProcessor(_session())
    frame = _context_frame([{"role": "system", "content": "boot"}])
    await proc.process_frame(frame, FrameDirection.DOWNSTREAM)
    assert called == []


async def test_memory_recall_injects_memories_before_user_message(monkeypatch):
    async def fake_recall(*, patient_id, query, top_k):
        assert patient_id == "p-1"
        assert query == "I want to book"
        return [
            {"content": "Prefers afternoons", "score": 0.9},
            {"content": "Allergic to penicillin", "score": 0.8},
        ]

    monkeypatch.setattr(voice_mod, "recall_memories", fake_recall)
    proc = MemoryRecallProcessor(_session(patient_id="p-1"))
    frame = _context_frame([{"role": "user", "content": "I want to book"}])
    await proc.process_frame(frame, FrameDirection.DOWNSTREAM)

    messages = frame.context.get_messages()
    assert len(messages) == 2
    injected = messages[0]
    assert injected["role"] == "system"
    assert "Prefers afternoons" in injected["content"]
    assert "Allergic to penicillin" in injected["content"]
    assert messages[-1]["role"] == "user"


async def test_memory_recall_no_memories_does_not_insert(monkeypatch):
    async def fake_recall(**_):
        return []

    monkeypatch.setattr(voice_mod, "recall_memories", fake_recall)
    proc = MemoryRecallProcessor(_session(patient_id="p-1"))
    frame = _context_frame([{"role": "user", "content": "I want to book"}])
    await proc.process_frame(frame, FrameDirection.DOWNSTREAM)
    assert len(frame.context.get_messages()) == 1


async def test_memory_recall_failure_is_swallowed(monkeypatch):
    async def boom(**_):
        raise RuntimeError("pgvector died")

    monkeypatch.setattr(voice_mod, "recall_memories", boom)
    proc = MemoryRecallProcessor(_session(patient_id="p-1"))
    frame = _context_frame([{"role": "user", "content": "I want to book"}])
    # Must not raise — voice turn keeps going without memory rather than
    # leaving the caller in dead silence.
    await proc.process_frame(frame, FrameDirection.DOWNSTREAM)
    assert len(frame.context.get_messages()) == 1


# ── _persist_session ──────────────────────────────────────────────────────

async def test_persist_session_skips_without_patient(monkeypatch):
    called = []

    async def fake_persist(**kwargs):
        called.append(kwargs)

    monkeypatch.setattr(voice_mod, "persist_turn", fake_persist)
    session = _session(patient_id=None, phone=None)
    context = LLMContext(messages=[
        {"role": "user", "content": "u1"}, {"role": "assistant", "content": "a1"},
        {"role": "user", "content": "u2"}, {"role": "assistant", "content": "a2"},
    ])
    await voice_mod._persist_session(session, context)
    assert called == []


async def test_persist_session_skips_when_log_too_short(monkeypatch):
    called = []

    async def fake_persist(**kwargs):
        called.append(kwargs)

    monkeypatch.setattr(voice_mod, "persist_turn", fake_persist)
    session = _session()
    context = LLMContext(messages=[
        {"role": "user", "content": "hello"}, {"role": "assistant", "content": "hi"},
    ])
    await voice_mod._persist_session(session, context)
    assert called == []


async def test_persist_session_skips_when_no_user_text(monkeypatch):
    """All-assistant log (degenerate but possible) shouldn't persist."""
    called = []

    async def fake_persist(**kwargs):
        called.append(kwargs)

    monkeypatch.setattr(voice_mod, "persist_turn", fake_persist)
    session = _session()
    context = LLMContext(messages=[{"role": "assistant", "content": x} for x in ("a", "b", "c", "d")])
    await voice_mod._persist_session(session, context)
    assert called == []


async def test_persist_session_writes_when_meaningful(monkeypatch):
    captured: dict[str, Any] = {}

    async def fake_persist(**kwargs):
        captured.update(kwargs)

    monkeypatch.setattr(voice_mod, "persist_turn", fake_persist)
    session = _session(patient_id="p-1", phone="234555")
    context = LLMContext(messages=[
        {"role": "system", "content": "instructions"},
        {"role": "user", "content": "Can I book Tuesday?"},
        {"role": "assistant", "content": "Sure, at what time?"},
        {"role": "user", "content": "Around 3pm"},
        {"role": "assistant", "content": "Booked you for 3pm Tuesday."},
    ])
    await voice_mod._persist_session(session, context)
    assert captured["patient_id"] == "p-1"
    assert captured["session_id"] == "voice:234555"
    assert captured["intent"] == "voice_session"
    assert "Can I book Tuesday?" in captured["user_text"]
    assert "Around 3pm" in captured["user_text"]
    assert "Sure, at what time?" in captured["assistant_text"]
    assert "Booked you for 3pm" in captured["assistant_text"]
    assert 0 < captured["importance"] <= 1


async def test_persist_session_swallows_errors(monkeypatch):
    async def boom(**_):
        raise RuntimeError("db down")

    monkeypatch.setattr(voice_mod, "persist_turn", boom)
    session = _session()
    context = LLMContext(messages=[
        {"role": "user", "content": "u1"}, {"role": "assistant", "content": "a1"},
        {"role": "user", "content": "u2"}, {"role": "assistant", "content": "a2"},
    ])
    # Must not raise — the call already ended; a failed write-back shouldn't
    # surface as a crash.
    await voice_mod._persist_session(session, context)
