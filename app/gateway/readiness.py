"""Gateway readiness report.

Every channel has a webhook route registered, so the *endpoint* is always
live — but whether it can successfully talk to its external service
depends on whether the right credentials are set in `.env`. This endpoint
surfaces that per-gateway state so operators (and hackathon judges) can
see channel readiness at a glance.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.config import get_settings

router = APIRouter(tags=["health"])


@router.get("/health/gateways")
async def gateways() -> dict:
    s = get_settings()

    def _ready(*required: str) -> bool:
        return all(bool(x) for x in required)

    demo = s.healthdesk_demo_mode

    web_ready = True  # /webhooks/web has no external dep; live once app is up

    whatsapp_creds = _ready(
        s.evolution_api_url, s.evolution_api_key, s.evolution_instance
    )
    whatsapp_ready = whatsapp_creds or demo
    whatsapp_auth = "hmac" if s.evolution_webhook_secret else "none"

    email_creds = _ready(s.email_api_url, s.email_api_token, s.email_from)
    email_ready = email_creds or demo

    voice_core_ready = _ready(s.deepgram_api_key, s.elevenlabs_api_key, s.dashscope_api_key)
    telephony_ready = _ready(s.twilio_account_sid, s.twilio_auth_token)
    # Web widget needs no telephony vendor — it's a self-hosted WebRTC
    # transport (aiortc), so it's live as soon as STT/TTS/LLM creds are set.
    voice_web_ready = bool(voice_core_ready and s.healthdesk_voice)
    voice_phone_ready = bool(voice_core_ready and telephony_ready and s.healthdesk_voice)
    voice_ready = voice_web_ready or voice_phone_ready

    return {
        "web": {
            "endpoint": "POST /webhooks/web",
            "live": web_ready,
            "notes": "chat widget at /chat posts here",
        },
        "whatsapp": {
            "endpoint": "POST /webhooks/whatsapp",
            "live": whatsapp_ready,
            "auth": whatsapp_auth,
            "mode": "demo" if demo and not whatsapp_creds else "live",
            "notes": (
                "demo mode: outbound routes to /webhooks/whatsapp/inbox"
                if demo and not whatsapp_creds
                else "Evolution API (WhatsApp Business) required"
            ),
        },
        "email": {
            "endpoint": "POST /webhooks/email",
            "live": email_ready,
            "mode": "demo" if demo and not email_creds else "live",
            "notes": (
                "demo mode: outbound routes to /webhooks/email/inbox"
                if demo and not email_creds
                else "Postmark-shaped provider parse webhook"
            ),
        },
        "voice": {
            "endpoint": "WS /voice/twilio/media, POST /voice/web/offer",
            "live": voice_ready,
            "phone": voice_phone_ready,
            "web": voice_web_ready,
            "notes": (
                "web widget needs Deepgram + ElevenLabs + DashScope; "
                "phone additionally needs Twilio; HEALTHDESK_VOICE=true"
            ),
        },
        "summary": {
            "total": 4,
            "live": sum([web_ready, whatsapp_ready, email_ready, voice_ready]),
            "demo_mode": demo,
        },
    }
