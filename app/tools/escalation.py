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
from app.dashboard import events
from app.dashboard.store import record_escalation
from app.gateway.schema import PatientMessage

log = logging.getLogger(__name__)


async def notify_staff(msg: PatientMessage, *, reason: str) -> dict[str, Any]:
    s = get_settings()
    delivered = False
    if not s.staff_escalation_webhook_url:
        log.info("escalation webhook not configured; would page (reason=%s)", reason)
    else:
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
            delivered = True
        except Exception:
            log.exception("escalation webhook failed")

    # Feed the human-in-the-loop dashboard queue. Best-effort: the row
    # insert no-ops if Postgres is down, and the SSE ping only reaches
    # dashboards served by this process (voice picks it up via poll).
    esc_id = await record_escalation(msg, reason=reason, delivered=delivered)
    if esc_id:
        events.publish(esc_id)

    return {"tool": "escalate", "delivered": delivered, "reason": reason, "escalation_id": esc_id}
