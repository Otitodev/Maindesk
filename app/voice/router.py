"""Twilio telephony entry points for the voice gateway.

Two routes:

- `POST /voice/twilio/incoming` — Twilio's voice webhook for an inbound
  call. Returns TwiML that opens a Media Stream back to `/voice/twilio/media`,
  carrying the caller's number through as a `<Parameter>` so we don't need a
  separate Twilio REST round-trip to look it up.
- `WS /voice/twilio/media` — the Media Stream itself. One connection per
  call; each gets its own Pipecat pipeline via `app.voice.bot.run_call`.
  There is no separate long-running worker process — a call's lifetime is
  exactly the lifetime of this websocket handler coroutine.
"""

from __future__ import annotations

import logging
from html import escape

from fastapi import APIRouter, Request, Response, WebSocket
from pipecat.runner.utils import parse_telephony_websocket
from pipecat.serializers.twilio import TwilioFrameSerializer
from pipecat.transports.websocket.fastapi import FastAPIWebsocketParams, FastAPIWebsocketTransport

from app import clinic_config
from app.config import get_settings
from app.memory.profile import resolve_by_phone, upsert_profile
from app.voice.bot import run_call

log = logging.getLogger("voice")

router = APIRouter(prefix="/voice/twilio", tags=["voice"])


@router.post("/incoming")
async def incoming_call(request: Request) -> Response:
    """Twilio voice webhook — returns TwiML that opens the media stream."""
    form = await request.form()
    from_number = str(form.get("From") or "")
    to_number = str(form.get("To") or "")

    host = request.headers.get("host") or request.url.hostname or ""
    stream_url = f"wss://{host}/voice/twilio/media"

    twiml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        "<Response><Connect>"
        f'<Stream url="{escape(stream_url)}">'
        f'<Parameter name="from_number" value="{escape(from_number)}"/>'
        f'<Parameter name="to_number" value="{escape(to_number)}"/>'
        "</Stream></Connect></Response>"
    )
    return Response(content=twiml, media_type="application/xml")


async def _resolve_caller(from_number: str | None) -> tuple[str | None, str | None]:
    """Return (patient_id, patient_phone), falling back to the demo phone
    if Twilio gave us no caller ID (e.g. local websocket-client testing)."""
    s = get_settings()
    phone = from_number or None

    if not phone and s.healthdesk_env == "demo" and s.healthdesk_demo_patient_phone:
        phone = s.healthdesk_demo_patient_phone
        log.info("voice: using demo patient phone %s", phone)

    if not phone:
        return None, None

    try:
        profile = await resolve_by_phone(phone)
        patient_id = profile["id"] if profile else await upsert_profile(phone=phone)
        return str(patient_id), phone
    except Exception:
        log.exception("voice identity resolution failed phone=%s", phone)
        return None, phone


@router.websocket("/media")
async def media_stream(websocket: WebSocket) -> None:
    s = get_settings()
    if not s.healthdesk_voice:
        await websocket.close(code=1000)
        return

    await websocket.accept()

    try:
        transport_type, call_data = await parse_telephony_websocket(websocket)
    except ValueError:
        log.warning("voice: websocket closed before telephony handshake")
        return

    if transport_type != "twilio":
        log.warning("voice: unexpected transport_type=%s, closing", transport_type)
        await websocket.close(code=1008)
        return

    serializer = TwilioFrameSerializer(
        stream_sid=call_data["stream_id"],
        call_sid=call_data["call_id"],
        account_sid=s.twilio_account_sid,
        auth_token=s.twilio_auth_token,
    )
    transport = FastAPIWebsocketTransport(
        websocket=websocket,
        params=FastAPIWebsocketParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
            add_wav_header=False,
            serializer=serializer,
        ),
    )

    patient_id, patient_phone = await _resolve_caller(call_data.from_number)
    await clinic_config.refresh()  # pick up latest clinic persona/hours for this call

    try:
        await run_call(transport, patient_id=patient_id, patient_phone=patient_phone)
    except Exception:
        log.exception("voice: unhandled exception running the call")
