"""HealthDesk MCP server — clinic tools for any MCP-compatible client.

Exposes the same tool layer the LangGraph agent and voice worker use, so
Claude Desktop / Cursor / any MCP client can work the front desk — look up
patients, check slots, book, reschedule, cancel, and escalate — without
touching the web UI. Aimed at staff/admin "copilot" use, not patients.

Run (stdio transport, what MCP clients spawn):

    python -m app.mcp.server

Claude Desktop config (claude_desktop_config.json):

    {
      "mcpServers": {
        "healthdesk": {
          "command": "<repo>/.venv/Scripts/python.exe",
          "args": ["-m", "app.mcp.server"],
          "env": { "PYTHONPATH": "<repo>" }
        }
      }
    }

Requires DATABASE_URL (and optionally STAFF_ESCALATION_WEBHOOK_URL) in
the repo's .env — the server reads the same settings as the gateway.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from mcp.server.fastmcp import FastMCP

from app.gateway.schema import PatientMessage
from app.memory.profile import resolve_by_phone
from app.tools import appointments
from app.tools.escalation import notify_staff

log = logging.getLogger("mcp")

mcp = FastMCP("healthdesk")


def _msg(content: str, patient_id: str | None = None) -> PatientMessage:
    """Wrap MCP tool input into the PatientMessage shape app.tools.* expects."""
    return PatientMessage(
        message_id="mcp",
        session_id="mcp:client",
        patient_id=patient_id,
        channel="mcp",
        content=content,
    )


async def _patient_or_error(phone: str) -> dict[str, Any]:
    patient = await resolve_by_phone(phone)
    if patient is None:
        return {"error": "unknown_patient", "phone": phone,
                "hint": "No patient with this phone on file. Check the number with the caller."}
    patient["id"] = str(patient["id"])
    return patient


@mcp.tool()
async def suggest_slots(n: int = 3) -> dict[str, Any]:
    """Suggest the next available 30-minute appointment slots in the
    clinic's timezone. Returns ISO 8601 timestamps that can be passed
    directly to book_appointment."""
    result = await appointments.suggest_slots(_msg("suggest slots"), n=n)
    return {"slots": result.get("slots", [])}


@mcp.tool()
async def lookup_patient(phone: str) -> dict[str, Any]:
    """Resolve a patient profile by phone number (digits only, with
    country code, e.g. 2348012345678). Returns the profile or an
    unknown_patient error."""
    patient = await _patient_or_error(phone)
    if "error" in patient:
        return patient
    return {
        "id": patient["id"],
        "full_name": patient.get("full_name"),
        "phone": patient.get("phone"),
        "email": patient.get("email"),
    }


@mcp.tool()
async def book_appointment(phone: str, slot_iso: str) -> dict[str, Any]:
    """Book an appointment for the patient with this phone number at
    `slot_iso` (an ISO 8601 timestamp confirmed via suggest_slots).
    Refuses double-bookings: returns slot_taken if the slot just went."""
    patient = await _patient_or_error(phone)
    if "error" in patient:
        return patient
    try:
        starts_at = datetime.fromisoformat(slot_iso.replace("Z", "+00:00"))
    except ValueError:
        return {"error": "bad_timestamp", "slot_iso": slot_iso,
                "hint": "Pass an ISO 8601 timestamp from suggest_slots."}
    result = await appointments.book(patient["id"], starts_at)
    if result.get("error"):
        return {"error": result["error"], "starts_at": result.get("starts_at")}
    return {"booked": True, "appointment_id": result["id"], "starts_at": result["starts_at"],
            "patient": patient.get("full_name")}


@mcp.tool()
async def cancel_appointment(phone: str, appointment_id: str) -> dict[str, Any]:
    """Cancel a booked appointment for the patient with this phone number.
    `appointment_id` comes from get_appointment_history. Scoped to the
    patient, so it never touches another patient's booking. Returns
    not_found if there's no matching booked appointment."""
    patient = await _patient_or_error(phone)
    if "error" in patient:
        return patient
    result = await appointments.cancel(patient["id"], appointment_id)
    if result.get("error"):
        return {"error": result["error"], "appointment_id": appointment_id}
    return {"cancelled": True, "appointment_id": result["id"],
            "starts_at": result["starts_at"], "patient": patient.get("full_name")}


@mcp.tool()
async def reschedule_appointment(
    phone: str, appointment_id: str, new_slot_iso: str
) -> dict[str, Any]:
    """Move an existing booked appointment to a new time. `appointment_id`
    comes from get_appointment_history; `new_slot_iso` is an ISO 8601 slot
    from suggest_slots. Atomic: if the new slot is taken, the original is
    kept and slot_taken is returned."""
    patient = await _patient_or_error(phone)
    if "error" in patient:
        return patient
    try:
        new_ts = datetime.fromisoformat(new_slot_iso.replace("Z", "+00:00"))
    except ValueError:
        return {"error": "bad_timestamp", "new_slot_iso": new_slot_iso,
                "hint": "Pass an ISO 8601 timestamp from suggest_slots."}
    result = await appointments.reschedule(patient["id"], appointment_id, new_ts)
    if result.get("error"):
        return {"error": result["error"], "starts_at": result.get("starts_at"),
                "appointment_id": appointment_id}
    return {"rescheduled": True, "appointment_id": result["id"],
            "old_appointment_id": result["old_appointment_id"],
            "starts_at": result["starts_at"], "patient": patient.get("full_name")}


@mcp.tool()
async def get_appointment_history(phone: str) -> dict[str, Any]:
    """Upcoming and past appointments for the patient with this phone
    number, most relevant first."""
    patient = await _patient_or_error(phone)
    if "error" in patient:
        return patient
    result = await appointments.history(patient["id"])
    return {"patient": patient.get("full_name"),
            "upcoming": result["upcoming"], "past": result["past"]}


@mcp.tool()
async def escalate_to_staff(reason: str, message: str = "", phone: str = "") -> dict[str, Any]:
    """Page clinic staff with a reason and optional patient context.
    Use for medical questions, urgent situations, or anything needing
    human judgement. The escalation lands in the staff dashboard queue."""
    patient_id: str | None = None
    if phone:
        patient = await resolve_by_phone(phone)
        if patient:
            patient_id = str(patient["id"])
    result = await notify_staff(
        _msg(message or reason, patient_id=patient_id), reason=reason
    )
    return {"escalated": True, "delivered": result.get("delivered", False),
            "escalation_id": result.get("escalation_id")}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    mcp.run()
