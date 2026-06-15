"""Email outbound client (Postmark-shaped).

Sends a reply through the provider's transactional-email API:
    POST {base}/email
    headers: X-Postmark-Server-Token: <token>
    body: {"From","To","Subject","TextBody","Headers":[...]}

Like the Evolution client, we keep one pooled httpx.AsyncClient per process and
never raise on send failure — the webhook has already acked, and a dropped
outbound email is preferable to crashing a turn. Swap the base URL / header for
another provider (SendGrid, Mailgun) without touching the adapter.
"""

from __future__ import annotations

import asyncio
import logging

import httpx

from app.config import get_settings

log = logging.getLogger(__name__)

_client: httpx.AsyncClient | None = None
_client_lock = asyncio.Lock()


async def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        async with _client_lock:
            if _client is None:
                s = get_settings()
                _client = httpx.AsyncClient(
                    base_url=s.email_api_url.rstrip("/"),
                    timeout=s.email_send_timeout,
                    headers={
                        "X-Postmark-Server-Token": s.email_api_token,
                        "Accept": "application/json",
                    },
                )
    return _client


async def close_client() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


async def send_email(
    *, to: str, subject: str, text: str, in_reply_to: str | None = None
) -> bool:
    """POST a reply. Returns True on 2xx, False otherwise (logged, never raised).

    `in_reply_to` threads the reply under the patient's original email by
    setting the In-Reply-To / References headers to its Message-ID."""
    s = get_settings()
    if not (s.email_api_token and s.email_from):
        log.warning("email outbound not configured; skipping send to=%s", to)
        return False

    body: dict = {
        "From": s.email_from,
        "To": to,
        "Subject": subject,
        "TextBody": text,
        "MessageStream": "outbound",
    }
    if in_reply_to:
        body["Headers"] = [
            {"Name": "In-Reply-To", "Value": in_reply_to},
            {"Name": "References", "Value": in_reply_to},
        ]
    try:
        client = await _get_client()
        resp = await client.post("/email", json=body)
        if resp.status_code >= 400:
            log.warning(
                "email send non-2xx to=%s status=%d body=%s",
                to, resp.status_code, resp.text[:300],
            )
            return False
        return True
    except httpx.HTTPError:
        log.exception("email send transport error to=%s", to)
        return False
