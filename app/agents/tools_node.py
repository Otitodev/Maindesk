"""Tool execution node (TRD §7.4).

Dispatches by intent. Real implementations live in app.tools.* — this
file just routes and collects results so the reasoner can summarise.
"""

from __future__ import annotations

import logging

from app.agents.state import AgentState
from app.tools import appointments, escalation

log = logging.getLogger(__name__)


async def tools_node(state: AgentState) -> AgentState:
    intent = state.get("intent")
    msg = state.get("message")
    if msg is None:
        return {"tool_results": []}

    results: list[dict] = []
    try:
        if intent == "book_appointment":
            results.append(await appointments.suggest_slots(msg))
        elif intent == "reschedule":
            results.append(await appointments.find_existing(msg))
        elif intent == "cancel":
            results.append(await appointments.find_existing(msg))
        elif intent == "escalate":
            results.append(await escalation.notify_staff(msg, reason="patient_request"))
    except Exception as exc:
        log.exception("tool execution failed")
        results.append({"error": str(exc)})

    return {"tool_results": results}
