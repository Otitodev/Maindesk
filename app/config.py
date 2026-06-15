from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Qwen / DashScope
    qwen_api_key: str = ""
    qwen_api_base: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    qwen_model_turbo: str = "qwen-turbo"
    qwen_model_plus: str = "qwen-plus"
    qwen_embed_model: str = "text-embedding-v3"
    qwen_embed_dim: int = 1024

    # Postgres / Supabase
    database_url: str = ""
    supabase_url: str = ""
    supabase_key: str = ""

    # LiveKit
    livekit_url: str = ""
    livekit_api_key: str = ""
    livekit_api_secret: str = ""

    # STT / TTS
    deepgram_api_key: str = ""
    elevenlabs_api_key: str = ""

    # WhatsApp / Evolution API
    evolution_api_url: str = ""
    evolution_api_key: str = ""
    evolution_instance: str = ""
    evolution_auth_mode: Literal["hmac", "token"] = "hmac"
    evolution_webhook_secret: str = ""
    evolution_ip_allowlist: list[str] = []
    evolution_send_timeout: float = 8.0

    # n8n + escalation
    n8n_webhook_url: str = ""
    gateway_proxy_key: str = ""
    staff_escalation_webhook_url: str = ""
    escalation_confidence_threshold: float = 0.45
    # Staff dashboard (/staff). Empty = open access (local demo only).
    staff_dashboard_key: str = ""

    # Voice on/off (Week-1 exit gate, PRD §11)
    healthdesk_voice: bool = True
    healthdesk_env: Literal["production", "demo"] = "production"
    # Phone used to identify the caller when LiveKit gives us no metadata
    # (e.g. browser-based Agents Playground sessions). Maps to a seeded
    # patient via memory.profile.resolve_by_phone so recall still works.
    healthdesk_demo_patient_phone: str = ""

    # Web chat
    web_api_key: str = ""
    clinic_timezone: str = "UTC"

    # Clinic business hours — drive real appointment-slot generation.
    clinic_open_hour: int = 9          # first slot starts at this hour (local)
    clinic_close_hour: int = 17        # no slot starts at/after this hour
    clinic_slot_minutes: int = 30      # slot length / appointment duration
    clinic_working_days: list[int] = [1, 2, 3, 4, 5]  # ISO weekday: 1=Mon..7=Sun
    slot_search_days: int = 14         # how far ahead suggest_slots looks

    # Google Calendar (optional). When both are set the calendar provider goes
    # live — real free/busy + appointment mirroring; otherwise the local stub
    # is used and behaviour matches Postgres-only scheduling.
    google_calendar_id: str = ""
    # Path to, or inline contents of, a service-account JSON key.
    google_service_account_json: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()
