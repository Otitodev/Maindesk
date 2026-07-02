"""Tests for the after-hours handoff node."""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.agents import handoff as handoff_mod
from app.gateway.schema import PatientMessage


def _msg() -> PatientMessage:
    return PatientMessage(message_id="m", session_id="web:s", channel="web", content="hi")


async def test_handoff_escalates_and_replies(monkeypatch):
    notify = AsyncMock(return_value={"tool": "escalate", "delivered": True})
    monkeypatch.setattr(handoff_mod.escalation, "notify_staff", notify)
    out = await handoff_mod.handoff_node({"message": _msg(), "language": "en"})
    assert out["escalated"] is True
    assert out["reply"].content == handoff_mod._HANDOFF_TEXT["en"]
    notify.assert_awaited_once()
    assert notify.await_args.kwargs["reason"] == "after_hours_staffed"


async def test_handoff_uses_detected_language(monkeypatch):
    monkeypatch.setattr(handoff_mod.escalation, "notify_staff", AsyncMock(return_value={}))
    out = await handoff_mod.handoff_node({"message": _msg(), "language": "es"})
    assert out["reply"].content == handoff_mod._HANDOFF_TEXT["es"]


async def test_handoff_falls_back_to_english(monkeypatch):
    monkeypatch.setattr(handoff_mod.escalation, "notify_staff", AsyncMock(return_value={}))
    out = await handoff_mod.handoff_node({"message": _msg(), "language": "xx"})
    assert out["reply"].content == handoff_mod._HANDOFF_TEXT["en"]
