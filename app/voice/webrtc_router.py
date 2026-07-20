"""Browser voice widget — WebRTC entry point for the voice gateway.

Alongside the Twilio phone number (`app/voice/router.py`), clinics can embed
this widget on their own site so customers can click "Call" and talk to the
same agent from a browser tab — no phone number needed. Uses Pipecat's
SmallWebRTCTransport (backed by aiortc), which is self-hosted and needs no
third-party WebRTC vendor or credentials, unlike the Twilio path.

Three routes:

- `GET /voice/web` — serves the embeddable widget page.
- `POST /voice/web/offer` — WebRTC SDP offer/answer exchange. On a new
  connection, spawns a Pipecat pipeline via `app.voice.bot.run_call`, same
  as the phone path; only the transport differs.
- `PATCH /voice/web/offer` — trickle ICE candidates.

Callers are anonymous (no phone number to resolve identity from), same as
an unidentified web-chat visitor — the agent asks for identifying details
itself when a tool needs them (e.g. booking).
"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, HTTPException
from fastapi.responses import HTMLResponse
from pipecat.transports.base_transport import BaseTransport, TransportParams
from pipecat.transports.smallwebrtc.request_handler import (
    SmallWebRTCPatchRequest,
    SmallWebRTCRequest,
    SmallWebRTCRequestHandler,
)
from pipecat.transports.smallwebrtc.transport import SmallWebRTCTransport

from app import clinic_config
from app.config import get_settings
from app.voice.bot import run_call

log = logging.getLogger("voice")

router = APIRouter(prefix="/voice/web", tags=["voice"])

# MULTIPLE: every browser tab that connects gets its own independent call,
# same as every phone call gets its own websocket on the Twilio side.
webrtc_handler = SmallWebRTCRequestHandler()

_widget_template = (Path(__file__).parent / "templates" / "web_widget.html").read_text(
    encoding="utf-8"
)


@router.get("", response_class=HTMLResponse)
async def widget() -> HTMLResponse:
    return HTMLResponse(_widget_template)


async def _run_web_call(transport: BaseTransport) -> None:
    try:
        # WebRTC/Opus interop rates — Pipecat's own defaults, much higher
        # fidelity than Twilio's 8kHz telephony audio.
        await run_call(
            transport,
            patient_id=None,
            patient_phone=None,
            audio_in_sample_rate=16000,
            audio_out_sample_rate=24000,
        )
    except Exception:
        log.exception("voice: unhandled exception running web call")


@router.post("/offer")
async def offer(request: SmallWebRTCRequest, background_tasks: BackgroundTasks) -> dict:
    s = get_settings()
    if not s.healthdesk_voice:
        raise HTTPException(status_code=503, detail="voice is disabled")

    async def webrtc_connection_callback(connection) -> None:
        transport = SmallWebRTCTransport(
            webrtc_connection=connection,
            params=TransportParams(
                audio_in_enabled=True,
                audio_out_enabled=True,
                audio_out_10ms_chunks=2,
            ),
        )
        await clinic_config.refresh()  # pick up latest clinic persona/hours for this call
        background_tasks.add_task(_run_web_call, transport)

    answer = await webrtc_handler.handle_web_request(
        request=request,
        webrtc_connection_callback=webrtc_connection_callback,
    )
    return answer


@router.patch("/offer")
async def ice_candidate(request: SmallWebRTCPatchRequest) -> dict:
    await webrtc_handler.handle_patch_request(request)
    return {"status": "success"}


async def close() -> None:
    """Tear down any live browser calls. Call from the app's shutdown hook."""
    await webrtc_handler.close()
