"""Slot-fill resolver (TRD §7.4).

Maps a patient's free-text reply onto a concrete choice within an in-flight
booking / reschedule / cancel flow. Used by the tools node to decide whether
the latest message means "book the 9 AM slot", "yes go ahead", "no thanks", or
"that's unrelated, treat it as a fresh request".

Mirrors the triage pattern: a constrained Qwen-Turbo call returning strict
JSON, with a defensive guard so a hallucinated slot that was never offered
can never be acted on.
"""

from __future__ import annotations

import json
import logging

from app.agents.qwen_client import complete
from app.config import get_settings

log = logging.getLogger(__name__)

_SYSTEM = """You match a patient's reply to a pending clinic front-desk action.
You are given the action type and the options that were offered. Respond with
strict JSON and no prose:
{"decision": <one of "select", "confirm", "deny", "none">, "slot": <the exact
chosen option string copied from the offered list, or null>}

Definitions:
- "select": the patient picked one of the offered time slots. Copy the exact
  matching slot string into "slot".
- "confirm": the patient agreed to proceed (e.g. "yes", "that's fine", "go ahead").
- "deny": the patient declined or wants to stop (e.g. "no", "never mind", "cancel that").
- "none": the reply does not map to any option — it's a new question or request.
Only ever copy a slot string that appears verbatim in the offered list."""


async def resolve_selection(pending: dict, message: str) -> dict:
    """Return {"decision": ..., "slot": ...} for the patient's reply.

    `pending` carries the in-flight action: {"type": "book"|"reschedule"|"cancel",
    "slots": [...iso strings...], ...}. On any parse failure we fail safe to
    "none" so the message is treated as fresh input rather than mis-actioned."""
    options = pending.get("slots") or []
    user = (
        f"Action: {pending.get('type')}\n"
        f"Offered slots: {options}\n"
        f"Patient reply: {message}"
    )
    s = get_settings()
    try:
        raw = await complete(
            model=s.qwen_model_turbo,
            system=_SYSTEM,
            user=user,
            temperature=0.0,
            max_tokens=80,
        )
        parsed = json.loads(raw)
    except (json.JSONDecodeError, ValueError, KeyError, TypeError):
        log.warning("slotfill parse failed; treating reply as 'none'")
        return {"decision": "none", "slot": None}

    decision = parsed.get("decision", "none")
    slot = parsed.get("slot")
    # Never act on a slot that wasn't actually offered.
    if slot is not None and slot not in options:
        slot = None
        if decision == "select":
            decision = "none"
    if decision not in {"select", "confirm", "deny", "none"}:
        decision = "none"
    return {"decision": decision, "slot": slot}
