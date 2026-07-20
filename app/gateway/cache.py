"""Time-aware LRU session cache for non-voice channels (TRD §6.2).

Voice sessions are managed per-call by the Pipecat pipeline (app.voice.bot)
and do not use this cache.
"""

from time import monotonic
from typing import Any

from cachetools import TLRUCache

AGENT_CACHE_MAX_SIZE = 128
AGENT_CACHE_IDLE_TTL = 3600  # seconds


def _expiry(_key: str, _value: Any, now: float) -> float:
    return now + AGENT_CACHE_IDLE_TTL


# TLRUCache: evicts on (a) idle TTL expiry and (b) LRU when full. TTLCache
# would only evict on TTL, not LRU, which doesn't match the spec.
agent_cache: TLRUCache = TLRUCache(
    maxsize=AGENT_CACHE_MAX_SIZE,
    ttu=_expiry,
    timer=monotonic,
)


def get_cached_session(session_id: str) -> Any | None:
    return agent_cache.get(session_id)


def set_cached_session(session_id: str, value: Any) -> None:
    agent_cache[session_id] = value
