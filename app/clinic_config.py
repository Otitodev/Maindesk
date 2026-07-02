"""Runtime clinic configuration.

Single-tenant: one clinic per deployment, stored as a singleton JSONB row in
`clinic_settings` and edited via the /onboarding wizard. Values fall back to the
`.env` defaults in app.config, so an unconfigured deployment behaves exactly as
before.

The accessor is split into a synchronous `current()` (reads an in-process
cache, so hot paths like the after-hours gate and prompt building stay sync) and
an async `refresh()` that reloads the cache from Postgres. `refresh()` is called
at app/voice-worker startup and after every save. Cross-process staleness (the
voice worker won't see a save made in the API process until its next refresh) is
acceptable for this single-tenant model.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from app.config import get_settings
from app.memory.db import get_pool

log = logging.getLogger(__name__)

# Fields the onboarding wizard manages (everything else stays env-driven).
EDITABLE_FIELDS = (
    "clinic_name",
    "agent_name",
    "timezone",
    "open_hour",
    "close_hour",
    "working_days",
    "answer_mode",
    "faqs",
)

_cache: dict[str, Any] | None = None


def _defaults() -> dict[str, Any]:
    s = get_settings()
    return {
        "clinic_name": "",
        "agent_name": "HealthDesk",
        "timezone": s.clinic_timezone,
        "open_hour": s.clinic_open_hour,
        "close_hour": s.clinic_close_hour,
        "slot_minutes": s.clinic_slot_minutes,
        "working_days": list(s.clinic_working_days),
        "search_days": s.slot_search_days,
        "answer_mode": s.answer_mode,
        "faqs": "",
    }


def current() -> dict[str, Any]:
    """Synchronous accessor. Returns the cached config, or env defaults if the
    cache hasn't been loaded yet (e.g. in unit tests with no database)."""
    return _cache if _cache is not None else _defaults()


async def refresh() -> dict[str, Any]:
    """Reload the cache from Postgres, overlaying stored values on env defaults.
    Best-effort: on any DB error we keep the env defaults."""
    global _cache
    cfg = _defaults()
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow("SELECT config FROM clinic_settings WHERE id = 1")
        if row and row["config"]:
            stored = row["config"]
            if isinstance(stored, str):
                stored = json.loads(stored)
            cfg.update({k: v for k, v in stored.items() if v not in (None, "")})
    except Exception:
        log.warning("clinic config read failed; using env defaults", exc_info=True)
    _cache = cfg
    return cfg


async def save(data: dict[str, Any]) -> dict[str, Any]:
    """Persist the editable subset (merged over current values) and refresh."""
    merged = {**current(), **{k: data[k] for k in EDITABLE_FIELDS if k in data}}
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO clinic_settings (id, config, updated_at) "
            "VALUES (1, $1, NOW()) "
            "ON CONFLICT (id) DO UPDATE SET config = $1, updated_at = NOW()",
            json.dumps(merged),
        )
    return await refresh()


def clear_cache() -> None:
    """Drop the in-process cache (used by tests and after external writes)."""
    global _cache
    _cache = None


def knowledge_block(cfg: dict[str, Any] | None = None) -> str:
    """Clinic identity + FAQ knowledge to inject into agent system prompts.
    Empty when nothing clinic-specific is configured, so default deployments
    keep their original prompt verbatim."""
    cfg = cfg or current()
    name = (cfg.get("clinic_name") or "").strip()
    faqs = (cfg.get("faqs") or "").strip()
    if not name and not faqs:
        return ""
    agent = (cfg.get("agent_name") or "HealthDesk").strip()
    lines = [
        f"You are {agent}, the front-desk assistant" + (f" for {name}" if name else "") + "."
    ]
    if faqs:
        lines.append(
            "Clinic knowledge — answer from these facts when relevant; if a "
            "question isn't covered, say you'll check or connect them to staff:\n"
            + faqs
        )
    return "\n\n".join(lines)
