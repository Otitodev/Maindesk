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
        body = (
            f"MainDesk paused a conversation and needs you.\n"
            f"session: {msg.session_id}\n"
            f"reason: {reason}\n"
            f"message: {msg.content[:300]}"
        )
        # Send Slack (`text`), Discord (`content`), and ntfy (`message`) keys
        # in one payload so the same URL setting works for any of them.
        # Extra keys are ignored by receivers that don't use them.
        payload = {"text": body, "content": body, "message": body}
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


# ── Active resume: push the staff's decision back to the patient ────────

async def deliver_staff_note(esc: dict) -> dict[str, Any]:
    """Fire the staff's note back to the patient on the channel they came in on.

    Called from the /staff action handler after `resolve_escalation` returns
    the resolved row. Best-effort: any failure is logged but never raised —
    the queue row still resolved successfully; the outbound push is a bonus.

    Skips when:
      - status == 'closed' (staff marked it non-actionable)
      - no note was written (nothing to say)
      - channel has no outbound path (voice today; web has no persistent socket)
    """
    if esc.get("status") == "closed":
        return {"delivered": False, "skipped": "closed"}
    note = (esc.get("note") or "").strip()
    if not note:
        return {"delivered": False, "skipped": "no-note"}

    channel = (esc.get("channel") or "").lower()
    text = f"Update from our team: {note}"

    if channel == "whatsapp":
        from app.gateway.adapters.evolution_client import send_text
        chat_id = _phone_to_chat_id(esc)
        if not chat_id:
            log.info("resume skipped: no phone for esc %s", esc.get("id"))
            return {"delivered": False, "skipped": "no-phone"}
        ok = await send_text(chat_id=chat_id, text=text)
        return {"delivered": bool(ok), "channel": "whatsapp"}

    if channel == "email":
        from app.gateway.adapters.email_client import send_email
        to = _email_from_esc(esc)
        if not to:
            log.info("resume skipped: no email for esc %s", esc.get("id"))
            return {"delivered": False, "skipped": "no-email"}
        ok = await send_email(
            to=to,
            subject="Update from your clinic",
            text=text,
            in_reply_to=None,
        )
        return {"delivered": bool(ok), "channel": "email"}

    # Voice: no outbound call today (would need SIP outbound + telephony
    # config). Web: the browser session may be closed. Both are logged
    # but skipped so the queue action still succeeds.
    log.info("resume skipped: channel=%s has no outbound path", channel)
    return {"delivered": False, "skipped": f"channel:{channel}"}


def _phone_to_chat_id(esc: dict) -> str | None:
    """Prefer the patient row's phone; fall back to parsing the session_id
    prefix. Evolution expects the number without a leading '+' as chat_id."""
    phone = esc.get("phone") or ""
    if not phone:
        sid = esc.get("session_id") or ""
        if sid.startswith("whatsapp:"):
            phone = sid.split(":", 1)[1]
    phone = phone.strip().lstrip("+")
    return phone or None


def _email_from_esc(esc: dict) -> str | None:
    email = (esc.get("email") or "").strip()
    if email:
        return email
    sid = esc.get("session_id") or ""
    if sid.startswith("email:"):
        return sid.split(":", 1)[1].strip() or None
    return None
