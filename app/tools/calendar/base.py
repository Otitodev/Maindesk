"""Calendar provider interface.

The appointment tool layer talks to whatever calendar backend is configured
through this narrow protocol, so Postgres stays the booking ledger while a real
calendar (Google, …) supplies availability and a staff-visible mirror. A
provider does two jobs:

  - availability: `busy_intervals` reports times the clinic is already blocked
    (staff calendar events, breaks) so generated slots reflect reality.
  - mirroring: `create_event` / `move_event` / `cancel_event` keep the calendar
    in sync with bookings. These are best-effort — Postgres remains the source
    of truth, so a mirror failure must never fail a booking.
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol, runtime_checkable


@runtime_checkable
class CalendarProvider(Protocol):
    async def busy_intervals(
        self, start: datetime, end: datetime
    ) -> list[tuple[datetime, datetime]]:
        """Return (start, end) busy intervals overlapping [start, end)."""
        ...

    async def create_event(
        self, patient_id: str, starts_at: datetime, *, duration_minutes: int
    ) -> str | None:
        """Create an event; return the provider event id, or None if the
        provider does not persist events (e.g. the stub)."""
        ...

    async def move_event(
        self, event_id: str, new_starts_at: datetime, *, duration_minutes: int
    ) -> None:
        """Move an existing event to a new start time."""
        ...

    async def cancel_event(self, event_id: str) -> None:
        """Delete/cancel an existing event."""
        ...
