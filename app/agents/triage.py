"""Intent triage agent (TRD §7.1).

Qwen-Turbo classifier — cheap and fast. Output is constrained JSON so
the orchestrator can route deterministically.
"""

from __future__ import annotations

import json
import logging

from app.agents.qwen_client import complete
from app.agents.state import AgentState
from app.config import get_settings

log = logging.getLogger(__name__)

_SYSTEM = """You classify patient messages for a clinic front desk.
Respond with strict JSON: {"intent": <one of book_appointment, reschedule,
cancel, ask_question, escalate, smalltalk, unknown>, "confidence": <0..1>}.
No prose."""


async def triage_node(state: AgentState) -> AgentState:
    s = get_settings()
    msg = state["message"]
    try:
        raw = await complete(
            model=s.qwen_model_turbo,
            system=_SYSTEM,
            user=msg.content,
            temperature=0.0,
            max_tokens=64,
        )
        parsed = json.loads(raw)
        intent = parsed.get("intent", "unknown")
        conf = float(parsed.get("confidence", 0.0))
    except (json.JSONDecodeError, ValueError, KeyError):
        log.warning("triage parse failed; defaulting to unknown")
        intent, conf = "unknown", 0.0
    return {"intent": intent, "intent_confidence": conf}
