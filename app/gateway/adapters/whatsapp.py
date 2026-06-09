"""Evolution API webhook adapter (TRD §6.1, §13).

Auth strategy is configurable: HMAC if the deployed Evolution version
supports it; otherwise shared-secret-header + IP allowlist.
"""

from __future__ import annotations

import hashlib
import hmac
import ipaddress
import logging
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request, status

from app.config import get_settings
from app.gateway.adapters.evolution_client import send_text
from app.gateway.cache import get_cached_session, set_cached_session
from app.gateway.redact import redact
from app.gateway.schema import PatientMessage, PatientReply

log = logging.getLogger(__name__)
router = APIRouter(prefix="/webhooks/whatsapp", tags=["whatsapp"])


def _verify_hmac(body: bytes, signature: str | None, secret: str) -> bool:
    if not signature:
        return False
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    # Accept either raw hex or "sha256=…" framing.
    candidate = signature.split("=", 1)[1] if "=" in signature else signature
    return hmac.compare_digest(expected, candidate)


def _verify_token(token: str | None, secret: str, client_ip: str, allowlist: list[str]) -> bool:
    if not token or not hmac.compare_digest(token, secret):
        return False
    if not allowlist:
        return True
    try:
        ip = ipaddress.ip_address(client_ip)
    except ValueError:
        return False
    for cidr in allowlist:
        try:
            if ip in ipaddress.ip_network(cidr, strict=False):
                return True
        except ValueError:
            continue
    return False


def _normalise(payload: dict[str, Any]) -> PatientMessage:
    """Map Evolution API's webhook envelope into a PatientMessage."""
    data = payload.get("data", payload)
    key = data.get("key", {})
    chat_id = key.get("remoteJid") or data.get("from") or "unknown"
    msg_id = key.get("id") or data.get("messageId") or "unknown"
    message_block = data.get("message", {}) or {}
    text = (
        message_block.get("conversation")
        or message_block.get("extendedTextMessage", {}).get("text")
        or data.get("body")
        or ""
    )
    media = (
        message_block.get("imageMessage", {}).get("url")
        or message_block.get("audioMessage", {}).get("url")
        or None
    )
    return PatientMessage(
        message_id=str(msg_id),
        session_id=f"whatsapp:{chat_id}",
        channel="whatsapp",
        content=text,
        media_url=media,
        platform_meta={"evolution": payload.get("event"), "raw_from": chat_id},
    )


@router.post("", status_code=status.HTTP_200_OK)
async def receive(
    request: Request,
    x_signature: str | None = Header(default=None, alias="X-Hub-Signature-256"),
    x_auth_token: str | None = Header(default=None, alias="X-Auth-Token"),
) -> dict[str, str]:
    settings = get_settings()
    body = await request.body()

    if settings.evolution_auth_mode == "hmac":
        if not _verify_hmac(body, x_signature, settings.evolution_webhook_secret):
            log.warning("whatsapp webhook hmac rejected")
            raise HTTPException(status_code=401, detail="invalid signature")
    else:
        client_ip = request.client.host if request.client else ""
        if not _verify_token(
            x_auth_token,
            settings.evolution_webhook_secret,
            client_ip,
            settings.evolution_ip_allowlist,
        ):
            log.warning("whatsapp webhook token/ip rejected (ip=%s)", client_ip)
            raise HTTPException(status_code=401, detail="unauthorized")

    payload = await request.json()
    try:
        msg = _normalise(payload)
    except Exception:
        log.exception("whatsapp normalise failed")
        raise HTTPException(status_code=422, detail="malformed payload")

    if not msg.content and not msg.media_url:
        # Status/typing/ack events — ack and drop.
        return {"status": "ignored"}

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
        chat_id = msg.platform_meta.get("raw_from") or msg.session_id.removeprefix("whatsapp:")
        ok = await send_text(chat_id=chat_id, text=safe)
        log.info(
            "whatsapp reply session=%s len=%d delivered=%s",
            msg.session_id, len(safe), ok,
        )
    return {"status": "ok"}
