"""Evolution API outbound client.

Evolution exposes per-instance send endpoints:
    POST {base}/message/sendText/{instance}
    body: {"number": "<jid_or_e164>", "text": "..."}
    headers: apikey: <instance api key>

We keep a single httpx.AsyncClient per process, reused across requests
so we get connection pooling instead of opening a TCP+TLS session for
every reply.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Final

import httpx

from app.config import get_settings

log = logging.getLogger(__name__)

_client: httpx.AsyncClient | None = None
_client_lock = asyncio.Lock()

# Evolution accepts JIDs (e.g. "234801…@s.whatsapp.net") or bare numbers.
# When we get a JID back from the webhook we strip the suffix — group
# chats use "@g.us" which we deliberately do NOT send to.
_USER_JID_SUFFIX: Final[str] = "@s.whatsapp.net"
_GROUP_JID_SUFFIX: Final[str] = "@g.us"


async def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        async with _client_lock:
            if _client is None:
                s = get_settings()
                _client = httpx.AsyncClient(
                    base_url=s.evolution_api_url.rstrip("/"),
                    timeout=s.evolution_send_timeout,
                    headers={"apikey": s.evolution_api_key},
                )
    return _client


async def close_client() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


def _to_number(chat_id: str) -> str | None:
    """Return the dial-ready recipient, or None if we shouldn't send."""
    if chat_id.endswith(_GROUP_JID_SUFFIX):
        # Refuse to broadcast to a group; the patient identifier must be
        # a single user.
        return None
    if chat_id.endswith(_USER_JID_SUFFIX):
        return chat_id[: -len(_USER_JID_SUFFIX)]
    return chat_id


async def send_text(*, chat_id: str, text: str) -> bool:
    """POST a text reply to Evolution. Returns True on 2xx, False otherwise.

    Failures are logged, never raised — the webhook handler has already
    acked, and a dropped outbound is preferable to crashing a turn.
    """
    s = get_settings()
    if s.healthdesk_demo_mode:
        from app.gateway.demo_inbox import record_whatsapp
        record_whatsapp(chat_id=chat_id, text=text)
        log.info("whatsapp demo-mode delivery chat=%s len=%d", chat_id, len(text))
        return True
    if not (s.evolution_api_url and s.evolution_api_key and s.evolution_instance):
        log.warning("evolution outbound not configured; skipping send chat=%s", chat_id)
        return False

    number = _to_number(chat_id)
    if number is None:
        log.info("evolution send refused (group jid) chat=%s", chat_id)
        return False

    path = f"/message/sendText/{s.evolution_instance}"
    payload = {"number": number, "text": text}
    try:
        client = await _get_client()
        resp = await client.post(path, json=payload)
        if resp.status_code >= 400:
            log.warning(
                "evolution send non-2xx chat=%s status=%d body=%s",
                chat_id, resp.status_code, resp.text[:300],
            )
            return False
        return True
    except httpx.HTTPError:
        log.exception("evolution send transport error chat=%s", chat_id)
        return False
