"""In-process pub/sub so the staff dashboard updates without polling.

Escalations created in this process (web + WhatsApp gateway) push an SSE
event immediately. The voice worker runs in a separate process, so its
escalations land via the dashboard's slow fallback poll instead.
"""

from __future__ import annotations

import asyncio

_subscribers: set[asyncio.Queue[str]] = set()


def publish(event: str) -> None:
    for q in tuple(_subscribers):
        try:
            q.put_nowait(event)
        except asyncio.QueueFull:
            pass  # slow consumer; the fallback poll will catch it up


def subscribe() -> asyncio.Queue[str]:
    q: asyncio.Queue[str] = asyncio.Queue(maxsize=32)
    _subscribers.add(q)
    return q


def unsubscribe(q: asyncio.Queue[str]) -> None:
    _subscribers.discard(q)
