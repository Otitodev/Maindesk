"""Web-chat webhook adapter (TRD §6.1).

Browser widget posts JSON; we normalise to PatientMessage, hand off to
the orchestrator, return the reply inline (synchronous, unlike WhatsApp).
"""

from __future__ import annotations

import hmac
import logging
import uuid

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field

from app.config import get_settings
from app.gateway.cache import get_cached_session, set_cached_session
from app.gateway.limiter import limiter
from app.gateway.redact import redact
from app.gateway.schema import PatientMessage, PatientReply

log = logging.getLogger(__name__)
router = APIRouter(prefix="/webhooks/web", tags=["web"])


class WebInbound(BaseModel):
    session_id: str
    content: str
    patient_id: str | None = None
    message_id: str = Field(default_factory=lambda: str(uuid.uuid4()))


class WebOutbound(BaseModel):
    session_id: str
    content: str


@router.post("", response_model=WebOutbound, status_code=status.HTTP_200_OK)
@limiter.limit("30/minute")
async def receive(payload: WebInbound, request: Request) -> WebOutbound:
    settings = get_settings()
    if settings.web_api_key:
        auth_header = request.headers.get("X-API-Key", "")
        if not hmac.compare_digest(auth_header, settings.web_api_key):
            raise HTTPException(status_code=401, detail="unauthorized")

    if not payload.content.strip():
        raise HTTPException(status_code=422, detail="empty content")

    msg = PatientMessage(
        message_id=payload.message_id,
        session_id=f"web:{payload.session_id}",
        patient_id=payload.patient_id,
        channel="web",
        content=payload.content,
    )

    graph = request.app.state.graph
    cached = get_cached_session(msg.session_id)
    config = {"configurable": {"thread_id": msg.session_id}}
    result = await graph.ainvoke(
        {"message": msg, "session_cache": cached},
        config=config,
    )
    set_cached_session(msg.session_id, result.get("session_cache"))

    reply: PatientReply | None = result.get("reply")
    safe = redact(reply.content) if reply else "Sorry, I had trouble with that — could you try again?"
    return WebOutbound(session_id=msg.session_id, content=safe)
