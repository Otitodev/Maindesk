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

    # Voice on/off (Week-1 exit gate, PRD §11)
    healthdesk_voice: bool = True
    # Phone used to identify the caller when LiveKit gives us no metadata
    # (e.g. browser-based Agents Playground sessions). Maps to a seeded
    # patient via memory.profile.resolve_by_phone so recall still works.
    healthdesk_demo_patient_phone: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()
