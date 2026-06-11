"""LiveKit voice agent — full feature parity with the WhatsApp/web path.

Architecture (livekit-agents 1.x):

    caller speaks
        │
        ▼
    Deepgram STT
        │
        ▼
    HealthDeskAgent.llm_node()   ◀── overridden: pulls memories from pgvector
        │                            via memory.recall.recall_memories, then
        ▼                            delegates to Agent.default.llm_node()
    Qwen-Plus (DashScope)
        │  may call any of:
        │   • find_open_slots(date)
        │   • book_appointment(slot_iso)
        │   • find_my_appointments()
        │   • escalate_to_staff(reason)
        ▼
    ElevenLabs TTS
        │
        ▼
    caller hears

Caller identity is resolved at session start from room metadata
(`patient_phone` field) or falls back to HEALTHDESK_DEMO_PATIENT_PHONE
so browser-based Agents Playground sessions still get personalised
recall. SIP-driven sessions get the real caller ID once SIP is wired.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime

from livekit.agents import (
    Agent,
    AgentSession,
    JobContext,
    JobProcess,
    ModelSettings,
    WorkerOptions,
    cli,
    function_tool,
    llm,
)
from livekit.plugins import deepgram, elevenlabs, openai, silero

from app.config import get_settings
from app.gateway.schema import PatientMessage
from app.memory.profile import resolve_by_phone, upsert_profile
from app.memory.recall import recall_memories
from app.tools.appointments import book, find_existing, suggest_slots
from app.tools.escalation import notify_staff

log = logging.getLogger("voice")

SYSTEM_PROMPT = """You are HealthDesk, a friendly front-desk assistant for a clinic.
You are speaking out loud — keep sentences short and natural.

Grounding rules — these are strict:
- If you don't know a clinic-specific fact (hours, address, phone, doctor
  names, prices, insurance, services, parking), say "let me check and get
  back to you". NEVER invent these facts.
- Only confirm appointment slots that came back from your find_open_slots
  tool. Never make up times.
- Never give medical advice. For anything clinical, call escalate_to_staff
  and tell the caller a clinician will reach out.
- If the caller mentions anything urgent or unsafe, call escalate_to_staff
  immediately."""

GREETING_INSTRUCTIONS = (
    'Greet the caller warmly: "Hi — you have reached the front desk. '
    'How can I help today?"'
)


class HealthDeskAgent(Agent):
    """Voice persona with proactive memory recall and reactive tools."""

    def __init__(self, patient_id: str | None, patient_phone: str | None) -> None:
        super().__init__(instructions=SYSTEM_PROMPT)
        self._patient_id = patient_id
        self._patient_phone = patient_phone
        # Session id used by tools and memory write-back.
        self._session_id = f"voice:{patient_phone or 'unknown'}"

    # ── Lifecycle ───────────────────────────────────────────────────────

    async def on_enter(self) -> None:
        self.session.generate_reply(instructions=GREETING_INSTRUCTIONS)

    # ── Proactive memory recall (RAG via llm_node override) ─────────────

    async def llm_node(
        self,
        chat_ctx: llm.ChatContext,
        tools: list[llm.Tool],
        model_settings: ModelSettings,
    ):
        """Fetch relevant memories before each LLM call and inject as a
        system message. Pattern lifted from LiveKit's llamaindex-rag
        example so memory works for every turn, not just when the LLM
        decides to call a recall tool."""
        if self._patient_id and chat_ctx.items:
            last = chat_ctx.items[-1]
            user_text = getattr(last, "text_content", None)
            if (
                isinstance(last, llm.ChatMessage)
                and last.role == "user"
                and user_text
            ):
                try:
                    memories = await recall_memories(
                        patient_id=self._patient_id,
                        query=user_text,
                        top_k=3,
                    )
                except Exception:
                    log.exception("voice memory recall failed")
                    memories = []

                if memories:
                    block = "Relevant patient memory from previous visits:\n" + "\n".join(
                        f"- {m['content']}" for m in memories
                    )
                    chat_ctx.items.insert(
                        len(chat_ctx.items) - 1,
                        llm.ChatMessage(role="system", content=[block]),
                    )
                    log.info(
                        "voice: injected %d memories patient=%s",
                        len(memories), self._patient_id,
                    )

        return Agent.default.llm_node(self, chat_ctx, tools, model_settings)

    # ── Reactive tools (LLM-callable) ───────────────────────────────────

    def _voice_msg(self, content: str) -> PatientMessage:
        """Wrap whatever the tool needs into the PatientMessage shape the
        existing app.tools.* helpers already accept."""
        return PatientMessage(
            message_id="voice",
            session_id=self._session_id,
            patient_id=self._patient_id,
            channel="voice",
            content=content,
        )

    @function_tool
    async def find_open_slots(self, date: str = "") -> str:
        """Find available appointment slots. Pass an ISO date (YYYY-MM-DD)
        if the caller named a day; leave blank for the next available."""
        result = await suggest_slots(self._voice_msg(f"book for {date}"))
        slots = result.get("slots", []) or []
        if not slots:
            return "No open slots in that window."
        return "Open slots: " + ", ".join(slots)

    @function_tool
    async def book_appointment(self, slot_iso: str) -> str:
        """Book the caller's appointment. `slot_iso` must be an ISO 8601
        timestamp you confirmed via find_open_slots."""
        if not self._patient_id:
            return (
                "I cannot book yet because I have not identified you. "
                "Could you give me the phone number on file?"
            )
        try:
            ts = datetime.fromisoformat(slot_iso.replace("Z", "+00:00"))
        except ValueError:
            return f"That time did not parse: {slot_iso}"
        result = await book(self._patient_id, ts)
        return f"Booked for {result['starts_at']}."

    @function_tool
    async def find_my_appointments(self) -> str:
        """Look up the caller's upcoming appointments on file."""
        if not self._patient_id:
            return "I do not have you on file yet."
        result = await find_existing(self._voice_msg(""))
        appts = result.get("appointments", []) or []
        if not appts:
            return "No upcoming appointments on file."
        return "Upcoming: " + "; ".join(
            f"{a['starts_at']} ({a['status']})" for a in appts
        )

    @function_tool
    async def escalate_to_staff(self, reason: str) -> str:
        """Notify human staff that this caller needs help. Use this for
        any medical concern, urgent situation, or request that needs
        human judgement."""
        await notify_staff(self._voice_msg(reason), reason=reason)
        return "I have notified staff — they will be with you shortly."


# ── LLM / VAD wiring ────────────────────────────────────────────────────

def _qwen_llm() -> openai.LLM:
    s = get_settings()
    return openai.LLM(
        model=s.qwen_model_plus,
        api_key=s.qwen_api_key,
        base_url=s.qwen_api_base,
        temperature=0.3,
    )


def prewarm(proc: JobProcess) -> None:
    proc.userdata["vad"] = silero.VAD.load()


# ── Caller identity resolution ──────────────────────────────────────────

async def _resolve_caller(ctx: JobContext) -> tuple[str | None, str | None]:
    """Return (patient_id, patient_phone), falling back to the demo phone
    if neither room metadata nor a real caller ID is available."""
    s = get_settings()
    phone: str | None = None

    md = ctx.room.metadata or ""
    if md:
        try:
            data = json.loads(md)
            phone = data.get("patient_phone") or data.get("phone")
        except json.JSONDecodeError:
            log.warning("room metadata was not valid JSON: %r", md[:200])

    if not phone and s.healthdesk_demo_patient_phone:
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


# ── Entrypoint ──────────────────────────────────────────────────────────

async def entrypoint(ctx: JobContext) -> None:
    s = get_settings()
    if not s.healthdesk_voice:
        log.info("HEALTHDESK_VOICE=false; voice worker exiting")
        return

    await ctx.connect()

    patient_id, patient_phone = await _resolve_caller(ctx)
    log.info(
        "voice session start room=%s patient_id=%s phone=%s",
        ctx.room.name, patient_id, patient_phone,
    )

    session = AgentSession(
        vad=ctx.proc.userdata["vad"],
        stt=deepgram.STT(api_key=s.deepgram_api_key, model="nova-3"),
        llm=_qwen_llm(),
        tts=elevenlabs.TTS(api_key=s.elevenlabs_api_key, model="eleven_flash_v2_5"),
    )
    agent = HealthDeskAgent(patient_id=patient_id, patient_phone=patient_phone)
    await session.start(agent=agent, room=ctx.room)


if __name__ == "__main__":
    os.environ.setdefault("LIVEKIT_URL", get_settings().livekit_url)
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint, prewarm_fnc=prewarm))
