"""Tests for the clinic business-hours helper + after-hours deferral policy."""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from app.agents import hours
from app.config import get_settings

# 2026-06-15 is a Monday; 2026-06-13 is a Saturday. Defaults: 09–17, Mon–Fri, UTC.
def _at(hour: int, *, day: int = 15, tz: str = "UTC") -> datetime:
    return datetime(2026, 6, day, hour, 0, tzinfo=ZoneInfo(tz))


def test_open_during_business_hours():
    assert hours.is_open(_at(10)) is True


def test_closed_before_open():
    assert hours.is_open(_at(7)) is False


def test_closed_at_and_after_close():
    assert hours.is_open(_at(17)) is False
    assert hours.is_open(_at(18)) is False


def test_closed_on_weekend():
    assert hours.is_open(_at(10, day=13)) is False  # Saturday


def test_timezone_is_respected(monkeypatch):
    monkeypatch.setenv("CLINIC_TIMEZONE", "America/New_York")
    get_settings.cache_clear()
    # 13:00 UTC == 09:00 New York → open; 12:00 UTC == 08:00 NY → closed.
    assert hours.is_open(_at(13)) is True
    assert hours.is_open(_at(12)) is False
    get_settings.cache_clear()


def test_should_defer_only_when_after_hours_mode_and_open(monkeypatch):
    monkeypatch.setenv("ANSWER_MODE", "after_hours")
    get_settings.cache_clear()
    assert hours.should_defer_to_staff(_at(10)) is True    # open + mode on → defer
    assert hours.should_defer_to_staff(_at(20)) is False   # closed → handle
    get_settings.cache_clear()


def test_no_defer_in_always_mode(monkeypatch):
    monkeypatch.setenv("ANSWER_MODE", "always")
    get_settings.cache_clear()
    assert hours.should_defer_to_staff(_at(10)) is False
    get_settings.cache_clear()
