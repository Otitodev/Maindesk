"""No-op calendar provider — the fallback when Google Calendar isn't configured.

Reports nothing busy (so availability comes from Postgres alone) and persists no
events (so mirroring is a no-op). This keeps local demos and the test suite
running without any external calendar, preserving the original Postgres-only
behaviour while the rest of the system is calendar-aware.
"""

from __future__ import annotations

from datetime import datetime


class StubCalendarProvider:
    async def busy_intervals(
        self, start: datetime, end: datetime
    ) -> list[tuple[datetime, datetime]]:
        return []

    async def create_event(
        self, patient_id: str, starts_at: datetime, *, duration_minutes: int
    ) -> str | None:
        return None

    async def move_event(
        self, event_id: str, new_starts_at: datetime, *, duration_minutes: int
    ) -> None:
        return None

    async def cancel_event(self, event_id: str) -> None:
        return None
