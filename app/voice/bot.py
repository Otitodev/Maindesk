"""Pipecat voice pipeline — full feature parity with the WhatsApp/web path.

Architecture (pipecat-ai 1.5.x, embedded in the FastAPI app — no separate
worker process):

    caller speaks (Twilio Media Stream)
        │
        ▼
    Deepgram STT
        │
        ▼
    MemoryRecallProcessor   ◀── pulls memories from pgvector via
        │                       memory.recall.recall_memories and inserts
        │                       them as a system message before the LLM call
        ▼
    Qwen-Plus (DashScope, via Pipecat's OpenAI-compatible LLM service)
        │  may call any of:
        │   • find_open_slots(date)
        │   • book_appointment(slot_iso)
        │   • find_my_appointments()
        │   • cancel_appointment(starts_at_iso)
        │   • reschedule_appointment(current_starts_at_iso, new_starts_at_iso)
        │   • escalate_to_staff(reason)
        ▼
    ElevenLabs TTS
        │
        ▼
    caller hears

Caller identity is resolved by the router (`app/voice/router.py`) from the
Twilio caller ID passed through as a TwiML `<Stream>` custom parameter, or
falls back to HEALTHDESK_DEMO_PATIENT_PHONE for local websocket-client
testing where there's no real PSTN call.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime

from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.audio.vad.vad_analyzer import VADParams
from pipecat.frames.frames import Frame, LLMContextFrame, LLMRunFrame, TTSSpeakFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.worker import PipelineParams, PipelineWorker
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    LLMContextAggregatorPair,
    LLMUserAggregatorParams,
)
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
from pipecat.services.deepgram.stt import DeepgramSTTService
from pipecat.services.elevenlabs.tts import ElevenLabsTTSService
from pipecat.services.llm_service import FunctionCallParams
from pipecat.services.openai.llm import OpenAILLMService
from pipecat.transports.base_transport import BaseTransport
from pipecat.workers.runner import WorkerRunner

from app import clinic_config
from app.agents.hours import should_defer_to_staff
from app.config import get_settings
from app.gateway.schema import PatientMessage
from app.memory.recall import recall_memories
from app.memory.write import persist_turn
from app.tools.appointments import book, cancel, find_existing, reschedule, suggest_slots
from app.tools.escalation import notify_staff

log = logging.getLogger("voice")

# Minimum number of user/assistant turns to bother persisting a session
# memory. Greeting + one short exchange is ~2 items; we want at least 2
# full back-and-forths so the summariser has something useful to work with.
_PERSIST_MIN_ITEMS = 4
_PERSIST_IMPORTANCE = 0.6

SYSTEM_PROMPT = """You are HealthDesk, a friendly front-desk assistant for a clinic.
You are speaking out loud — keep sentences short and natural.

Filler rule — VERY IMPORTANT for natural conversation:
- Before calling ANY tool (find_open_slots, book_appointment,
  find_my_appointments, cancel_appointment, reschedule_appointment,
  escalate_to_staff), say a short filler sentence FIRST so the caller hears
  you and doesn't think the line went dead.
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
  immediately (still with a brief filler — "Hold on, getting someone now...").

Language rule:
- If the caller speaks a language other than English, reply entirely in
  the caller's language (the TTS voice is multilingual). Keep using their
  language until they switch."""

DEFAULT_GREETING = "Hi — you have reached the front desk. How can I help today?"

# Used in after-hours mode when the clinic is actually open: staff are in, so
# offer to connect/take a message rather than handling everything solo.
GREETING_DEFERRAL = (
    "Greet the caller warmly and let them know the clinic is open and staff can "
    "help directly. Offer to take a quick message or connect them, and if they "
    "need anything call escalate_to_staff. Keep it brief and friendly."
)


def _parse_iso(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


@dataclass
class CallSession:
    """Per-call state shared across tool handlers via `app_resources`."""

    patient_id: str | None
    patient_phone: str | None

    @property
    def session_id(self) -> str:
        return f"voice:{self.patient_phone or 'unknown'}"

    def voice_msg(self, content: str) -> PatientMessage:
        """Wrap whatever the tool needs into the PatientMessage shape the
        existing app.tools.* helpers already accept."""
        return PatientMessage(
            message_id="voice",
            session_id=self.session_id,
            patient_id=self.patient_id,
            channel="voice",
            content=content,
        )


# ── Proactive memory recall (RAG via a frame processor) ─────────────────


class MemoryRecallProcessor(FrameProcessor):
    """Fetch relevant memories before each LLM call and inject as a system
    message. Pattern lifted from LiveKit's llamaindex-rag example so memory
    works for every turn, not just when the LLM decides to call a recall
    tool."""

    def __init__(self, session: CallSession) -> None:
        super().__init__()
        self._session = session

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)

        if isinstance(frame, LLMContextFrame) and self._session.patient_id:
            messages = frame.context.get_messages()
            last_user_text: str | None = None
            last_user_idx: int | None = None
            for idx in range(len(messages) - 1, -1, -1):
                msg = messages[idx]
                if isinstance(msg, dict) and msg.get("role") == "user":
                    content = msg.get("content")
                    if isinstance(content, str) and content:
                        last_user_text = content
                        last_user_idx = idx
                    break

            if last_user_text is not None and last_user_idx is not None:
                try:
                    memories = await recall_memories(
                        patient_id=self._session.patient_id,
                        query=last_user_text,
                        top_k=3,
                    )
                except Exception:
                    log.exception("voice memory recall failed")
                    memories = []

                if memories:
                    block = "Relevant patient memory from previous visits:\n" + "\n".join(
                        f"- {m['content']}" for m in memories
                    )
                    messages.insert(last_user_idx, {"role": "system", "content": block})
                    frame.context.set_messages(messages)
                    log.info(
                        "voice: injected %d memories patient=%s",
                        len(memories), self._session.patient_id,
                    )

        await self.push_frame(frame, direction)


# ── Reactive tools (LLM-callable) ────────────────────────────────────────
# Direct-function style: Pipecat derives each tool's JSON schema from the
# signature + docstring. Session state (patient_id, etc.) comes in via
# `params.app_resources`, wired up as the CallSession in run_call().


async def find_open_slots(params: FunctionCallParams, date: str = "") -> None:
    """Find available appointment slots.

    Args:
        date: ISO date (YYYY-MM-DD) if the caller named a day; leave blank
            for the next available slot.
    """
    session: CallSession = params.app_resources
    result = await suggest_slots(session.voice_msg(f"book for {date}"))
    slots = result.get("slots", []) or []
    if not slots:
        await params.result_callback("No open slots in that window.")
        return
    await params.result_callback("Open slots: " + ", ".join(slots))


async def book_appointment(params: FunctionCallParams, slot_iso: str) -> None:
    """Book the caller's appointment.

    Args:
        slot_iso: ISO 8601 timestamp you confirmed via find_open_slots.
    """
    session: CallSession = params.app_resources
    if not session.patient_id:
        await params.result_callback(
            "I cannot book yet because I have not identified you. "
            "Could you give me the phone number on file?"
        )
        return
    try:
        ts = datetime.fromisoformat(slot_iso.replace("Z", "+00:00"))
    except ValueError:
        await params.result_callback(f"That time did not parse: {slot_iso}")
        return
    result = await book(session.patient_id, ts)
    if result.get("error") == "slot_taken":
        await params.result_callback(
            "Sorry, that slot was just taken. "
            "Would you like me to find another available time?"
        )
        return
    await params.result_callback(f"Booked for {result['starts_at']}.")


async def find_my_appointments(params: FunctionCallParams) -> None:
    """Look up the caller's upcoming appointments on file."""
    session: CallSession = params.app_resources
    if not session.patient_id:
        await params.result_callback("I do not have you on file yet.")
        return
    result = await find_existing(session.voice_msg(""))
    appts = result.get("appointments", []) or []
    if not appts:
        await params.result_callback("No upcoming appointments on file.")
        return
    await params.result_callback(
        "Upcoming: " + "; ".join(f"{a['starts_at']} ({a['status']})" for a in appts)
    )


async def escalate_to_staff(params: FunctionCallParams, reason: str) -> None:
    """Notify human staff that this caller needs help. Use this for any
    medical concern, urgent situation, or request that needs human
    judgement.

    Args:
        reason: Why the caller needs human help.
    """
    session: CallSession = params.app_resources
    await notify_staff(session.voice_msg(reason), reason=reason)
    await params.result_callback("I have notified staff — they will be with you shortly.")


async def _resolve_appointment_id(session: CallSession, starts_at_iso: str) -> str | None:
    """Resolve a spoken appointment time back to its row id by matching
    against the caller's booked appointments. Compares parsed timestamps
    so trailing-zero / offset formatting differences don't cause a miss."""
    target = _parse_iso(starts_at_iso)
    result = await find_existing(session.voice_msg(""))
    for appt in result.get("appointments", []) or []:
        if appt.get("status") != "booked":
            continue
        if appt["starts_at"] == starts_at_iso or (
            target is not None and _parse_iso(appt["starts_at"]) == target
        ):
            return appt["id"]
    return None


async def cancel_appointment(params: FunctionCallParams, starts_at_iso: str) -> None:
    """Cancel the caller's appointment at the given time.

    Args:
        starts_at_iso: ISO 8601 start time of an existing appointment — use
            the exact value returned by find_my_appointments.
    """
    session: CallSession = params.app_resources
    if not session.patient_id:
        await params.result_callback("I do not have you on file yet.")
        return
    appt_id = await _resolve_appointment_id(session, starts_at_iso)
    if not appt_id:
        await params.result_callback("I could not find a booked appointment at that time.")
        return
    result = await cancel(session.patient_id, appt_id)
    if result.get("error"):
        await params.result_callback("I could not cancel that — let me get a colleague to help.")
        return
    await params.result_callback(f"Done — your appointment on {result['starts_at']} is cancelled.")


async def reschedule_appointment(
    params: FunctionCallParams, current_starts_at_iso: str, new_starts_at_iso: str
) -> None:
    """Move the caller's existing appointment to a new time.

    Args:
        current_starts_at_iso: The appointment's current start time (from
            find_my_appointments).
        new_starts_at_iso: A slot you confirmed via find_open_slots.
    """
    session: CallSession = params.app_resources
    if not session.patient_id:
        await params.result_callback("I do not have you on file yet.")
        return
    new_ts = _parse_iso(new_starts_at_iso)
    if new_ts is None:
        await params.result_callback(f"That new time did not parse: {new_starts_at_iso}")
        return
    appt_id = await _resolve_appointment_id(session, current_starts_at_iso)
    if not appt_id:
        await params.result_callback("I could not find your current appointment to move.")
        return
    result = await reschedule(session.patient_id, appt_id, new_ts)
    if result.get("error") == "slot_taken":
        await params.result_callback(
            "Sorry, that new time was just taken. "
            "Would you like me to find another available slot?"
        )
        return
    if result.get("error"):
        await params.result_callback("I could not move that — let me get a colleague to help.")
        return
    await params.result_callback(f"Done — moved to {result['starts_at']}.")


_TOOLS = [
    find_open_slots,
    book_appointment,
    find_my_appointments,
    escalate_to_staff,
    cancel_appointment,
    reschedule_appointment,
]


# ── Session persistence ──────────────────────────────────────────────────


async def _persist_session(session: CallSession, context: LLMContext) -> None:
    """Summarise the call and write one memory row. Skips when there is no
    patient on file or the call was too short to be useful."""
    if not session.patient_id:
        return
    turns: list[tuple[str, str]] = []
    for msg in context.get_messages():
        if not isinstance(msg, dict):
            continue
        role = msg.get("role")
        if role not in ("user", "assistant"):
            continue
        content = msg.get("content")
        if isinstance(content, str) and content:
            turns.append((role, content))
    if len(turns) < _PERSIST_MIN_ITEMS:
        log.info("voice: skipping write-back, only %d items", len(turns))
        return
    user_lines = "\n".join(t for r, t in turns if r == "user")
    assistant_lines = "\n".join(t for r, t in turns if r == "assistant")
    if not user_lines:
        return
    try:
        await persist_turn(
            patient_id=session.patient_id,
            session_id=session.session_id,
            user_text=user_lines,
            assistant_text=assistant_lines,
            importance=_PERSIST_IMPORTANCE,
            intent="voice_session",
        )
        log.info(
            "voice: persisted session memory patient=%s items=%d",
            session.patient_id, len(turns),
        )
    except Exception:
        log.exception("voice session persist failed")


# ── Pipeline assembly + call lifecycle ───────────────────────────────────


async def run_call(
    transport: BaseTransport,
    *,
    patient_id: str | None,
    patient_phone: str | None,
    audio_in_sample_rate: int = 8000,
    audio_out_sample_rate: int = 8000,
) -> None:
    """Build the pipeline for one call and run it to completion.

    Sample rate defaults match Twilio's 8kHz mu-law Media Streams; the
    browser widget (WebRTC/Opus) passes its own, higher-fidelity rates.
    """
    s = get_settings()
    if not s.healthdesk_voice:
        log.info("HEALTHDESK_VOICE=false; refusing call")
        return

    session = CallSession(patient_id=patient_id, patient_phone=patient_phone)
    log.info(
        "voice session start patient_id=%s phone=%s",
        session.patient_id, session.patient_phone,
    )

    block = clinic_config.knowledge_block()
    instructions = f"{SYSTEM_PROMPT}\n\n{block}" if block else SYSTEM_PROMPT

    context = LLMContext(
        messages=[{"role": "system", "content": instructions}],
        tools=_TOOLS,
    )
    user_aggregator, assistant_aggregator = LLMContextAggregatorPair(
        context,
        user_params=LLMUserAggregatorParams(
            # Tighter silence window — 250ms of quiet is enough to call
            # end-of-turn for a phone conversation (defaults feel laggy on
            # a receptionist agent). start_secs trimmed to match.
            vad_analyzer=SileroVADAnalyzer(
                params=VADParams(stop_secs=0.25, start_secs=0.2),
            ),
        ),
    )

    stt = DeepgramSTTService(
        api_key=s.deepgram_api_key,
        settings=DeepgramSTTService.Settings(model="nova-3", language="en-US"),
    )
    # qwen-turbo shaves ~1-2s off first-token latency vs qwen-plus and is
    # accurate enough for short receptionist turns. Switch to plus only if
    # accuracy on long, multi-intent turns becomes the bottleneck.
    llm = OpenAILLMService(
        api_key=s.dashscope_api_key,
        base_url=s.qwen_api_base,
        settings=OpenAILLMService.Settings(model=s.qwen_model_turbo, temperature=0.3),
    )
    tts = ElevenLabsTTSService(
        api_key=s.elevenlabs_api_key,
        settings=ElevenLabsTTSService.Settings(
            voice=s.elevenlabs_voice_id, model="eleven_flash_v2_5"
        ),
    )
    memory_recall = MemoryRecallProcessor(session)

    pipeline = Pipeline(
        [
            transport.input(),
            stt,
            user_aggregator,
            memory_recall,
            llm,
            tts,
            transport.output(),
            assistant_aggregator,
        ]
    )

    worker = PipelineWorker(
        pipeline,
        params=PipelineParams(
            audio_in_sample_rate=audio_in_sample_rate,
            audio_out_sample_rate=audio_out_sample_rate,
            enable_metrics=True,
        ),
        app_resources=session,
    )

    @transport.event_handler("on_client_connected")
    async def on_client_connected(transport, client):
        # In after-hours mode during open hours, greet as a staffed front
        # desk and let the LLM generate the line; otherwise use the clinic-
        # configured greeting (or a generic fallback) and speak it directly,
        # skipping the LLM round trip so audio starts immediately.
        if should_defer_to_staff():
            context.add_message({"role": "system", "content": GREETING_DEFERRAL})
            await worker.queue_frames([LLMRunFrame()])
        else:
            greeting = (clinic_config.current().get("greeting") or "").strip()
            await worker.queue_frames([TTSSpeakFrame(text=greeting or DEFAULT_GREETING)])

    @transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(transport, client):
        await worker.cancel()

    # handle_sigint=False: uvicorn owns SIGINT/SIGTERM for the host process.
    runner = WorkerRunner(handle_sigint=False, force_gc=True)
    await runner.add_workers(worker)
    await runner.run()

    await _persist_session(session, context)
