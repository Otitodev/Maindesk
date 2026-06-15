"""Google Calendar provider — real free/busy + appointment mirroring.

Uses the already-vendored httpx for the Calendar v3 REST API and google-auth
only to mint a service-account bearer token. Token refresh is synchronous in
google-auth, so it runs in a worker thread to avoid blocking the event loop.

Auth model: a service account with write access to one clinic calendar
(`GOOGLE_CALENDAR_ID`). Share that calendar with the service account's email,
or use domain-wide delegation — no per-user OAuth flow.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta

import httpx
from google.auth.transport.requests import Request as GoogleAuthRequest

log = logging.getLogger("calendar.google")

SCOPES = ["https://www.googleapis.com/auth/calendar"]
_API = "https://www.googleapis.com/calendar/v3"
_TIMEOUT = 8.0


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def _parse(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


class GoogleCalendarProvider:
    def __init__(self, calendar_id: str, credentials) -> None:
        self._calendar_id = calendar_id
        self._creds = credentials

    async def _headers(self) -> dict[str, str]:
        def _refresh() -> str:
            if not self._creds.valid:
                self._creds.refresh(GoogleAuthRequest())
            return self._creds.token

        token = await asyncio.to_thread(_refresh)
        return {"Authorization": f"Bearer {token}"}

    async def busy_intervals(
        self, start: datetime, end: datetime
    ) -> list[tuple[datetime, datetime]]:
        headers = await self._headers()
        body = {
            "timeMin": _iso(start),
            "timeMax": _iso(end),
            "items": [{"id": self._calendar_id}],
        }
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(f"{_API}/freeBusy", json=body, headers=headers)
            resp.raise_for_status()
            data = resp.json()
        busy = data.get("calendars", {}).get(self._calendar_id, {}).get("busy", [])
        return [(_parse(b["start"]), _parse(b["end"])) for b in busy]

    async def create_event(
        self, patient_id: str, starts_at: datetime, *, duration_minutes: int
    ) -> str | None:
        headers = await self._headers()
        body = {
            "summary": f"Appointment — patient {patient_id}",
            "start": {"dateTime": _iso(starts_at)},
            "end": {"dateTime": _iso(starts_at + timedelta(minutes=duration_minutes))},
        }
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(
                f"{_API}/calendars/{self._calendar_id}/events",
                json=body, headers=headers,
            )
            resp.raise_for_status()
            return resp.json().get("id")

    async def move_event(
        self, event_id: str, new_starts_at: datetime, *, duration_minutes: int
    ) -> None:
        headers = await self._headers()
        body = {
            "start": {"dateTime": _iso(new_starts_at)},
            "end": {"dateTime": _iso(new_starts_at + timedelta(minutes=duration_minutes))},
        }
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.patch(
                f"{_API}/calendars/{self._calendar_id}/events/{event_id}",
                json=body, headers=headers,
            )
            resp.raise_for_status()

    async def cancel_event(self, event_id: str) -> None:
        headers = await self._headers()
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.delete(
                f"{_API}/calendars/{self._calendar_id}/events/{event_id}",
                headers=headers,
            )
            # 410 Gone = already deleted; treat as success (idempotent cancel).
            if resp.status_code not in (200, 204, 410):
                resp.raise_for_status()
