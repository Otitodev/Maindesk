"""Calendar provider factory.

`get_provider()` returns the Google provider when a calendar id + service
account are configured, else the no-op stub. Cached like `get_settings()` so a
provider (and its credentials) is built once per process. google-auth is
imported lazily so the stub path has no hard dependency on it.
"""

from __future__ import annotations

import json
import logging
from functools import lru_cache

from app.config import get_settings
from app.tools.calendar.base import CalendarProvider
from app.tools.calendar.stub import StubCalendarProvider

log = logging.getLogger("calendar")


def _load_service_account_info(raw: str) -> dict:
    """Accept either inline JSON or a path to a JSON key file."""
    raw = raw.strip()
    if raw.startswith("{"):
        return json.loads(raw)
    with open(raw, encoding="utf-8") as fh:
        return json.load(fh)


@lru_cache
def get_provider() -> CalendarProvider:
    s = get_settings()
    if s.google_calendar_id and s.google_service_account_json:
        try:
            from google.oauth2 import service_account

            from app.tools.calendar.google import SCOPES, GoogleCalendarProvider

            info = _load_service_account_info(s.google_service_account_json)
            creds = service_account.Credentials.from_service_account_info(
                info, scopes=SCOPES
            )
            log.info("calendar: Google Calendar provider active (id=%s)", s.google_calendar_id)
            return GoogleCalendarProvider(s.google_calendar_id, creds)
        except Exception:
            log.exception("calendar: Google init failed; falling back to stub")
    return StubCalendarProvider()
