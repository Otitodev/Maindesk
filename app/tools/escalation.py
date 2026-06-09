"""Staff escalation (TRD §15 P2 #19).

Hackathon demo: posts to a Slack-compatible incoming webhook. Real
deployments would page on-call instead. Failure is non-fatal — we'd
rather greet the patient with a fallback than crash the turn.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.config import get_settings
from app.gateway.schema import PatientMessage

log = logging.getLogger(__name__)


async def notify_staff(msg: PatientMessage, *, reason: str) -> dict[str, Any]:
    s = get_settings()
    if not s.staff_escalation_webhook_url:
        log.info("escalation webhook not configured; would page (reason=%s)", reason)
        return {"tool": "escalate", "delivered": False, "reason": reason}

    payload = {
        "text": (
            f":rotating_light: Escalation requested\n"
            f"*session:* {msg.session_id}\n*reason:* {reason}\n"
            f"*message:* {msg.content[:300]}"
        )
    }
    try:
        async with httpx.AsyncClient(timeout=5.0) as http:
            r = await http.post(s.staff_escalation_webhook_url, json=payload)
            r.raise_for_status()
        return {"tool": "escalate", "delivered": True, "reason": reason}
    except Exception:
        log.exception("escalation webhook failed")
        return {"tool": "escalate", "delivered": False, "reason": reason}
