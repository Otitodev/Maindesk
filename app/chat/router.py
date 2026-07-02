"""Patient-facing chat widget at /chat.

A self-contained HTML page that talks to the same `/webhooks/web`
endpoint as any other web caller — so the widget exercises the real
orchestrator graph, real tool layer, and real reply path. The page is
served unauthenticated so it works as a demo; the underlying
`/webhooks/web` is the surface that should be locked with `WEB_API_KEY`
in any non-demo deployment, in which case this widget will need a
proxy in front (out of scope here).
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter(prefix="/chat", tags=["chat"])

_template = (Path(__file__).parent / "templates" / "index.html").read_text(encoding="utf-8")


@router.get("", response_class=HTMLResponse)
async def chat_widget() -> HTMLResponse:
    return HTMLResponse(_template)
