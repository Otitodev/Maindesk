"""Tool execution node (TRD §7.4).

Drives the appointment flows as a small, checkpoint-backed state machine so
book / reschedule / cancel actually commit on the text channels instead of the
reasoner merely *describing* a booking that never happened.

Two phases per turn:

  1. Resume — if a `pending` action is in flight (set on a previous turn), try
     to resolve the patient's latest reply against it (slot pick / yes / no)
     and execute the mutation via the shared `app.tools.appointments` helpers.
  2. Start  — otherwise open a new flow based on the triaged intent: offer
     slots (book), find the appointment + offer slots (reschedule), or find the
     appointment to confirm (cancel).

All real DB work lives in `app.tools.*`; this node only routes, tracks the
pending state, and collects results for the reasoner to phrase.
"""

from __future__ import annotations

import logging
from datetime import datetime

from app.agents.slotfill import resolve_selection
from app.agents.state import AgentState
from app.tools import appointments, escalation

log = logging.getLogger(__name__)

# Map a pending flow type onto the canonical Intent so the writer's importance
# heuristic still scores resumed turns as high-value bookings.
_PENDING_INTENT = {
    "book": "book_appointment",
    "reschedule": "reschedule",
    "cancel": "cancel",
}


def _parse_iso(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


async def _resume_pending(state: AgentState, pending: dict) -> AgentState | None:
    """Complete an in-flight action from the patient's latest reply.

    Returns updated state when the flow resolves (mutation done, or the patient
    backed out), or None to fall through to fresh intent handling when the
    reply doesn't map to the pending action."""
    msg = state["message"]
    ptype = pending.get("type")
    sel = await resolve_selection(pending, msg.content)
    decision = sel["decision"]

    # Patient backed out — drop the flow, let the reasoner acknowledge.
    if decision == "deny":
        return _resolved([{"tool": ptype, "status": "abandoned"}], ptype)

    if ptype in {"book", "reschedule"}:
        if decision != "select" or not sel["slot"]:
            return None  # not a slot pick — treat as fresh input
        if not msg.patient_id:  # mutation needs an identified patient
            return _resolved([{"tool": ptype, "error": "no_identity"}], ptype)
        ts = _parse_iso(sel["slot"])
        if ts is None:
            return None
        if ptype == "book":
            res = await appointments.book(msg.patient_id, ts, reason=pending.get("reason"))
        else:
            res = await appointments.reschedule(
                msg.patient_id, pending["appointment_id"], ts
            )
        return _resolved([res], ptype)

    if ptype == "cancel":
        if decision != "confirm":
            return None
        if not msg.patient_id:
            return _resolved([{"tool": ptype, "error": "no_identity"}], ptype)
        res = await appointments.cancel(msg.patient_id, pending["appointment_id"])
        return _resolved([res], ptype)

    return None


def _resolved(results: list[dict], ptype: str | None) -> AgentState:
    """State for a just-completed flow: clear pending, and pin intent +
    confidence so a low-confidence "9am"/"yes" reply can't trip the reasoner's
    escalation short-circuit."""
    return {
        "tool_results": results,
        "pending": None,
        "intent": _PENDING_INTENT.get(ptype, "unknown"),
        "intent_confidence": 1.0,
    }


async def _start_flow(state: AgentState) -> AgentState:
    """Open a fresh appointment flow based on the triaged intent."""
    intent = state.get("intent")
    msg = state["message"]
    results: list[dict] = []
    pending: dict | None = None

    if intent == "book_appointment":
        slots = await appointments.suggest_slots(msg)
        results.append(slots)
        if slots.get("slots"):
            # The message that triggered the booking intent doubles as the
            # reason for visit — free text, not a separate question turn.
            pending = {"type": "book", "slots": slots["slots"], "reason": msg.content}

    elif intent == "reschedule":
        existing = await appointments.find_existing(msg)
        results.append(existing)
        appts = existing.get("appointments") or []
        if appts:
            slots = await appointments.suggest_slots(msg)
            results.append(slots)
            if slots.get("slots"):
                pending = {
                    "type": "reschedule",
                    "appointment_id": appts[0]["id"],
                    "slots": slots["slots"],
                }

    elif intent == "cancel":
        existing = await appointments.find_existing(msg)
        results.append(existing)
        appts = existing.get("appointments") or []
        if appts:
            # No slots to offer — cancel just needs a yes/no on the found appt.
            pending = {"type": "cancel", "appointment_id": appts[0]["id"], "slots": []}

    elif intent == "escalate":
        results.append(await escalation.notify_staff(msg, reason="patient_request"))

    return {"tool_results": results, "pending": pending}


async def tools_node(state: AgentState) -> AgentState:
    msg = state.get("message")
    if msg is None:
        return {"tool_results": []}

    pending = state.get("pending")
    try:
        if pending:
            resumed = await _resume_pending(state, pending)
            if resumed is not None:
                return resumed
        return await _start_flow(state)
    except Exception as exc:
        log.exception("tool execution failed")
        return {"tool_results": [{"error": str(exc)}], "pending": None}
