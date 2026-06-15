"""Tests for the slot-fill resolver — JSON parsing, fail-safe, and the
guard that a slot never offered can't be acted on."""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.agents import slotfill

_SLOT = "2026-07-01T09:00:00+00:00"


async def test_select_returns_offered_slot(monkeypatch):
    monkeypatch.setattr(
        slotfill, "complete",
        AsyncMock(return_value=f'{{"decision": "select", "slot": "{_SLOT}"}}'),
    )
    out = await slotfill.resolve_selection({"type": "book", "slots": [_SLOT]}, "9am")
    assert out == {"decision": "select", "slot": _SLOT}


async def test_confirm_for_cancel(monkeypatch):
    monkeypatch.setattr(
        slotfill, "complete",
        AsyncMock(return_value='{"decision": "confirm", "slot": null}'),
    )
    out = await slotfill.resolve_selection({"type": "cancel", "slots": []}, "yes")
    assert out["decision"] == "confirm"


async def test_hallucinated_slot_is_rejected(monkeypatch):
    """If the model returns a slot that was never offered, drop it and
    downgrade the decision so we can't book a made-up time."""
    monkeypatch.setattr(
        slotfill, "complete",
        AsyncMock(return_value='{"decision": "select", "slot": "2099-01-01T00:00:00+00:00"}'),
    )
    out = await slotfill.resolve_selection({"type": "book", "slots": [_SLOT]}, "whenever")
    assert out == {"decision": "none", "slot": None}


async def test_bad_json_fails_safe_to_none(monkeypatch):
    monkeypatch.setattr(slotfill, "complete", AsyncMock(return_value="not json"))
    out = await slotfill.resolve_selection({"type": "book", "slots": [_SLOT]}, "9am")
    assert out == {"decision": "none", "slot": None}
