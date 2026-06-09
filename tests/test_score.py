from datetime import datetime, timedelta, timezone

from app.memory.score import HALF_LIFE_DAYS, compute_memory_score


def test_higher_similarity_wins():
    base = dict(importance=0.5, access_count=5, last_accessed=datetime.now(timezone.utc))
    low = compute_memory_score(similarity=0.2, **base)
    high = compute_memory_score(similarity=0.9, **base)
    assert high > low


def test_recency_decays():
    fresh = datetime.now(timezone.utc)
    old = fresh - timedelta(days=HALF_LIFE_DAYS * 4)  # 4 half-lives → ~6% remaining
    common = dict(similarity=0.5, importance=0.5, access_count=0)
    assert compute_memory_score(last_accessed=fresh, **common) > compute_memory_score(
        last_accessed=old, **common
    )


def test_none_last_accessed_is_safe():
    score = compute_memory_score(
        similarity=0.7, importance=0.5, access_count=0, last_accessed=None
    )
    assert isinstance(score, float)


def test_access_count_saturates():
    common = dict(
        similarity=0.5,
        importance=0.5,
        last_accessed=datetime.now(timezone.utc),
    )
    a = compute_memory_score(access_count=20, **common)
    b = compute_memory_score(access_count=200, **common)
    # Both should be capped at the same level — log curve + clamp.
    assert abs(a - b) < 0.05


def test_importance_contributes_linearly():
    common = dict(
        similarity=0.5, access_count=0, last_accessed=datetime.now(timezone.utc)
    )
    low = compute_memory_score(importance=0.0, **common)
    high = compute_memory_score(importance=1.0, **common)
    assert high > low


def test_naive_datetime_treated_as_utc():
    aware = datetime.now(timezone.utc)
    naive = aware.replace(tzinfo=None)
    common = dict(similarity=0.5, importance=0.5, access_count=0)
    s_naive = compute_memory_score(last_accessed=naive, **common)
    s_aware = compute_memory_score(last_accessed=aware, **common)
    assert abs(s_naive - s_aware) < 1e-3
