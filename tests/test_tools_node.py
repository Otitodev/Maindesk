"""Tests for the tools-node appointment state machine.

Covers both phases: starting a flow from a fresh intent (offer slots / find
existing + set `pending`) and resuming an in-flight flow from the patient's
reply (slot pick, confirm, deny, fall-through, missing identity).
"""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.agents import tools_node as tn
from app.gateway.schema import PatientMessage

_SLOT = "2026-07-01T09:00:00+00:00"


def _msg(content="hi", patient_id="p-1"):
    return PatientMessage(
        message_id="m", session_id="web:s", patient_id=patient_id,
        channel="web", content=content,
    )


# ── starting a flow ─────────────────────────────────────────────────────

async def test_book_intent_offers_slots_and_sets_pending(monkeypatch):
    monkeypatch.setattr(
        tn.appointments, "suggest_slots",
        AsyncMock(return_value={"tool": "suggest_slots", "slots": [_SLOT]}),
    )
    out = await tn.tools_node(
        {"message": _msg("I need a checkup"), "intent": "book_appointment"}
    )
    # The triggering message doubles as the reason for visit.
    assert out["pending"] == {"type": "book", "slots": [_SLOT], "reason": "I need a checkup"}
    assert out["tool_results"][0]["tool"] == "suggest_slots"


async def test_reschedule_intent_finds_then_offers(monkeypatch):
    monkeypatch.setattr(
        tn.appointments, "find_existing",
        AsyncMock(return_value={
            "tool": "find_existing",
            "appointments": [{"id": "a1", "starts_at": _SLOT, "status": "booked"}],
        }),
    )
    monkeypatch.setattr(
        tn.appointments, "suggest_slots",
        AsyncMock(return_value={"tool": "suggest_slots", "slots": [_SLOT]}),
    )
    out = await tn.tools_node({"message": _msg(), "intent": "reschedule"})
    assert out["pending"]["type"] == "reschedule"
    assert out["pending"]["appointment_id"] == "a1"


async def test_cancel_intent_sets_pending_without_slots(monkeypatch):
    monkeypatch.setattr(
        tn.appointments, "find_existing",
        AsyncMock(return_value={
            "tool": "find_existing",
            "appointments": [{"id": "a1", "starts_at": _SLOT, "status": "booked"}],
        }),
    )
    out = await tn.tools_node({"message": _msg(), "intent": "cancel"})
    assert out["pending"] == {"type": "cancel", "appointment_id": "a1", "slots": []}


async def test_book_intent_no_slots_leaves_pending_none(monkeypatch):
    monkeypatch.setattr(
        tn.appointments, "suggest_slots",
        AsyncMock(return_value={"tool": "suggest_slots", "slots": []}),
    )
    out = await tn.tools_node({"message": _msg(), "intent": "book_appointment"})
    assert out["pending"] is None


# ── resuming a flow ─────────────────────────────────────────────────────

async def test_pending_book_select_books_and_clears(monkeypatch):
    monkeypatch.setattr(
        tn, "resolve_selection",
        AsyncMock(return_value={"decision": "select", "slot": _SLOT}),
    )
    book_mock = AsyncMock(return_value={"tool": "book", "id": "b1", "starts_at": _SLOT})
    monkeypatch.setattr(tn.appointments, "book", book_mock)
    out = await tn.tools_node({
        "message": _msg("9am"), "intent": "unknown",
        "pending": {"type": "book", "slots": [_SLOT], "reason": "sore throat"},
    })
    assert out["pending"] is None
    assert out["tool_results"][0]["id"] == "b1"
    # Low-confidence reply must not trip the reasoner's escalation guard.
    assert out["intent_confidence"] == 1.0
    # The reason captured when the flow started rides along to the booking.
    book_mock.assert_awaited_once_with("p-1", tn._parse_iso(_SLOT), reason="sore throat")
    assert out["intent"] == "book_appointment"
    book_mock.assert_awaited_once()


async def test_pending_cancel_confirm_cancels(monkeypatch):
    monkeypatch.setattr(
        tn, "resolve_selection",
        AsyncMock(return_value={"decision": "confirm", "slot": None}),
    )
    cancel_mock = AsyncMock(return_value={"tool": "cancel", "status": "cancelled"})
    monkeypatch.setattr(tn.appointments, "cancel", cancel_mock)
    out = await tn.tools_node({
        "message": _msg("yes"),
        "pending": {"type": "cancel", "appointment_id": "a1", "slots": []},
    })
    assert out["pending"] is None
    cancel_mock.assert_awaited_once_with("p-1", "a1")


async def test_pending_reschedule_select_reschedules(monkeypatch):
    monkeypatch.setattr(
        tn, "resolve_selection",
        AsyncMock(return_value={"decision": "select", "slot": _SLOT}),
    )
    resched = AsyncMock(return_value={"tool": "reschedule", "id": "n1", "starts_at": _SLOT})
    monkeypatch.setattr(tn.appointments, "reschedule", resched)
    out = await tn.tools_node({
        "message": _msg("the 9am one"),
        "pending": {"type": "reschedule", "appointment_id": "a1", "slots": [_SLOT]},
    })
    assert out["pending"] is None
    resched.assert_awaited_once()
    assert resched.call_args[0][1] == "a1"  # old appointment id passed through


async def test_pending_deny_abandons(monkeypatch):
    monkeypatch.setattr(
        tn, "resolve_selection",
        AsyncMock(return_value={"decision": "deny", "slot": None}),
    )
    out = await tn.tools_node({
        "message": _msg("no thanks"),
        "pending": {"type": "book", "slots": [_SLOT]},
    })
    assert out["pending"] is None
    assert out["tool_results"][0]["status"] == "abandoned"


async def test_pending_none_falls_through_to_fresh_intent(monkeypatch):
    """An unrelated reply mid-flow is treated as fresh input, not mis-actioned."""
    monkeypatch.setattr(
        tn, "resolve_selection",
        AsyncMock(return_value={"decision": "none", "slot": None}),
    )
    suggest = AsyncMock(return_value={"tool": "suggest_slots", "slots": [_SLOT]})
    monkeypatch.setattr(tn.appointments, "suggest_slots", suggest)
    book_mock = AsyncMock()
    monkeypatch.setattr(tn.appointments, "book", book_mock)
    out = await tn.tools_node({
        "message": _msg("actually, are you open Saturdays?"),
        "intent": "book_appointment",
        "pending": {"type": "book", "slots": ["stale-slot"]},
    })
    suggest.assert_awaited_once()       # re-entered the start phase
    book_mock.assert_not_awaited()      # nothing booked on a fall-through


async def test_pending_book_select_without_identity(monkeypatch):
    monkeypatch.setattr(
        tn, "resolve_selection",
        AsyncMock(return_value={"decision": "select", "slot": _SLOT}),
    )
    book_mock = AsyncMock()
    monkeypatch.setattr(tn.appointments, "book", book_mock)
    out = await tn.tools_node({
        "message": _msg("9am", patient_id=None),
        "pending": {"type": "book", "slots": [_SLOT]},
    })
    assert out["tool_results"][0]["error"] == "no_identity"
    book_mock.assert_not_awaited()
