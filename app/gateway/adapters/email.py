"""Email channel webhook adapter (TRD §6.1).

A provider parse webhook (Postmark Inbound, SendGrid Parse, …) POSTs the
inbound email as JSON; we normalise it to a PatientMessage, run the same
orchestrator graph as every other channel, and send the reply back through the
provider — threaded under the original message. Async like WhatsApp: we ack the
webhook and deliver the reply out-of-band.
"""

from __future__ import annotations

import hmac
import logging
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request, status

from app.config import get_settings
from app.gateway.adapters.email_client import send_email
from app.gateway.cache import get_cached_session, set_cached_session
from app.gateway.limiter import limiter
from app.gateway.redact import redact
from app.gateway.schema import PatientMessage, PatientReply
from app.memory.profile import resolve_by_email

log = logging.getLogger(__name__)
router = APIRouter(prefix="/webhooks/email", tags=["email"])


def _incoming_message_id(payload: dict[str, Any]) -> str | None:
    """The original email's Message-ID header, used to thread the reply."""
    for header in payload.get("Headers", []) or []:
        if str(header.get("Name", "")).lower() == "message-id":
            return header.get("Value")
    return payload.get("MessageID")


def _normalise(payload: dict[str, Any]) -> PatientMessage:
    """Map a provider inbound-email envelope into a PatientMessage."""
    from_full = payload.get("FromFull") or {}
    from_email = (from_full.get("Email") or payload.get("From") or "").strip().lower()
    subject = payload.get("Subject") or ""
    # StrippedTextReply drops the quoted thread; fall back to the full body.
    text = (payload.get("StrippedTextReply") or payload.get("TextBody") or "").strip()
    return PatientMessage(
        message_id=str(payload.get("MessageID") or "unknown"),
        session_id=f"email:{from_email}",
        channel="email",
        content=text,
        platform_meta={
            "from": from_email,
            "subject": subject,
            "in_reply_to": _incoming_message_id(payload),
        },
    )


@router.post("", status_code=status.HTTP_200_OK)
@limiter.limit("30/minute")
async def receive(
    request: Request,
    x_webhook_secret: str | None = Header(default=None, alias="X-Webhook-Secret"),
) -> dict[str, str]:
    settings = get_settings()
    if settings.healthdesk_demo_mode:
        # Demo mode: accept unsigned POSTs so the loop is exercisable
        # without a real Postmark instance. Never enable in production.
        pass
    elif settings.email_webhook_secret:
        if not x_webhook_secret or not hmac.compare_digest(
            x_webhook_secret, settings.email_webhook_secret
        ):
            log.warning("email webhook secret rejected")
            raise HTTPException(status_code=401, detail="unauthorized")

    payload = await request.json()
    try:
        msg = _normalise(payload)
    except Exception:
        log.exception("email normalise failed")
        raise HTTPException(status_code=422, detail="malformed payload")

    from_email = msg.platform_meta.get("from", "")
    if not from_email or not msg.content:
        # Auto-replies, empty bodies, parse noise — ack and drop.
        return {"status": "ignored"}

    # Resolve identity by email so memory recall can run; unknown senders
    # proceed without a patient_id (no recall), same as the web widget.
    try:
        profile = await resolve_by_email(from_email)
        if profile:
            msg = msg.model_copy(update={"patient_id": str(profile["id"])})
    except Exception:
        log.exception("email identity resolution failed email=%s", from_email)

    graph = request.app.state.graph
    cached = get_cached_session(msg.session_id)
    config = {"configurable": {"thread_id": msg.session_id}}
    result = await graph.ainvoke(
        {"message": msg, "session_cache": cached},
        config=config,
    )
    set_cached_session(msg.session_id, result.get("session_cache"))

    reply: PatientReply | None = result.get("reply")
    if reply is not None and reply.content.strip():
        safe = redact(reply.content)
        subject = msg.platform_meta.get("subject") or "Your message"
        re_subject = subject if subject.lower().startswith("re:") else f"Re: {subject}"
        ok = await send_email(
            to=from_email,
            subject=re_subject,
            text=safe,
            in_reply_to=msg.platform_meta.get("in_reply_to"),
        )
        log.info("email reply to=%s len=%d delivered=%s", from_email, len(safe), ok)
    return {"status": "ok"}
