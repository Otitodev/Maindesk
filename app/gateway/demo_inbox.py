"""In-memory outbound inbox for demo mode.

When HEALTHDESK_DEMO_MODE=true, the WhatsApp and email adapters divert
outbound replies into a bounded ring buffer instead of hitting Evolution
or Postmark. Retrieval endpoints let a demo caller confirm the loop ran
end-to-end without provisioning external services.

Not durable. Not thread-safe across processes. Demo/hackathon only.
"""

from __future__ import annotations

import time
from collections import deque
from threading import Lock
from typing import Deque

from fastapi import APIRouter

_MAX_ITEMS = 50
_whatsapp: Deque[dict] = deque(maxlen=_MAX_ITEMS)
_email: Deque[dict] = deque(maxlen=_MAX_ITEMS)
_lock = Lock()


def record_whatsapp(*, chat_id: str, text: str) -> None:
    with _lock:
        _whatsapp.append(
            {"ts": time.time(), "chat_id": chat_id, "text": text}
        )


def record_email(*, to: str, subject: str, text: str) -> None:
    with _lock:
        _email.append(
            {"ts": time.time(), "to": to, "subject": subject, "text": text}
        )


router = APIRouter(tags=["demo"])


@router.get("/webhooks/whatsapp/inbox")
async def whatsapp_inbox() -> dict:
    with _lock:
        items = list(_whatsapp)
    return {"count": len(items), "items": items}


@router.get("/webhooks/email/inbox")
async def email_inbox() -> dict:
    with _lock:
        items = list(_email)
    return {"count": len(items), "items": items}
