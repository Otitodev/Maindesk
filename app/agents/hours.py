"""Clinic business-hours helper.

Single source of truth for "is the clinic open right now", shared by the
orchestrator after-hours gate and the voice greeting. Same working-day +
hour-window logic used to generate slots in app/tools/appointments.py.
"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from app import clinic_config


def is_open(now: datetime | None = None) -> bool:
    """True if the clinic is open at `now` (defaults to the current time in the
    clinic timezone). Hour-granular: open at open_hour, closed once the hour
    reaches close_hour. Reads runtime clinic config (env defaults apply)."""
    cfg = clinic_config.current()
    tz = ZoneInfo(cfg["timezone"])
    current = now.astimezone(tz) if now is not None else datetime.now(tz)
    if current.isoweekday() not in cfg["working_days"]:
        return False
    return cfg["open_hour"] <= current.hour < cfg["close_hour"]


def should_defer_to_staff(now: datetime | None = None) -> bool:
    """True when after-hours mode is on AND the clinic is currently open — staff
    are in, so the agent should hand off rather than fully handle the turn."""
    return clinic_config.current()["answer_mode"] == "after_hours" and is_open(now)
