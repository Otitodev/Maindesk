"""Tiny intent-classification eval (TRD §16).

Run: `python -m evals.run_intent_eval`
Reports accuracy, a per-class confusion table, and latency percentiles.
Writes machine-readable output to evals/results/intent_eval_results.json.
"""

from __future__ import annotations

import asyncio
import collections
import datetime
import json
import pathlib
import statistics
import sys
import time

from app.agents.state import AgentState
from app.agents.triage import triage_node
from app.config import get_settings
from app.gateway.schema import PatientMessage

CASES_PATH = pathlib.Path(__file__).parent / "intent_cases.jsonl"
RESULTS_PATH = pathlib.Path(__file__).parent / "results" / "intent_eval_results.json"


async def _classify(text: str) -> tuple[str, float]:
    """Return (predicted_intent, latency_ms) for a single case."""
    msg = PatientMessage(
        message_id="eval",
        session_id="eval:harness",
        channel="web",
        content=text,
    )
    state: AgentState = {"message": msg}
    started = time.perf_counter()
    result = await triage_node(state)
    latency_ms = (time.perf_counter() - started) * 1000
    return result.get("intent", "unknown"), latency_ms


def _percentile(values: list[float], pct: float) -> float:
    qs = statistics.quantiles(values, n=100, method="inclusive")
    return qs[max(0, min(98, round(pct) - 1))]


async def main() -> int:
    with CASES_PATH.open() as fp:
        cases = [json.loads(line) for line in fp if line.strip()]

    correct = 0
    confusion: dict[tuple[str, str], int] = collections.defaultdict(int)
    latencies: list[float] = []
    case_results: list[dict] = []
    for c in cases:
        predicted, latency_ms = await _classify(c["text"])
        expected = c["expected"]
        confusion[(expected, predicted)] += 1
        latencies.append(latency_ms)
        ok = predicted == expected
        if ok:
            correct += 1
        else:
            print(f"MISS: {expected:18} -> {predicted:18} | {c['text']}")
        case_results.append(
            {
                "text": c["text"],
                "expected": expected,
                "predicted": predicted,
                "correct": ok,
                "latency_ms": round(latency_ms, 1),
            }
        )

    total = len(cases)
    accuracy = correct / total if total else 0.0
    p50 = statistics.median(latencies)
    p95 = _percentile(latencies, 95)
    print(f"\nAccuracy: {correct}/{total} ({accuracy:.1%})")
    print(f"Latency:  p50 {p50:.0f}ms / p95 {p95:.0f}ms")

    per_intent: dict[str, dict[str, int]] = collections.defaultdict(
        lambda: {"total": 0, "correct": 0}
    )
    for r in case_results:
        per_intent[r["expected"]]["total"] += 1
        if r["correct"]:
            per_intent[r["expected"]]["correct"] += 1

    RESULTS_PATH.parent.mkdir(exist_ok=True)
    RESULTS_PATH.write_text(
        json.dumps(
            {
                "run_at": datetime.datetime.now(datetime.timezone.utc).isoformat(
                    timespec="seconds"
                ),
                "model": get_settings().qwen_model_turbo,
                "accuracy": round(accuracy, 4),
                "correct": correct,
                "total": total,
                "latency_ms": {"p50": round(p50, 1), "p95": round(p95, 1)},
                "per_intent": dict(per_intent),
                "cases": case_results,
            },
            indent=2,
        )
        + "\n"
    )
    print(f"Results written to {RESULTS_PATH.relative_to(pathlib.Path.cwd())}")
    return 0 if accuracy >= 0.85 else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
