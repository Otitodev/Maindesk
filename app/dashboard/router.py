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

_TEMPLATE_DIR = pathlib.Path(__file__).parent / "templates"
_TEMPLATE_PATH = _TEMPLATE_DIR / "index.html"      # /staff overview
_INBOX_TEMPLATE = _TEMPLATE_DIR / "inbox.html"     # /staff/inbox full queue


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
        f'<div class="row"><span class="md-status md-status--{status}">{status}</span>'
        f'<span class="who">{who}</span><span class="chip">{channel}</span>'
        f'<span class="session">{session}</span>'
        f'<span class="when">{when}</span></div>'
        f'<div class="reason">{reason}</div>'
        f'<div class="preview">&ldquo;{preview}&rdquo;</div>'
    )
    if status != "open":
        note_line = f'<div class="note-line">note: {note}</div>' if note else ""
        return f'<div class="md-esc-card">{head}{note_line}</div>'

    qkey = urllib.parse.quote(key)
    actions = "".join(
        f'<button class="{action}" hx-post="/staff/escalations/{esc_id}?key={qkey}" '
        f"hx-vals='{{\"action\": \"{action}\"}}' "
        f'hx-include="#note-{esc_id}" hx-target="#queue">{label}</button>'
        for action, label in
        [("approve", "Approve"), ("redirect", "Redirect to doctor"), ("close", "Close")]
    )
    return (
        f'<div class="md-esc-card">{head}<div class="actions">'
        f'<input id="note-{esc_id}" name="note" placeholder="optional note&hellip;">'
        f"{actions}</div></div>"
    )


async def _queue_fragment(key: str, *, limit: int | None = None) -> str:
    try:
        escalations = await store.list_escalations()
    except Exception:
        log.warning("dashboard queue query failed", exc_info=True)
        return '<div class="md-empty">Database not reachable — is Postgres up?</div>'
    if not escalations:
        return '<div class="md-empty">No conversations paused right now. MainDesk has it.</div>'
    if limit is not None:
        escalations = escalations[:limit]
    return "".join(_esc_card(e, key) for e in escalations)


def _queue_badge(open_count: int) -> str:
    """Sidebar pill next to "Conversations" — hidden when zero."""
    if not open_count:
        return ""
    return f'<span class="md-shell__link-count">{open_count}</span>'


@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse, include_in_schema=False)
async def index(request: Request) -> HTMLResponse:
    """Operator overview — the new /staff landing."""
    key = _check_key(request)
    try:
        m = await store.month_analytics()
    except Exception:
        log.warning("overview analytics query failed", exc_info=True)
        m = {"bookings_this_month": 0, "bookings_last_month": 0, "growth_pct": None,
             "escalations_open": 0, "hours_replaced": 0.0}

    open_count = int(m["escalations_open"])
    if m["growth_pct"] is None:
        trend = "First month of tracking."
    elif m["growth_pct"] >= 0:
        trend = f"Up {m['growth_pct']}% vs last month."
    else:
        trend = f"Down {abs(m['growth_pct'])}% vs last month."

    qkey = urllib.parse.quote(key)
    if open_count == 0:
        esc_foot = "Nothing paused. MainDesk is answering everything."
    elif open_count == 1:
        esc_foot = f'<a href="/staff/inbox?key={qkey}">1 conversation</a> needs your call.'
    else:
        esc_foot = f'<a href="/staff/inbox?key={qkey}">{open_count} conversations</a> need your call.'

    page = _TEMPLATE_PATH.read_text(encoding="utf-8")
    page = (
        page.replace("__KEY__", qkey)
        .replace("__BOOKINGS_THIS_MONTH__", str(m["bookings_this_month"]))
        .replace("__BOOKINGS_TREND__", html.escape(trend))
        .replace("__ESCALATIONS_OPEN__", str(open_count))
        .replace("__ESCALATION_FOOT__", esc_foot)
        .replace("__HOURS_REPLACED__", f'{m["hours_replaced"]:g}')
        .replace("__QUEUE_BADGE__", _queue_badge(open_count))
    )
    return HTMLResponse(page)


@router.get("/inbox", response_class=HTMLResponse)
async def inbox(request: Request) -> HTMLResponse:
    """Full conversation inbox — was the original /staff view."""
    key = _check_key(request)
    try:
        open_count = int((await store.month_analytics())["escalations_open"])
    except Exception:
        open_count = 0
    page = _INBOX_TEMPLATE.read_text(encoding="utf-8")
    page = (
        page.replace("__KEY__", urllib.parse.quote(key))
        .replace("__QUEUE_BADGE__", _queue_badge(open_count))
    )
    return HTMLResponse(page)


@router.get("/queue", response_class=HTMLResponse)
async def queue(request: Request) -> HTMLResponse:
    key = _check_key(request)
    raw_limit = request.query_params.get("limit")
    limit: int | None = None
    if raw_limit and raw_limit.isdigit():
        limit = max(1, min(int(raw_limit), 50))
    return HTMLResponse(await _queue_fragment(key, limit=limit))


@router.post("/escalations/{esc_id}", response_class=HTMLResponse)
async def act(esc_id: str, request: Request) -> HTMLResponse:
    key = _check_key(request)
    form = urllib.parse.parse_qs((await request.body()).decode())
    action = (form.get("action") or [""])[0]
    note = (form.get("note") or [""])[0]
    if action not in store.ACTION_TO_STATUS:
        raise HTTPException(status_code=422, detail=f"unknown action {action!r}")
    try:
        resolved = await store.resolve_escalation(esc_id, action=action, note=note)
        if not resolved:
            log.info("escalation %s already resolved or missing", esc_id)
        else:
            # Fire the staff's note back to the patient on their original
            # channel. Best-effort — the queue row is already resolved and
            # the staff UI must not stall on an outbound provider hiccup.
            from app.tools.escalation import deliver_staff_note
            try:
                outcome = await deliver_staff_note(resolved)
                log.info("resume outbound esc=%s outcome=%s", esc_id, outcome)
            except Exception:
                log.warning("resume outbound failed esc=%s", esc_id, exc_info=True)
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
        return HTMLResponse('<div class="md-empty">Database not reachable.</div>')
    if not rows:
        return HTMLResponse('<div class="md-empty">No upcoming bookings.</div>')
    items = "".join(
        f'<div class="md-booking"><span>{html.escape(r.get("full_name") or "Unknown")}</span>'
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
    open_count = int(m["escalations_open"])
    queue_badge = _queue_badge(open_count)
    page = f"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>MainDesk — Analytics</title>
<link rel="stylesheet" href="/vendor/fonts.css" />
<link rel="stylesheet" href="/maindesk-ds.css" />
<style>
  .an-grid {{
    display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
    gap: 16px; margin-bottom: 32px;
  }}
  .an-tile {{
    background: var(--white);
    border: 1px solid var(--border-soft);
    border-radius: var(--radius-lg);
    padding: 22px 20px;
    box-shadow: var(--shadow-sm);
  }}
  .an-tile .label {{
    font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.08em;
    color: var(--ink-soft); margin: 0 0 8px; font-weight: 600;
  }}
  .an-tile .value {{
    font-family: var(--font-display);
    font-size: 34px; font-weight: 700; margin: 0; line-height: 1.1;
    color: var(--ink);
  }}
  .an-tile .footnote {{ font-size: 0.8rem; color: var(--ink-soft); margin: 8px 0 0; }}
  .delta {{ font-size: 14px; font-weight: 600; margin-left: 10px; vertical-align: middle; }}
  .delta.up   {{ color: var(--green-live); }}
  .delta.down {{ color: #dc2626; }}
  .an-callout {{
    background: var(--white);
    border: 1px solid var(--border-soft);
    border-radius: var(--radius-lg);
    padding: 24px 28px;
    box-shadow: var(--shadow-sm);
  }}
  .an-callout h2 {{
    font-family: var(--font-display);
    font-size: 1rem; margin: 0 0 8px; color: var(--teal-text);
  }}
  .an-callout p {{ margin: 0; color: var(--ink-soft); font-size: 0.95rem; }}
  .an-value-unit {{ font-size: 16px; color: var(--ink-soft); font-weight: 500; }}
</style></head>
<body>
<div class="md-shell">
  <aside class="md-shell__sidebar">
    <a href="/" class="md-shell__brand">
      <span class="md-shell__mark"></span>
      <span>MainDesk</span>
    </a>
    <nav class="md-shell__nav">
      <span class="md-shell__nav-group-label">Operate</span>
      <a href="/staff?key={qkey}" class="md-shell__link">Overview</a>
      <a href="/staff/inbox?key={qkey}" class="md-shell__link">Conversations {queue_badge}</a>
      <a href="/staff/analytics?key={qkey}" class="md-shell__link is-active">Analytics</a>
      <span class="md-shell__nav-group-label">Setup</span>
      <a href="/onboarding?key={qkey}" class="md-shell__link">Configure</a>
      <a href="/chat" class="md-shell__link" target="_blank">Preview chat ↗</a>
    </nav>
    <div class="md-shell__foot">
      <span class="md-shell__status-dot"></span>Live
    </div>
  </aside>
  <main class="md-shell__content">
    <div class="md-shell__content-header">
      <h1 class="md-shell__content-title">Analytics</h1>
      <p class="md-shell__content-sub">This month · so far</p>
    </div>
    <div class="an-grid">
      <div class="an-tile">
        <p class="label">Bookings handled</p>
        <p class="value">{m["bookings_this_month"]} {growth_bit}</p>
        <p class="footnote">vs {m["bookings_last_month"]} last month</p>
      </div>
      <div class="an-tile">
        <p class="label">Escalations to a human</p>
        <p class="value">{m["escalations_this_month"]}</p>
        <p class="footnote">{m["escalations_open"]} currently open</p>
      </div>
      <div class="an-tile">
        <p class="label">Avg. time to human</p>
        <p class="value">{avg_min}<span class="an-value-unit"> min</span></p>
        <p class="footnote">from escalation to clinician reply</p>
      </div>
      <div class="an-tile">
        <p class="label">Reception time replaced</p>
        <p class="value">{m["hours_replaced"]}<span class="an-value-unit"> hrs</span></p>
        <p class="footnote">est. at 4 min per autonomous booking</p>
      </div>
    </div>

    <div class="an-callout">
      <h2>What this tells you</h2>
      <p>Every escalation in that middle tile is a moment MainDesk chose humility — a case where confidence dipped or a red-flag intent surfaced. Every booking in the left tile is a call your team didn't have to take. The right tile compounds: for a $299/mo plan, an autonomous booking costs roughly $0.30 — a receptionist call costs $3–7.</p>
    </div>
  </main>
</div>
</body></html>"""
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
