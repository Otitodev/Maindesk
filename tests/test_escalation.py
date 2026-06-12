"""Tests for app/tools/escalation.notify_staff."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.config import get_settings
from app.gateway.schema import PatientMessage
from app.tools.escalation import notify_staff


def _msg(content: str = "I need help") -> PatientMessage:
    return PatientMessage(
        message_id="m", session_id="s", channel="web", content=content
    )


@pytest.fixture(autouse=True)
def clear_settings():
    yield
    get_settings.cache_clear()


async def test_no_webhook_url_returns_not_delivered(monkeypatch):
    monkeypatch.setenv("STAFF_ESCALATION_WEBHOOK_URL", "")
    get_settings.cache_clear()
    result = await notify_staff(_msg(), reason="test")
    assert result["tool"] == "escalate"
    assert result["delivered"] is False
    assert result["reason"] == "test"


async def test_successful_post_returns_delivered(monkeypatch):
    monkeypatch.setenv("STAFF_ESCALATION_WEBHOOK_URL", "https://hooks.example.com/123")
    get_settings.cache_clear()

    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()

    with patch("app.tools.escalation.httpx.AsyncClient") as mock_cls:
        mock_http = AsyncMock()
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_http.post = AsyncMock(return_value=mock_response)

        result = await notify_staff(_msg(), reason="urgent")

    assert result["delivered"] is True
    assert result["reason"] == "urgent"
    mock_http.post.assert_called_once()


async def test_http_error_returns_not_delivered(monkeypatch):
    monkeypatch.setenv("STAFF_ESCALATION_WEBHOOK_URL", "https://hooks.example.com/123")
    get_settings.cache_clear()

    with patch("app.tools.escalation.httpx.AsyncClient") as mock_cls:
        mock_http = AsyncMock()
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_http.post = AsyncMock(side_effect=httpx.ConnectError("connection refused"))

        result = await notify_staff(_msg(), reason="urgent")

    assert result["delivered"] is False
