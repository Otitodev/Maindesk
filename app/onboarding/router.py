"""Self-serve onboarding wizard — /onboarding.

A single key-guarded form (same auth pattern as /staff) that reads and writes
the runtime clinic config in app.clinic_config: hours, working days, timezone,
answer mode, agent persona, and FAQ knowledge. Saving takes effect immediately
in this process (the store refreshes its cache); other workers pick it up on
their next refresh.

No template engine: the page is plain HTML with html.escape, matching the
dashboard's zero-dependency approach.
"""

from __future__ import annotations

import html
import logging
import pathlib
import urllib.parse
from zoneinfo import ZoneInfo, available_timezones

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse

from app import clinic_config
from app.config import get_settings

log = logging.getLogger(__name__)

router = APIRouter(prefix="/onboarding", tags=["onboarding"])

_TEMPLATE_PATH = pathlib.Path(__file__).parent / "templates" / "index.html"
_DAY_LABELS = [(1, "Mon"), (2, "Tue"), (3, "Wed"), (4, "Thu"), (5, "Fri"), (6, "Sat"), (7, "Sun")]


def _check_key(request: Request) -> str:
    """401 unless the request carries STAFF_DASHBOARD_KEY (when configured)."""
    expected = get_settings().staff_dashboard_key
    supplied = request.query_params.get("key") or request.headers.get("x-staff-key") or ""
    if expected and supplied != expected:
        raise HTTPException(status_code=401, detail="missing or invalid staff key")
    return supplied


def _parse_form(form: dict[str, list[str]]) -> dict:
    """Validate and coerce posted form values into a clinic-config patch."""
    def one(key: str, default: str = "") -> str:
        return (form.get(key) or [default])[0].strip()

    try:
        open_hour = int(one("open_hour", "9"))
        close_hour = int(one("close_hour", "17"))
    except ValueError:
        raise HTTPException(status_code=422, detail="hours must be integers")
    if not (0 <= open_hour < close_hour <= 24):
        raise HTTPException(status_code=422, detail="require 0 <= open_hour < close_hour <= 24")

    working_days = sorted({int(d) for d in form.get("working_days", []) if d.isdigit() and 1 <= int(d) <= 7})
    if not working_days:
        raise HTTPException(status_code=422, detail="select at least one working day")

    tz = one("timezone", "UTC")
    try:
        ZoneInfo(tz)
    except Exception:
        raise HTTPException(status_code=422, detail=f"unknown timezone {tz!r}")

    answer_mode = one("answer_mode", "always")
    if answer_mode not in ("always", "after_hours"):
        raise HTTPException(status_code=422, detail="invalid answer_mode")

    return {
        "clinic_name": one("clinic_name"),
        "agent_name": one("agent_name", "MainDesk") or "MainDesk",
        "greeting": one("greeting"),
        "timezone": tz,
        "open_hour": open_hour,
        "close_hour": close_hour,
        "working_days": working_days,
        "answer_mode": answer_mode,
        "faqs": one("faqs"),
    }


def _render(cfg: dict, key: str, *, saved: bool = False) -> str:
    page = _TEMPLATE_PATH.read_text(encoding="utf-8")
    days = "".join(
        '<label class="md-chip"><input type="checkbox" name="working_days" value="{v}"{chk}> {label}</label>'.format(
            v=v, label=label, chk=" checked" if v in cfg["working_days"] else ""
        )
        for v, label in _DAY_LABELS
    )
    tz_options = "".join(
        '<option{sel}>{tz}</option>'.format(
            tz=html.escape(tz), sel=" selected" if tz == cfg["timezone"] else ""
        )
        for tz in sorted(available_timezones())
    )

    def mode_sel(value: str) -> str:
        return " selected" if cfg["answer_mode"] == value else ""

    return (
        page.replace("__KEY__", urllib.parse.quote(key))
        .replace("__CLINIC_NAME__", html.escape(cfg["clinic_name"]))
        .replace("__AGENT_NAME__", html.escape(cfg["agent_name"]))
        .replace("__GREETING__", html.escape(cfg.get("greeting", "")))
        .replace("__OPEN_HOUR__", str(cfg["open_hour"]))
        .replace("__CLOSE_HOUR__", str(cfg["close_hour"]))
        .replace("__DAYS__", days)
        .replace("__TZ_OPTIONS__", tz_options)
        .replace("__MODE_ALWAYS__", mode_sel("always"))
        .replace("__MODE_AFTER__", mode_sel("after_hours"))
        .replace("__FAQS__", html.escape(cfg["faqs"]))
        .replace("__SAVED__", "Saved ✓" if saved else "")
    )


@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse, include_in_schema=False)
async def index(request: Request) -> HTMLResponse:
    key = _check_key(request)
    await clinic_config.refresh()
    return HTMLResponse(_render(clinic_config.current(), key))


@router.post("", response_class=HTMLResponse)
async def save(request: Request) -> HTMLResponse:
    key = _check_key(request)
    form = urllib.parse.parse_qs((await request.body()).decode())
    patch = _parse_form(form)
    try:
        cfg = await clinic_config.save(patch)
    except Exception:
        log.warning("clinic config save failed", exc_info=True)
        raise HTTPException(status_code=503, detail="could not save (database unreachable?)")
    return HTMLResponse(_render(cfg, key, saved=True))
