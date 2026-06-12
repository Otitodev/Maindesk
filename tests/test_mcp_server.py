"""Tests for the HealthDesk MCP server (app/mcp/server.py).

The FastMCP @tool decorator returns the plain function, so tools are
tested directly with the DB/tool layer monkeypatched — same pattern as
the rest of the suite, no MCP transport required.
"""

from __future__ import annotations

import uuid

import pytest

import app.mcp.server as mcp_mod

PATIENT = {
    "id": uuid.UUID("99999999-8888-7777-6666-555555555555"),
    "full_name": "Adaeze Okafor",
    "phone": "2348012345678",
    "email": None,
    "preferences": "{}",
}


@pytest.fixture
def known_patient(monkeypatch):
    async def fake_resolve(phone):
        return dict(PATIENT) if phone == PATIENT["phone"] else None

    monkeypatch.setattr(mcp_mod, "resolve_by_phone", fake_resolve)


async def test_all_five_tools_registered():
    tools = {t.name for t in await mcp_mod.mcp.list_tools()}
    assert tools == {
        "suggest_slots",
        "lookup_patient",
        "book_appointment",
        "get_appointment_history",
        "escalate_to_staff",
    }


async def test_lookup_patient_found(known_patient):
    out = await mcp_mod.lookup_patient(PATIENT["phone"])
    assert out["full_name"] == "Adaeze Okafor"
    assert out["id"] == str(PATIENT["id"])
    assert "preferences" not in out  # internal field not leaked


async def test_lookup_patient_unknown(known_patient):
    out = await mcp_mod.lookup_patient("2340000000000")
    assert out["error"] == "unknown_patient"


async def test_suggest_slots_passthrough(monkeypatch):
    async def fake_suggest(_msg, *, n=3):
        return {"tool": "suggest_slots", "slots": [f"slot-{i}" for i in range(n)]}

    monkeypatch.setattr(mcp_mod.appointments, "suggest_slots", fake_suggest)
    out = await mcp_mod.suggest_slots(n=2)
    assert out == {"slots": ["slot-0", "slot-1"]}


async def test_book_appointment_happy_path(known_patient, monkeypatch):
    booked = {}

    async def fake_book(patient_id, starts_at):
        booked["patient_id"] = patient_id
        booked["starts_at"] = starts_at
        return {"tool": "book", "id": "appt-1", "starts_at": starts_at.isoformat()}

    monkeypatch.setattr(mcp_mod.appointments, "book", fake_book)
    out = await mcp_mod.book_appointment(PATIENT["phone"], "2026-06-20T14:00:00+00:00")
    assert out["booked"] is True
    assert out["appointment_id"] == "appt-1"
    assert booked["patient_id"] == str(PATIENT["id"])


async def test_book_appointment_unknown_patient(known_patient):
    out = await mcp_mod.book_appointment("2340000000000", "2026-06-20T14:00:00+00:00")
    assert out["error"] == "unknown_patient"


async def test_book_appointment_bad_timestamp(known_patient):
    out = await mcp_mod.book_appointment(PATIENT["phone"], "next Tuesday-ish")
    assert out["error"] == "bad_timestamp"


async def test_book_appointment_slot_taken(known_patient, monkeypatch):
    async def fake_book(patient_id, starts_at):
        return {"tool": "book", "error": "slot_taken", "starts_at": starts_at.isoformat()}

    monkeypatch.setattr(mcp_mod.appointments, "book", fake_book)
    out = await mcp_mod.book_appointment(PATIENT["phone"], "2026-06-20T14:00:00+00:00")
    assert out["error"] == "slot_taken"
    assert "booked" not in out


async def test_history_includes_upcoming_and_past(known_patient, monkeypatch):
    async def fake_history(patient_id, *, limit=10):
        return {"tool": "history", "upcoming": [{"id": "u1"}], "past": [{"id": "p1"}]}

    monkeypatch.setattr(mcp_mod.appointments, "history", fake_history)
    out = await mcp_mod.get_appointment_history(PATIENT["phone"])
    assert out["upcoming"] == [{"id": "u1"}]
    assert out["past"] == [{"id": "p1"}]
    assert out["patient"] == "Adaeze Okafor"


async def test_escalate_passes_context(known_patient, monkeypatch):
    captured = {}

    async def fake_notify(msg, *, reason):
        captured["msg"] = msg
        captured["reason"] = reason
        return {"tool": "escalate", "delivered": True, "reason": reason,
                "escalation_id": "esc-1"}

    monkeypatch.setattr(mcp_mod, "notify_staff", fake_notify)
    out = await mcp_mod.escalate_to_staff(
        "patient reports chest pain", message="please call back", phone=PATIENT["phone"]
    )
    assert out == {"escalated": True, "delivered": True, "escalation_id": "esc-1"}
    assert captured["reason"] == "patient reports chest pain"
    assert captured["msg"].channel == "mcp"
    assert captured["msg"].patient_id == str(PATIENT["id"])
    assert captured["msg"].content == "please call back"


async def test_escalate_works_without_phone(monkeypatch):
    async def fake_notify(msg, *, reason):
        return {"tool": "escalate", "delivered": False, "reason": reason,
                "escalation_id": None}

    monkeypatch.setattr(mcp_mod, "notify_staff", fake_notify)
    out = await mcp_mod.escalate_to_staff("caller needs a human")
    assert out["escalated"] is True
    assert out["escalation_id"] is None
