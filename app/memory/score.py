"""Decay-aware memory scoring (TRD §9.3).

Final score = w_sim * cosine + w_rec * recency + w_imp * importance
              + w_acc * log1p(access_count)

Weights are intentionally biased toward similarity — decay should
re-shuffle ties, not override semantic relevance.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone

W_SIM = 0.55
W_REC = 0.20
W_IMP = 0.15
W_ACC = 0.10

# Recency half-life in days.
HALF_LIFE_DAYS = 30.0


def _recency(last_accessed: datetime | None) -> float:
    if last_accessed is None:
        return 0.0
    if last_accessed.tzinfo is None:
        last_accessed = last_accessed.replace(tzinfo=timezone.utc)
    age_days = (datetime.now(timezone.utc) - last_accessed).total_seconds() / 86400.0
    return math.exp(-math.log(2) * age_days / HALF_LIFE_DAYS)


def compute_memory_score(
    similarity: float,
    importance: float,
    access_count: int,
    last_accessed: datetime | None,
) -> float:
    rec = _recency(last_accessed)
    acc = math.log1p(max(0, access_count)) / math.log1p(20)  # caps around 20 hits
    acc = min(acc, 1.0)
    return (
        W_SIM * similarity
        + W_REC * rec
        + W_IMP * importance
        + W_ACC * acc
    )
