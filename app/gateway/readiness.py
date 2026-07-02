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

    web_ready = True  # /webhooks/web has no external dep; live once app is up

    whatsapp_ready = _ready(
        s.evolution_api_url, s.evolution_api_key, s.evolution_instance
    )
    whatsapp_auth = "hmac" if s.evolution_webhook_secret else "none"

    email_ready = _ready(s.email_api_url, s.email_api_token, s.email_from)

    voice_ready = _ready(
        s.livekit_url,
        s.livekit_api_key,
        s.livekit_api_secret,
        s.deepgram_api_key,
        s.elevenlabs_api_key,
    ) and s.healthdesk_voice

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
            "notes": "Evolution API (WhatsApp Business) required",
        },
        "email": {
            "endpoint": "POST /webhooks/email",
            "live": email_ready,
            "notes": "Postmark-shaped provider parse webhook",
        },
        "voice": {
            "endpoint": "LiveKit worker (agent_name=healthdesk)",
            "live": voice_ready,
            "notes": "LiveKit + Deepgram + ElevenLabs required; HEALTHDESK_VOICE=true",
        },
        "summary": {
            "total": 4,
            "live": sum([web_ready, whatsapp_ready, email_ready, voice_ready]),
        },
    }
