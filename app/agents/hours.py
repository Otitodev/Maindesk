"""Clinic business-hours helper.

Single source of truth for "is the clinic open right now", shared by the
orchestrator after-hours gate and the voice greeting. Same working-day +
hour-window logic used to generate slots in app/tools/appointments.py.
"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from app.config import get_settings


def is_open(now: datetime | None = None) -> bool:
    """True if the clinic is open at `now` (defaults to the current time in the
    clinic timezone). Hour-granular: open at clinic_open_hour, closed once the
    hour reaches clinic_close_hour."""
    s = get_settings()
    tz = ZoneInfo(s.clinic_timezone)
    current = now.astimezone(tz) if now is not None else datetime.now(tz)
    if current.isoweekday() not in s.clinic_working_days:
        return False
    return s.clinic_open_hour <= current.hour < s.clinic_close_hour


def should_defer_to_staff(now: datetime | None = None) -> bool:
    """True when after-hours mode is on AND the clinic is currently open — staff
    are in, so the agent should hand off rather than fully handle the turn."""
    return get_settings().answer_mode == "after_hours" and is_open(now)
