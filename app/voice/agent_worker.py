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

# Load .env into os.environ BEFORE importing livekit.* so the LiveKit
# CLI sees LIVEKIT_API_KEY / LIVEKIT_API_SECRET. Pydantic Settings reads
# the same file for our own code but never exports to os.environ.
from dotenv import load_dotenv
load_dotenv()

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
from app.memory.write import persist_turn
from app.tools.appointments import book, find_existing, suggest_slots
from app.tools.escalation import notify_staff

# Minimum number of items in the conversation log to bother persisting.
# Greeting + one short exchange is 3 items; we want at least 2 full
# back-and-forths so the summariser has something useful to work with.
_PERSIST_MIN_ITEMS = 4
_PERSIST_IMPORTANCE = 0.6

log = logging.getLogger("voice")

SYSTEM_PROMPT = """You are HealthDesk, a friendly front-desk assistant for a clinic.
You are speaking out loud — keep sentences short and natural.

Filler rule — VERY IMPORTANT for natural conversation:
- Before calling ANY tool (find_open_slots, book_appointment,
  find_my_appointments, escalate_to_staff), say a short filler sentence
  FIRST so the caller hears you and doesn't think the line went dead.
- Vary the filler. Use phrases like:
    "One moment, let me check that for you..."
    "Sure, let me pull that up..."
    "Just a second while I look..."
    "Let me see..."
- Then call the tool. After the tool returns, continue with the result.
- The filler is mandatory whenever a tool runs. Never silently invoke
  a tool — the caller hears nothing while it runs, and that feels broken.

Grounding rules — these are strict:
- If you don't know a clinic-specific fact (hours, address, phone, doctor
  names, prices, insurance, services, parking), say "let me check and get
  back to you". NEVER invent these facts.
- Only confirm appointment slots that came back from your find_open_slots
  tool. Never make up times.
- Never give medical advice. For anything clinical, call escalate_to_staff
  and tell the caller a clinician will reach out.
- If the caller mentions anything urgent or unsafe, call escalate_to_staff
  immediately (still with a brief filler — "Hold on, getting someone now...")."""

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
        # Captured (role, text) tuples — populated by _capture_conversation_item
        # via the conversation_item_added event.
        self._conversation_log: list[tuple[str, str]] = []

    # ── Lifecycle ───────────────────────────────────────────────────────

    async def on_enter(self) -> None:
        # Wire turn capture so we can write a session memory on exit.
        # Bound method works as a sync handler — pyee-style emitter.
        self.session.on("conversation_item_added", self._capture_conversation_item)
        self.session.generate_reply(instructions=GREETING_INSTRUCTIONS)

    async def on_exit(self) -> None:
        await self._persist_session()

    # ── Conversation capture + persistence ──────────────────────────────

    def _capture_conversation_item(self, ev) -> None:
        """Append (role, text) tuples to the session log as LiveKit emits
        them. Synchronous because it's pure list-append — any I/O lives
        in on_exit / _persist_session."""
        item = getattr(ev, "item", None)
        if item is None:
            return
        role = getattr(item, "role", None)
        text = getattr(item, "text_content", None)
        if text and role in ("user", "assistant"):
            self._conversation_log.append((role, text))

    async def _persist_session(self) -> None:
        """Summarise the call and write one memory row. Skips when there
        is no patient on file or the call was too short to be useful."""
        if not self._patient_id:
            return
        if len(self._conversation_log) < _PERSIST_MIN_ITEMS:
            log.info(
                "voice: skipping write-back, only %d items",
                len(self._conversation_log),
            )
            return
        user_lines = "\n".join(t for r, t in self._conversation_log if r == "user")
        assistant_lines = "\n".join(t for r, t in self._conversation_log if r == "assistant")
        if not user_lines:
            return
        try:
            await persist_turn(
                patient_id=self._patient_id,
                session_id=self._session_id,
                user_text=user_lines,
                assistant_text=assistant_lines,
                importance=_PERSIST_IMPORTANCE,
                intent="voice_session",
            )
            log.info(
                "voice: persisted session memory patient=%s items=%d",
                self._patient_id, len(self._conversation_log),
            )
        except Exception:
            log.exception("voice session persist failed")

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
        if the caller named a day; leave blank for the next available.

        BEFORE calling this, say a brief filler out loud — e.g.
        "Let me check what we have available...". Do not call silently."""
        result = await suggest_slots(self._voice_msg(f"book for {date}"))
        slots = result.get("slots", []) or []
        if not slots:
            return "No open slots in that window."
        return "Open slots: " + ", ".join(slots)

    @function_tool
    async def book_appointment(self, slot_iso: str) -> str:
        """Book the caller's appointment. `slot_iso` must be an ISO 8601
        timestamp you confirmed via find_open_slots.

        BEFORE calling this, say a brief filler out loud — e.g.
        "Booking that for you now...". Do not call silently."""
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
        if result.get("error") == "slot_taken":
            return (
                f"Sorry, that slot was just taken. "
                f"Would you like me to find another available time?"
            )
        return f"Booked for {result['starts_at']}."

    @function_tool
    async def find_my_appointments(self) -> str:
        """Look up the caller's upcoming appointments on file.

        BEFORE calling this, say a brief filler out loud — e.g.
        "One moment, pulling up your appointments...". Do not call silently."""
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
        human judgement.

        BEFORE calling this, reassure the caller out loud — e.g.
        "Hold on, getting someone for you now..." — do not call silently.
        The caller is often anxious when this fires; the filler matters."""
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
    # agent_name="healthdesk" registers us for explicit dispatch so the
    # worker shows up in LiveKit Cloud Console's agent dropdown. Without
    # a name the worker only runs via auto-dispatch on API-created rooms,
    # which the Console UI doesn't trigger.
    cli.run_app(
        WorkerOptions(
            entrypoint_fnc=entrypoint,
            prewarm_fnc=prewarm,
            agent_name="healthdesk",
        )
    )
