from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)

Channel = Literal["voice", "whatsapp", "web", "mcp"]


class PatientMessage(BaseModel):
    """Normalised inbound message. All platform adapters emit this before
    anything touches the orchestrator. See TRD §6.1."""

    message_id: str
    session_id: str  # "{channel}:{chat_id}", e.g. "whatsapp:+2348012345678"
    patient_id: str | None = None  # resolved from memory; None on first contact
    channel: Channel
    content: str
    media_url: str | None = None
    timestamp: datetime = Field(default_factory=_utcnow)
    platform_meta: dict = Field(default_factory=dict)


class PatientReply(BaseModel):
    """Normalised outbound reply pre-redaction."""

    session_id: str
    channel: Channel
    content: str
    media_url: str | None = None
