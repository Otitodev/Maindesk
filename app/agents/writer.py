"""Memory write-back node (TRD §9.4).

Fire-and-forget: we don't block the reply on the embed+insert. Reasoner
decides what's worth keeping via a lightweight importance heuristic;
summarisation is a Qwen-Turbo call to keep cost flat.
"""

from __future__ import annotations

import asyncio
import logging

from app.agents.state import AgentState
from app.memory.write import persist_turn

log = logging.getLogger(__name__)


def _importance(state: AgentState) -> float:
    """Cheap heuristic — keep the LLM out of the hot path. Booking/cancel
    interactions and escalations are high-value; smalltalk isn't worth
    keeping."""
    intent = state.get("intent", "unknown")
    if intent in {"book_appointment", "reschedule", "cancel"}:
        return 0.8
    if intent == "escalate":
        return 0.9
    if intent == "ask_question":
        return 0.5
    return 0.2


async def writer_node(state: AgentState) -> AgentState:
    msg = state.get("message")
    reply = state.get("reply")
    if msg is None or reply is None or not msg.patient_id:
        return {}

    score = _importance(state)
    if score < 0.3:
        return {}

    asyncio.create_task(
        persist_turn(
            patient_id=msg.patient_id,
            session_id=msg.session_id,
            user_text=msg.content,
            assistant_text=reply.content,
            importance=score,
            intent=state.get("intent", "unknown"),
        )
    )
    return {}
