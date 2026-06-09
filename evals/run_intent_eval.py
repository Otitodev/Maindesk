"""Tiny intent-classification eval (TRD §16).

Run: `python -m evals.run_intent_eval`
Reports accuracy and a per-class confusion table.
"""

from __future__ import annotations

import asyncio
import collections
import json
import pathlib
import sys

from app.agents.state import AgentState
from app.agents.triage import triage_node
from app.gateway.schema import PatientMessage

CASES_PATH = pathlib.Path(__file__).parent / "intent_cases.jsonl"


async def _classify(text: str) -> str:
    msg = PatientMessage(
        message_id="eval",
        session_id="eval:harness",
        channel="web",
        content=text,
    )
    state: AgentState = {"message": msg}
    result = await triage_node(state)
    return result.get("intent", "unknown")


async def main() -> int:
    with CASES_PATH.open() as fp:
        cases = [json.loads(line) for line in fp if line.strip()]

    correct = 0
    confusion: dict[tuple[str, str], int] = collections.defaultdict(int)
    for c in cases:
        predicted = await _classify(c["text"])
        expected = c["expected"]
        confusion[(expected, predicted)] += 1
        if predicted == expected:
            correct += 1
        else:
            print(f"MISS: {expected:18} -> {predicted:18} | {c['text']}")

    total = len(cases)
    accuracy = correct / total if total else 0.0
    print(f"\nAccuracy: {correct}/{total} ({accuracy:.1%})")
    return 0 if accuracy >= 0.85 else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
