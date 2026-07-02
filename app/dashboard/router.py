"""Staff dashboard — human-in-the-loop checkpoint UI (PRD Track 4 brief).

A single HTMX page served at /staff:
  * live escalation queue (SSE push + slow fallback poll)
  * one-click Approve / Redirect to doctor / Close with note
  * upcoming bookings sidebar

No template engine or extra dependencies: fragments are rendered with
plain string formatting + html.escape. Access is guarded by the optional
STAFF_DASHBOARD_KEY setting (open when unset, e.g. local demos).
"""

from __future__ import annotations

import asyncio
import html
import logging
import pathlib
import urllib.parse
from datetime import datetime

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, StreamingResponse

from app.config import get_settings
from app.dashboard import events, store

log = logging.getLogger(__name__)

router = APIRouter(prefix="/staff", tags=["staff"])

_TEMPLATE_PATH = pathlib.Path(__file__).parent / "templates" / "index.html"


def _check_key(request: Request) -> str:
    """401 unless the request carries STAFF_DASHBOARD_KEY (when configured)."""
    expected = get_settings().staff_dashboard_key
    supplied = request.query_params.get("key") or request.headers.get("x-staff-key") or ""
    if expected and supplied != expected:
        raise HTTPException(status_code=401, detail="missing or invalid staff key")
    return supplied


def _fmt(ts: datetime | None) -> str:
    return ts.strftime("%b %d, %H:%M") if ts else ""


def _esc_card(e: dict, key: str) -> str:
    esc_id = html.escape(str(e["id"]))
    status = html.escape(e.get("status") or "open")
    who = html.escape(e.get("full_name") or "Unknown patient")
    channel = html.escape(e.get("channel") or "?")
    session = html.escape(e.get("session_id") or "")
    reason = html.escape(e.get("reason") or "")
    preview = html.escape(e.get("message_preview") or "")
    note = html.escape(e.get("note") or "")
    when = _fmt(e.get("created_at"))

    head = (
        f'<div class="row"><span class="badge {status}">{status}</span>'
        f'<span class="who">{who}</span><span class="chip">{channel}</span>'
        f'<span class="session">{session}</span>'
        f'<span class="when">{when}</span></div>'
        f'<div class="reason">{reason}</div>'
        f'<div class="preview">&ldquo;{preview}&rdquo;</div>'
    )
    if status != "open":
        note_line = f'<div class="note-line">note: {note}</div>' if note else ""
        return f'<div class="card">{head}{note_line}</div>'

    qkey = urllib.parse.quote(key)
    actions = "".join(
        f'<button class="{action}" hx-post="/staff/escalations/{esc_id}?key={qkey}" '
        f"hx-vals='{{\"action\": \"{action}\"}}' "
        f'hx-include="#note-{esc_id}" hx-target="#queue">{label}</button>'
        for action, label in
        [("approve", "Approve"), ("redirect", "Redirect to doctor"), ("close", "Close")]
    )
    return (
        f'<div class="card">{head}<div class="actions">'
        f'<input id="note-{esc_id}" name="note" placeholder="optional note&hellip;">'
        f"{actions}</div></div>"
    )


async def _queue_fragment(key: str) -> str:
    try:
        escalations = await store.list_escalations()
    except Exception:
        log.warning("dashboard queue query failed", exc_info=True)
        return '<div class="empty">Database not reachable — is Postgres up?</div>'
    if not escalations:
        return '<div class="empty">No escalations yet. All quiet. 🎉</div>'
    return "".join(_esc_card(e, key) for e in escalations)


@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse, include_in_schema=False)
async def index(request: Request) -> HTMLResponse:
    key = _check_key(request)
    page = _TEMPLATE_PATH.read_text(encoding="utf-8")
    return HTMLResponse(page.replace("__KEY__", urllib.parse.quote(key)))


@router.get("/queue", response_class=HTMLResponse)
async def queue(request: Request) -> HTMLResponse:
    key = _check_key(request)
    return HTMLResponse(await _queue_fragment(key))


@router.post("/escalations/{esc_id}", response_class=HTMLResponse)
async def act(esc_id: str, request: Request) -> HTMLResponse:
    key = _check_key(request)
    form = urllib.parse.parse_qs((await request.body()).decode())
    action = (form.get("action") or [""])[0]
    note = (form.get("note") or [""])[0]
    if action not in store.ACTION_TO_STATUS:
        raise HTTPException(status_code=422, detail=f"unknown action {action!r}")
    try:
        applied = await store.resolve_escalation(esc_id, action=action, note=note)
        if not applied:
            log.info("escalation %s already resolved or missing", esc_id)
    except Exception:
        log.warning("dashboard action failed", exc_info=True)
    return HTMLResponse(await _queue_fragment(key))


@router.get("/bookings", response_class=HTMLResponse)
async def bookings(request: Request) -> HTMLResponse:
    _check_key(request)
    try:
        rows = await store.recent_bookings()
    except Exception:
        log.warning("dashboard bookings query failed", exc_info=True)
        return HTMLResponse('<div class="empty">Database not reachable.</div>')
    if not rows:
        return HTMLResponse('<div class="empty">No upcoming bookings.</div>')
    items = "".join(
        f'<div class="booking"><span>{html.escape(r.get("full_name") or "Unknown")}</span>'
        f'<span class="when">{_fmt(r.get("starts_at"))} &middot; {html.escape(r.get("status") or "")}</span></div>'
        for r in rows
    )
    return HTMLResponse(items)


@router.get("/analytics", response_class=HTMLResponse)
async def analytics(request: Request) -> HTMLResponse:
    """Ops-facing analytics page — shows the ROI story to a clinic owner."""
    key = _check_key(request)
    try:
        m = await store.month_analytics()
    except Exception:
        log.warning("analytics query failed", exc_info=True)
        m = {
            "bookings_this_month": 0, "bookings_last_month": 0, "growth_pct": None,
            "escalations_this_month": 0, "escalations_open": 0,
            "avg_resolve_seconds": 0.0, "hours_replaced": 0.0,
        }
    qkey = urllib.parse.quote(key)
    avg_min = int(round(m["avg_resolve_seconds"] / 60)) if m["avg_resolve_seconds"] else 0
    growth_bit = (
        f'<span class="delta {"up" if m["growth_pct"] >= 0 else "down"}">'
        f'{m["growth_pct"]:+d}%</span>'
        if m["growth_pct"] is not None
        else '<span class="delta">—</span>'
    )
    page = f"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>MainDesk — Analytics</title>
<style>
:root {{
  --bg: #0f1419; --panel: #1a2129; --border: #2c3640;
  --text: #e6edf3; --muted: #8b98a5; --accent: #4fc3f7;
  --up: #34d399; --down: #f87171;
}}
* {{ box-sizing: border-box; }}
body {{ margin: 0; background: var(--bg); color: var(--text);
       font: 15px/1.5 system-ui, -apple-system, "Segoe UI", sans-serif; }}
header {{ display: flex; align-items: baseline; gap: 12px;
         padding: 18px 28px; border-bottom: 1px solid var(--border); }}
header h1 {{ font-size: 18px; margin: 0; }}
header .sub {{ color: var(--muted); font-size: 13px; }}
header nav {{ margin-left: auto; display: flex; gap: 20px; font-size: 13px; }}
header nav a {{ color: var(--muted); text-decoration: none; }}
header nav a.active {{ color: var(--text); border-bottom: 2px solid var(--accent); padding-bottom: 4px; }}
main {{ padding: 32px 28px; max-width: 1100px; }}
.eyebrow {{ font-size: 12px; text-transform: uppercase; letter-spacing: .1em;
            color: var(--muted); margin: 0 0 24px; }}
.grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
         gap: 16px; margin-bottom: 32px; }}
.tile {{ background: var(--panel); border: 1px solid var(--border);
         border-radius: 12px; padding: 22px 20px; }}
.tile .label {{ font-size: 12px; text-transform: uppercase; letter-spacing: .08em;
                color: var(--muted); margin: 0 0 8px; }}
.tile .value {{ font-size: 34px; font-weight: 700; margin: 0; line-height: 1.1; }}
.tile .footnote {{ font-size: 12px; color: var(--muted); margin: 8px 0 0; }}
.delta {{ font-size: 14px; font-weight: 600; margin-left: 10px; vertical-align: middle; }}
.delta.up   {{ color: var(--up); }}
.delta.down {{ color: var(--down); }}
.callout {{ background: var(--panel); border: 1px solid var(--border);
            border-radius: 12px; padding: 24px 28px; }}
.callout h2 {{ font-size: 15px; margin: 0 0 8px; color: var(--accent); }}
.callout p {{ margin: 0; color: var(--muted); font-size: 14px; }}
</style></head>
<body><header>
  <h1>MainDesk</h1><span class="sub">operator analytics</span>
  <nav>
    <a href="/staff?key={qkey}">Queue</a>
    <a href="/staff/analytics?key={qkey}" class="active">Analytics</a>
  </nav>
</header>
<main>
  <p class="eyebrow">This month · so far</p>
  <div class="grid">
    <div class="tile">
      <p class="label">Bookings handled</p>
      <p class="value">{m["bookings_this_month"]} {growth_bit}</p>
      <p class="footnote">vs {m["bookings_last_month"]} last month</p>
    </div>
    <div class="tile">
      <p class="label">Escalations to a human</p>
      <p class="value">{m["escalations_this_month"]}</p>
      <p class="footnote">{m["escalations_open"]} currently open</p>
    </div>
    <div class="tile">
      <p class="label">Avg. time to human</p>
      <p class="value">{avg_min}<span style="font-size:16px;color:var(--muted);"> min</span></p>
      <p class="footnote">from escalation to clinician reply</p>
    </div>
    <div class="tile">
      <p class="label">Reception time replaced</p>
      <p class="value">{m["hours_replaced"]}<span style="font-size:16px;color:var(--muted);"> hrs</span></p>
      <p class="footnote">est. at 4 min per autonomous booking</p>
    </div>
  </div>

  <div class="callout">
    <h2>What this tells you</h2>
    <p>Every escalation in that middle tile is a moment MainDesk chose humility — a case where confidence dipped or a red-flag intent surfaced. Every booking in the left tile is a call your team didn't have to take. The right tile compounds: for a $299/mo plan, an autonomous booking costs roughly $0.30 — a receptionist call costs $3–7.</p>
  </div>
</main></body></html>"""
    return HTMLResponse(page)


@router.get("/events")
async def sse(request: Request) -> StreamingResponse:
    _check_key(request)

    async def stream():
        q = events.subscribe()
        try:
            yield ": connected\n\n"
            while True:
                try:
                    esc_id = await asyncio.wait_for(q.get(), timeout=15.0)
                    yield f"event: escalation\ndata: {esc_id}\n\n"
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
        finally:
            events.unsubscribe(q)

    return StreamingResponse(stream(), media_type="text/event-stream")
