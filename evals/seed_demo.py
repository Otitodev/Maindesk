"""Seed 3 demo patients with memories + embeddings.

Run once: `python -m evals.seed_demo`
Idempotent: re-running upserts patients and skips memories that already
exist for that patient (matched on content prefix).
"""

from __future__ import annotations

import asyncio
import logging
from typing import TypedDict

from app.agents.qwen_client import embed
from app.memory.db import get_pool
from app.memory.profile import upsert_profile

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("seed")


class Mem(TypedDict):
    content: str
    memory_type: str
    importance: float


class Patient(TypedDict):
    phone: str
    full_name: str
    memories: list[Mem]


DEMO_PATIENTS: list[Patient] = [
    {
        # Mapped to the demo phone so WhatsApp-driven recall works.
        # Placeholder number — must match HEALTHDESK_DEMO_PATIENT_PHONE in .env.
        "phone": "2340000000000",
        "full_name": "Adaeze Okafor",
        "memories": [
            {"content": "Patient prefers afternoon appointments after 3pm.",
             "memory_type": "preference", "importance": 0.7},
            {"content": "Patient is allergic to penicillin.",
             "memory_type": "medical", "importance": 0.95},
            {"content": "Last visit was for a sprained ankle on 2026-04-12.",
             "memory_type": "history", "importance": 0.5},
        ],
    },
    {
        "phone": "2348023456789",
        "full_name": "Tunde Adebayo",
        "memories": [
            {"content": "Patient has type 2 diabetes diagnosed in 2024.",
             "memory_type": "medical", "importance": 0.9},
            {"content": "Spouse Ngozi sometimes books on patient's behalf.",
             "memory_type": "context", "importance": 0.6},
            {"content": "Patient is on Cigna PPO insurance.",
             "memory_type": "billing", "importance": 0.6},
        ],
    },
    {
        "phone": "2348034567890",
        "full_name": "Chiamaka Eze",
        "memories": [
            {"content": "Patient is hearing-impaired; please reply over WhatsApp not by call.",
             "memory_type": "accessibility", "importance": 0.9},
            {"content": "Patient prefers female physicians.",
             "memory_type": "preference", "importance": 0.7},
        ],
    },
]


async def _seed_patient(p: Patient) -> None:
    patient_id = await upsert_profile(phone=p["phone"], full_name=p["full_name"])
    log.info("patient %s (%s) -> %s", p["full_name"], p["phone"], patient_id)

    pool = await get_pool()
    async with pool.acquire() as conn:
        for mem in p["memories"]:
            # Skip if a memory with this content already exists for this patient.
            exists = await conn.fetchval(
                "SELECT 1 FROM patient_memories WHERE patient_id = $1 AND content = $2",
                patient_id, mem["content"],
            )
            if exists:
                log.info("  skip (exists): %s", mem["content"][:60])
                continue

            vec = await embed(mem["content"])
            await conn.execute(
                """
                INSERT INTO patient_memories
                  (patient_id, content, memory_type, importance_score, embedding)
                VALUES ($1, $2, $3, $4, $5::vector)
                """,
                patient_id, mem["content"], mem["memory_type"], mem["importance"],
                str(vec),
            )
            log.info("  insert: %s", mem["content"][:60])


async def main() -> None:
    for p in DEMO_PATIENTS:
        await _seed_patient(p)
    log.info("done.")


if __name__ == "__main__":
    asyncio.run(main())
