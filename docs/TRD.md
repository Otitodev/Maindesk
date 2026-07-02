# Technical Requirements Document — HealthDesk AI

**Version:** 2.0  
**Date:** June 9, 2026  
**Author:** Otito Ogene  
**Submission:** Global AI Hackathon Series with Qwen Cloud — Track 4: Autopilot Agent

---

## 1. System Overview

HealthDesk AI is a multi-agent system built on LangGraph, FastAPI, and Qwen Cloud. It exposes a unified messaging gateway that normalises events from LiveKit (voice/SIP), Evolution API (WhatsApp), and web webhooks into a single internal `PatientMessage` schema, dispatches them to specialist LangGraph agents, and maintains persistent patient memory across sessions using Supabase + pgvector.

All LLM inference runs on Qwen via Alibaba Cloud. The voice layer is handled by LiveKit Agents v1.5.x (replacing VAPI), which provides WebRTC transport, native SIP telephony, preemptive generation, and adaptive interruption handling — giving full pipeline control over STT → LLM → TTS latency. The backend is containerised and deployed on Alibaba Cloud ECS. Workflow automation (reminders, cron follow-ups) runs on a self-hosted n8n instance.

---

## 2. Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      Patient Channels                        │
│  LiveKit SIP (voice) │  Evolution API (WA)  │  Web webhook  │
└──────────────────────┬──────────────────────────────────────┘
                       │
          ┌────────────┴─────────────┐
          │                          │
          ▼                          ▼
┌──────────────────┐      ┌─────────────────────────────────┐
│  LiveKit Agent   │      │      FastAPI Gateway Layer       │
│  Worker Process  │      │  Adapter → PatientMessage schema │
│  (voice/SIP)     │      │  TLRU agent cache (128, 1hr TTL) │
│  STT→LLM→TTS     │      │  Secret redaction                │
└────────┬─────────┘      └──────────────┬──────────────────┘
         │                               │
         └──────────────┬────────────────┘
                        ▼
┌─────────────────────────────────────────────────────────────┐
│                  LangGraph Orchestrator                       │
│   Intent classification → agent routing                      │
│   State management + checkpointing (PostgreSQL)              │
└──────┬──────────┬──────────┬────────────┬───────────────────┘
       │          │          │            │
       ▼          ▼          ▼            ▼
  Intake     Scheduler  Follow-up    FAQ/Compliance
  Agent       Agent      Agent          Agent
       │          │          │            │
       └──────────┴──────────┴────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────────┐
│               Persistent Memory Layer                        │
│  pgvector semantic recall │ Decay scoring                    │
│  Patient preference profile │ Session history               │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│              Qwen Cloud (Alibaba Cloud ECS)                  │
│  Qwen LLM API │ FastAPI container │ Supabase + pgvector      │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│                  n8n (self-hosted)                           │
│  Reminder sequences │ Follow-up crons │ Tool calls           │
└─────────────────────────────────────────────────────────────┘
```

---

## 3. Tech Stack

| Layer | Technology | Notes |
|---|---|---|
| LLM | Qwen-Plus / Qwen-Turbo (Qwen Cloud API) | All inference; mandatory for hackathon |
| Agent orchestration | LangGraph | State graph, checkpointing, agent routing |
| Voice layer | LiveKit Agents v1.5.x (Python) | Replaces VAPI; WebRTC + SIP, full pipeline control |
| STT | Deepgram Nova-3 (via LiveKit plugin) | 6.84% WER, <300ms, noise robust |
| TTS | ElevenLabs Flash (via LiveKit plugin) | 75ms first-chunk latency |
| Backend | FastAPI (Python 3.12) | Webhook receiver, REST API, tool endpoints |
| Memory store | Supabase + pgvector | Semantic recall, patient profiles, session history |
| Relational DB | PostgreSQL (via Supabase) | Appointments, clinic config, structured data |
| WhatsApp channel | Evolution API | Built on Baileys; webhook delivery to FastAPI |
| Workflow automation | n8n (self-hosted) | Reminders, cron follow-ups, external tool calls |
| Containerisation | Docker | Single-image deployment |
| Cloud infra | Alibaba Cloud ECS | Mandatory per hackathon rules |
| CI/CD | Manual `docker push` to ACR for the hackathon; GitHub Actions is post-hackathon scope | Avoid spending half a day on CI before the submission has a working demo. |

---

## 4. Voice Layer — LiveKit Agents

### 4.1 Why LiveKit over VAPI

VAPI is a managed black box: STT → LLM → TTS happen inside VAPI's infrastructure with no visibility or pipeline control. Every turn incurs two cloud hops (patient → VAPI cloud → FastAPI webhook → Qwen → VAPI cloud → patient). LiveKit gives full ownership of every stage.

Key LiveKit v1.5.x features used in this build:

- **Preemptive generation** — enabled by default; speculatively starts LLM response before end-of-turn is confirmed, shaving 150–300ms off perceived latency
- **Adaptive interruption handling** — trained audio model, 86% precision / 100% recall at 500ms overlap; filters backchannelling so the agent doesn't cut itself off when a patient says "mm-hmm"
- **Dynamic endpointing** — EMA-based adaptive pause detection; tunes turn detection to each patient's speech rhythm
- **Native SIP telephony** — inbound phone calls route directly into LiveKit rooms via SIP trunk; no Twilio bridge required
- **Answering Machine Detection (AMD)** — classifies outbound call answers as human, IVR, voicemail, or unavailable before the agent speaks

### 4.2 Qwen integration with LiveKit

Qwen Cloud exposes an OpenAI-compatible endpoint. LiveKit's OpenAI plugin connects directly:

```python
from livekit.plugins import openai as lk_openai
from livekit.plugins import deepgram, elevenlabs
from livekit.agents import AgentSession, Agent, WorkerOptions, cli

class HealthDeskVoiceAgent(Agent):
    def __init__(self):
        super().__init__(
            instructions=SYSTEM_PROMPT,
            tools=[check_availability, book_appointment, lookup_patient],
        )

async def entrypoint(ctx):
    session = AgentSession(
        llm=lk_openai.LLM(
            model="qwen-plus",
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
            api_key=os.getenv("DASHSCOPE_API_KEY"),
        ),
        stt=deepgram.STT(model="nova-3"),
        tts=elevenlabs.TTS(model="eleven_flash_v2_5"),
    )
    await session.start(ctx.room, agent=HealthDeskVoiceAgent())

if __name__ == "__main__":
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint))
```

### 4.3 SIP telephony setup

LiveKit native SIP replaces VAPI's phone number management:

```bash
# Purchase number or configure SIP trunk in LiveKit dashboard
# Point inbound SIP trunk at LiveKit SIP endpoint
# Agent worker spawns automatically on inbound call room creation
lk sip inbound create --trunk-id <trunk_id>
```

Inbound call flow:
```
Patient dials clinic number
  → SIP trunk → LiveKit SIP endpoint
  → LiveKit room created
  → Agent worker job dispatched
  → AMD check (human vs machine)
  → HealthDeskVoiceAgent joins room
  → STT → Qwen LLM → ElevenLabs TTS pipeline starts
```

### 4.4 Pre-synthesised greeting

Greeting audio is cached at startup to eliminate TTS latency on first contact:

```python
async def on_session_start(session: AgentSession):
    # Pre-synthesised, no TTS call on first word
    await session.say(
        "Hello, you've reached the clinic. How can I help you today?",
        audio=CACHED_GREETING_AUDIO
    )
```

---

## 5. Latency Budget

### 5.1 Per-turn breakdown (voice, LiveKit stack)

| Stage | Estimate | Optimisation applied |
|---|---|---|
| WebRTC audio transport (patient → LiveKit) | 20–50ms | WebRTC ICE, co-located infra |
| Deepgram Nova-3 STT | 80–120ms | Streaming; result arrives before speech ends |
| Preemptive LLM generation start | -150–300ms | Begins before end-of-turn confirmed |
| Qwen-Plus TTFT (intent + response) | 250–500ms* | Qwen-Turbo for intent (~80ms), Plus for response |
| pgvector memory recall | 20–50ms | Warm connection pool; indexed ivfflat |
| ElevenLabs Flash TTS first chunk | 75ms | Flash model, not standard |
| WebRTC audio transport (LiveKit → patient) | 20–50ms | Same room, co-located |
| **Total time-to-first-spoken-word (target)** | **~500ms median, ~800ms p95** | **With preemptive generation; assumes measured Qwen TTFT** |

\* Qwen-Plus TTFT to be measured against the deployed Alibaba region in week 1 and the table updated with actual numbers. The "Should have" list mandates a measurement gate; if measured p50 exceeds 600ms, the demo falls back to a pre-recorded "thinking" filler phrase ("One moment while I check that for you...") to mask the worst spikes.

### 5.2 Latency optimisations

**Single embedding call** — embed the patient's utterance once. The vector drives the pgvector recall query; the *retrieved memory rows* (text) are then concatenated into the LLM prompt as context. One embedding API call serves both the search and the prompt-construction path, eliminating a redundant 100–200ms Qwen embedding call.

**Two-model intent routing** — Qwen-Turbo classifies intent (~80ms TTFT); Qwen-Plus handles reasoning only for the assigned agent. Avoids burning Plus latency on a routing decision.

**Memory recall during STT** — pgvector search fires as soon as partial STT transcript arrives, not after end-of-turn. Results are ready before the LLM call starts.

**Co-location** — LiveKit worker process, FastAPI backend, and Supabase all deployed to the same Alibaba Cloud ECS region as the Qwen Cloud API endpoint. Eliminates cross-region LLM round-trips (saves 40–80ms).

**Cached TTS for common phrases** — confirmation phrases ("I've booked your appointment for...") use pre-synthesised ElevenLabs audio stored in Alibaba Cloud OSS. Skips the TTS API call entirely for predictable outputs.

### 5.2.1 Demonstrating the latency claim

LiveKit Agents emits per-turn timing events (`stt_end`, `llm_first_token`, `tts_first_byte`, `playback_start`). The demo:

1. Subscribes to these events and writes them to a structured log line per turn.
2. A small overlay (`scripts/latency_overlay.py`) tails the log and renders a live "TTFW: 412ms" chip in the demo video's corner via OBS browser source.
3. The README links to `evals/run_latency_probe.py` output so the claim is reproducible, not just asserted on camera.

### 5.3 WhatsApp / web latency (non-voice)

No hard latency requirement. Evolution API webhook → FastAPI → LangGraph → Qwen → response typically completes in 1.5–3s. Patients see a "typing..." indicator. Acceptable for async messaging.

---

## 6. Gateway Layer

### 6.1 Unified message schema

All platform adapters produce a `PatientMessage` before anything touches LangGraph:

```python
class PatientMessage(BaseModel):
    message_id: str
    session_id: str          # platform:chat_id (e.g. "whatsapp:+2348012345678")
    patient_id: str | None   # resolved from memory; None if first contact
    channel: Literal["voice", "whatsapp", "web"]
    content: str
    media_url: str | None    # for voice memos, images
    timestamp: datetime
    platform_meta: dict      # raw platform-specific fields
```

LiveKit voice sessions produce `PatientMessage` via a room event hook:

```python
@session.on("user_speech_committed")
async def on_speech(event):
    msg = PatientMessage(
        session_id=f"voice:{ctx.room.name}",
        channel="voice",
        content=event.transcript,
        ...
    )
    await orchestrator.handle(msg)
```

### 6.2 Agent cache (non-voice channels)

WhatsApp and web sessions use a time-aware LRU cache to avoid cold-starting LangGraph on every message. LiveKit voice sessions are managed by the LiveKit worker process directly.

```python
from cachetools import TLRUCache
from time import monotonic

AGENT_CACHE_MAX_SIZE = 128
AGENT_CACHE_IDLE_TTL = 3600  # 1 hour

# TLRUCache: time-aware LRU. Evicts on (a) idle TTL expiry and (b) least-recently-used
# when full. TTLCache would only evict on TTL, not LRU, which doesn't match the spec.
def _expiry(_key, _value, now):
    return now + AGENT_CACHE_IDLE_TTL

agent_cache: TLRUCache = TLRUCache(
    maxsize=AGENT_CACHE_MAX_SIZE,
    ttu=_expiry,
    timer=monotonic,
)

def get_or_create_agent(session_id: str) -> CompiledGraph:
    if session_id not in agent_cache:
        agent_cache[session_id] = build_agent_graph()
    return agent_cache[session_id]
```

### 6.3 Secret redaction

Applied before any text is sent to a messaging platform:

```python
import re

REDACT_PATTERNS = [
    r"\b\d{9}\b",       # SSN-like
    r"\b\d{16}\b",      # card numbers
    r"Bearer\s+\S+",    # auth tokens
]

def redact_secrets(text: str) -> str:
    for pattern in REDACT_PATTERNS:
        text = re.sub(pattern, "[REDACTED]", text)
    return text
```

### 6.4 Channel endpoints

```
POST /webhook/whatsapp      # Evolution API events
POST /webhook/web           # web chat events
POST /webhook/followup      # n8n post-visit follow-up trigger
POST /n8n/trigger/reminder  # outbound to n8n after booking
GET  /health                # health check for Alibaba Cloud load balancer
```

LiveKit voice does not use a webhook endpoint — the agent worker connects to LiveKit rooms directly via the LiveKit SDK.

---

## 7. LangGraph Orchestrator

### 7.1 State schema

```python
from typing import TypedDict, Annotated
from langgraph.graph.message import add_messages

class AgentState(TypedDict):
    messages: Annotated[list, add_messages]
    patient_id: str | None
    channel: str
    intent: str | None
    active_agent: str | None
    memory_context: list[dict]   # injected from pgvector recall
    appointment_data: dict
    escalate: bool
    checkpoint_id: str | None
```

### 7.2 Intent classification

| Intent | Routed to | Model |
|---|---|---|
| `book_appointment` | Scheduler agent | Qwen-Turbo → Qwen-Plus |
| `reschedule_appointment` | Scheduler agent | Qwen-Turbo → Qwen-Plus |
| `intake_new_patient` | Intake agent | Qwen-Turbo → Qwen-Plus |
| `post_visit_followup` | Follow-up agent | Qwen-Turbo → Qwen-Plus |
| `faq` | FAQ/compliance agent | Qwen-Turbo only |
| `escalate` | Human handoff | — |
| `ambiguous` | Clarification loop | Qwen-Turbo |

### 7.3 Checkpointing

```python
# app/agents/orchestrator.py
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

# from_conn_string is an async context manager; .setup() creates the
# checkpoint/writes tables on first run (idempotent). Call setup() once
# at FastAPI startup, then keep the saver alive for the process lifetime
# via an AsyncExitStack held on app state.
async def build_graph(app_state):
    cm = AsyncPostgresSaver.from_conn_string(settings.DATABASE_URL)
    checkpointer = await app_state.exit_stack.enter_async_context(cm)
    await checkpointer.setup()
    return builder.compile(checkpointer=checkpointer)
```

Allows session resumption on LiveKit disconnects and WhatsApp dropped messages.

---

## 8. Specialist Agents

### 8.1 Intake agent

**Tools:** `lookup_patient`, `create_patient`, `update_patient_profile`  
**Completion condition:** Name, DOB, reason for visit, contact preference collected. Transitions to scheduler.

### 8.2 Scheduler agent

**Tools:** `check_availability`, `book_appointment`, `reschedule_appointment`, `cancel_appointment`  
**Post-booking:** Fires `POST /n8n/trigger/reminder` with `patient_id`, `appointment_id`, `channel`.

### 8.3 Follow-up agent

**Trigger:** n8n cron at 09:00 clinic timezone → `POST /webhook/followup`  
**Tools:** `get_appointment_history`, `send_followup_message`, `log_followup`

### 8.4 FAQ / compliance agent

**Tools:** `search_knowledge_base` (vector similarity on clinic FAQ embeddings), `escalate_to_staff`  
**Escalation condition:** Confidence below 0.75, or query involves prior authorisation, complaints, or clinical advice.  
**Escalation sink (demo).** No real staff exist in the hackathon environment, so `escalate_to_staff` writes a row to `escalations` in Supabase and posts a formatted message to a configured Slack incoming webhook (`STAFF_ESCALATION_WEBHOOK_URL`). The demo video shows the Slack notification firing alongside the patient receiving the "A staff member will follow up by next business day" line. Configurable per clinic in production.

---

## 9. Persistent Memory Layer

### 9.1 Memory schema

```sql
CREATE TABLE patient_memories (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    patient_id TEXT NOT NULL,
    session_id TEXT,
    content TEXT NOT NULL,
    embedding VECTOR(1024),         -- Qwen text-embedding-v3 default output dim
    memory_type TEXT,              -- 'preference' | 'history' | 'clinical_note'
    importance_score FLOAT DEFAULT 1.0,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    last_accessed_at TIMESTAMPTZ,
    access_count INT DEFAULT 0
);

CREATE INDEX ON patient_memories
    USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);
```

### 9.2 Semantic recall (fires during STT, not after)

```python
async def recall_memories(
    patient_id: str,
    query: str,
    top_k: int = 5,
) -> list[dict]:
    # One embedding call powers the pgvector search; the retrieved rows
    # (text) are concatenated into the LLM prompt downstream.
    query_embedding = await embed_once(query)

    # Over-fetch from pgvector (raw cosine), then re-rank with decay scoring
    # so recency / importance / access-frequency shape the final top_k.
    candidates = await supabase.rpc("match_patient_memories", {
        "query_embedding": query_embedding,
        "patient_id": patient_id,
        "match_threshold": 0.75,
        "match_count": top_k * 2,
    })

    reranked = sorted(
        candidates,
        key=lambda m: compute_memory_score(m, m["similarity"]),
        reverse=True,
    )[:top_k]

    # Access bookkeeping is fire-and-forget — never block the hot path.
    asyncio.create_task(
        update_memory_access(ids=[r["id"] for r in reranked])
    )
    return reranked
```

### 9.3 Decay scoring

```python
import math

def compute_memory_score(memory: dict, query_similarity: float) -> float:
    days_old = (now() - memory["created_at"]).days
    recency_score = math.exp(-0.05 * days_old)   # half-life ~14 days
    access_bonus = min(0.2, memory["access_count"] * 0.02)

    return (
        0.5 * query_similarity +
        0.3 * recency_score +
        0.1 * memory["importance_score"] +
        0.1 * access_bonus
    )
```

### 9.4 Memory write-back

Recall is hot-path; writes happen out-of-band so a slow embed never delays a turn.

**Trigger.** Two paths:
1. **Per-turn structured extractions** — after every patient turn, a fast Qwen-Turbo call extracts any *preference* signals ("I prefer mornings", "I drive there from work") and writes them with `memory_type='preference'` and `importance_score=0.8`. Skipped if the extractor returns nothing.
2. **End-of-session summary** — on LiveKit room close or WhatsApp idle > 10 min, Qwen-Plus summarises the session into 1–3 sentences with `memory_type='history'` and `importance_score=0.5`. Clinical-sounding statements ("I have been feeling dizzy") are tagged `memory_type='clinical_note'` with `importance_score=0.9`.

**Importance heuristic.** Set by the extractor/summariser via a constrained schema (`{type, content, importance}`); the LLM picks from `{0.3, 0.5, 0.8, 0.9}` per the rubric above rather than free-form floats. Anything below 0.3 is dropped.

**Async path.** All writes run via `asyncio.create_task` after the turn's response has been sent to the patient. The write coroutine: (a) embeds the content with Qwen text-embedding-v3, (b) inserts into `patient_memories`, (c) logs on failure but never raises into the agent loop.

```python
# voice/healthdesk_agent.py — fires after each user turn
@session.on("agent_speech_committed")
async def _persist_turn(event):
    asyncio.create_task(
        memory.write.extract_and_persist(
            patient_id=state.patient_id,
            session_id=state.session_id,
            user_text=event.user_transcript,
            agent_text=event.response,
        )
    )
```

### 9.5 Patient preference profile

```python
class PatientProfile(BaseModel):
    patient_id: str
    preferred_channel: Literal["voice", "whatsapp", "web"]
    preferred_time_slots: list[str]   # e.g. ["morning", "weekday"]
    language: str
    last_visit_date: date | None
    last_visit_reason: str | None
    recurring_concern: str | None
    notes: str | None
```

---

## 10. n8n Workflow Automation

### 10.1 Post-booking reminder sequence

```
Trigger: POST /n8n/trigger/reminder
  → Wait until T-24hr
    → Send reminder via patient's preferred channel
      → If no confirmation after 2hr → escalate to staff
  → Wait until T-2hr
    → Send final reminder
```

### 10.2 Post-visit follow-up cron

```
Daily cron at 09:00 clinic timezone:
  Query appointments where date = yesterday AND followup_sent = false
  → For each: POST /webhook/followup {patient_id, appointment_id}
```

---

## 11. Qwen Model Selection

| Task | Model | Rationale |
|---|---|---|
| Intent classification | Qwen-Turbo | Fast (~80ms TTFT), cheap, simple prompt |
| Agent reasoning + tool calls | Qwen-Plus | Balance of speed and capability |
| Memory embedding | Qwen text-embedding-v3 | Consistent embedding space across all memories |
| Escalation decisions | Threshold rule + Qwen-Plus | Confidence < 0.75 → escalate directly (no LLM call). Borderline cases (0.6–0.75) go to Qwen-Plus for a yes/no. Qwen-Max removed: the latency cost wasn't justified by the marginal accuracy gain on what is mostly a thresholded decision. |
| Voice pipeline LLM (LiveKit) | Qwen-Plus via OAI-compatible endpoint | Same model, different transport |

---

## 12. Deployment

### 12.1 Alibaba Cloud resources

| Resource | Service |
|---|---|
| Compute | Alibaba Cloud ECS (ecs.c7.large, 2vCPU 4GB) |
| Container registry | Alibaba Cloud Container Registry (ACR) |
| Object storage | Alibaba Cloud OSS (cached TTS audio, media) |
| Load balancer | Alibaba Cloud SLB |
| Database | Supabase self-hosted on ECS, or Supabase Cloud |

**Region selection:** Deploy to the same Alibaba Cloud region as the Qwen Cloud API endpoint. Eliminates cross-region LLM latency (saves 40–80ms per turn).

### 12.2 LiveKit deployment

**Regional alignment (must be verified Week 1).** LiveKit Cloud has no mainland-China region, so the deployment triple will most likely be: LiveKit Cloud Singapore + Alibaba Cloud International ECS Singapore + DashScope International (Singapore). Pre-flight tasks before any voice work begins:

1. Confirm LiveKit Cloud region available to the account; note its latency to ECS Singapore.
2. Confirm DashScope International serves Qwen-Plus + text-embedding-v3 from the same region.
3. Confirm LiveKit Cloud SIP inbound minutes, concurrent participants, and phone-number provisioning are usable on the free/dev tier for the demo window. If SIP is metered above the demo's needs, either budget for paid minutes or accept the WhatsApp-only fallback (§12.5).

The LiveKit agent worker runs as a separate process on the same ECS instance as FastAPI:

```bash
# Start FastAPI
uvicorn app.main:app --host 0.0.0.0 --port 8000 &

# Start LiveKit agent worker
python agent_worker.py start
```

### 12.3 Dockerfile

```dockerfile
FROM python:3.12-slim

WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends supervisor \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .
COPY deploy/supervisord.conf /etc/supervisor/conf.d/healthdesk.conf

EXPOSE 8000

# supervisord manages both processes so signals propagate and a crash in
# either uvicorn or the LiveKit worker terminates the container (and the
# ECS health check restarts it). A backgrounded `&` would silently keep
# the container alive after either child died.
CMD ["/usr/bin/supervisord", "-n", "-c", "/etc/supervisor/supervisord.conf"]
```

```ini
# deploy/supervisord.conf
[supervisord]
nodaemon=true

[program:api]
command=uvicorn app.main:app --host 0.0.0.0 --port 8000
autorestart=true
stdout_logfile=/dev/stdout
stdout_logfile_maxbytes=0
stderr_logfile=/dev/stderr
stderr_logfile_maxbytes=0

[program:voice]
command=python voice/agent_worker.py start
autorestart=true
stdout_logfile=/dev/stdout
stdout_logfile_maxbytes=0
stderr_logfile=/dev/stderr
stderr_logfile_maxbytes=0

[eventlistener:fail-fast]
# If either child enters a fatal state, kill supervisord so the container
# exits non-zero and the orchestrator restarts it.
command=sh -c "printf 'READY\n' && while read -r _; do kill -SIGTERM $PPID; done"
events=PROCESS_STATE_FATAL
```

### 12.4 Environment variables

```
DASHSCOPE_API_KEY=
QWEN_API_BASE=https://dashscope.aliyuncs.com/compatible-mode/v1
DATABASE_URL=postgresql://...
SUPABASE_URL=
SUPABASE_KEY=
LIVEKIT_URL=
LIVEKIT_API_KEY=
LIVEKIT_API_SECRET=
DEEPGRAM_API_KEY=
ELEVENLABS_API_KEY=
EVOLUTION_API_URL=
EVOLUTION_API_KEY=
EVOLUTION_AUTH_MODE=hmac          # or "token" if Evolution build lacks HMAC
N8N_WEBHOOK_URL=
GATEWAY_PROXY_KEY=
STAFF_ESCALATION_WEBHOOK_URL=     # Slack incoming webhook for demo escalation sink
```

### 12.5 Fallback deployment (WhatsApp-only)

Triggered by the Week-1 exit gate in the PRD timeline. If the gate selects WhatsApp-only:

- The `voice/` package is excluded from the container build (`HEALTHDESK_VOICE=off` in the build args; the supervisord `[program:voice]` block is omitted from the rendered config).
- The architecture diagram and submission write-up retain LiveKit as the documented production voice layer; the demo video uses WhatsApp scenarios from PRD §6 (Journeys 1, 3, 4) plus a returning-patient flow via WhatsApp instead of voice.
- DashScope / Supabase / n8n / Evolution API stay unchanged; only the LiveKit dependency is dropped.

---

## 13. Security Considerations

- All patient data in transit: TLS 1.3
- Evolution API webhooks validated via HMAC signature **where supported by the deployed Evolution version**; if HMAC is unavailable (older or community builds), the webhook falls back to a shared-secret header (`X-Evolution-Token`) + IP allowlist on the FastAPI ingress. The handler accepts whichever scheme is configured via env var `EVOLUTION_AUTH_MODE=hmac|token`.
- LiveKit room tokens are short-lived JWTs signed with `LIVEKIT_API_SECRET`
- Secret redaction applied before all platform replies
- Patient IDs are internal UUIDs; phone numbers stored hashed in session_id index
- No real patient data used in demo; all synthetic

---

## 14. Repository Structure

```
healthdesk-ai/
├── app/
│   ├── main.py
│   ├── gateway/
│   │   ├── adapters/
│   │   │   ├── whatsapp.py      # Evolution API adapter
│   │   │   └── web.py
│   │   ├── cache.py             # TLRU agent cache (non-voice)
│   │   ├── redact.py
│   │   └── schema.py            # PatientMessage schema
│   ├── agents/
│   │   ├── orchestrator.py      # LangGraph state graph
│   │   ├── intake.py
│   │   ├── scheduler.py
│   │   ├── followup.py
│   │   └── faq.py
│   ├── memory/
│   │   ├── recall.py
│   │   ├── decay.py
│   │   ├── write.py
│   │   └── profile.py
│   ├── tools/
│   │   ├── calendar.py
│   │   ├── knowledge_base.py
│   │   └── escalation.py
│   └── config.py
├── voice/
│   ├── agent_worker.py          # LiveKit agent worker entry point
│   ├── healthdesk_agent.py      # HealthDeskVoiceAgent class
│   ├── sip_config.py            # SIP trunk setup helpers
│   └── greeting_cache.py        # Pre-synthesised TTS audio
├── n8n/
│   └── workflows/
│       ├── reminder_sequence.json
│       └── followup_cron.json
├── supabase/
│   └── migrations/
│       ├── 001_patients.sql
│       ├── 002_appointments.sql
│       └── 003_memories.sql
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── README.md
```

The `evals/` package (added per §16) sits alongside `app/`:

```
evals/
├── intent_dataset.jsonl       # ~30 labelled cases
├── memory_dataset.jsonl       # ~10 scripted recall scenarios
├── run_intent_eval.py         # measures classification accuracy
├── run_memory_eval.py         # measures recall precision @ k
└── run_latency_probe.py       # measures Qwen-Plus TTFT from deploy region
```

---

## 15. Judging Criteria Alignment

| Criterion | Weight | How this submission addresses it |
|---|---|---|
| Technical depth & engineering | 30% | LiveKit Agents with custom Qwen pipeline, pgvector memory with decay scoring, TLRU session cache, preemptive generation, two-model intent routing, single-embed optimisation |
| Innovation & AI creativity | 30% | Persistent memory with semantic recall + decay is non-trivial at hackathon scale; LiveKit + Qwen voice pipeline is a novel combination; memory-recall-during-STT pattern reduces latency architecturally |
| Problem value & impact | 25% | Healthcare front desk automation has clear ROI; architecture is configurable per clinic and designed for multi-tenant productisation |
| Presentation & documentation | 15% | Architecture diagram in submission, 3-min demo showing returning patient recognition, this TRD as supplementary doc, open-source repo with MIT licence |

---

## 16. Evaluation

The submission backs the "production-grade" claim with three small, automatable evals run from `evals/`. None of them gate the demo, but the numbers go in the README and the submission write-up.

### 16.1 Intent classification accuracy

- **Dataset** — `evals/intent_dataset.jsonl`, ~30 hand-labelled utterances spanning the seven intents in §7.2 (book / reschedule / intake / followup / faq / escalate / ambiguous), drawn from the user journeys in PRD §6 plus adversarial cases ("My kid has a fever and I want to know if you take Aetna" — mixed intent).
- **Metric** — top-1 accuracy and per-class precision/recall.
- **Pass bar** — ≥ 85% top-1 with Qwen-Turbo classifier; below that, refine the prompt or add few-shot examples before submission.

### 16.2 Memory recall precision @ k

- **Dataset** — `evals/memory_dataset.jsonl`, ~10 scripted patient histories with seeded memories (preferences, prior visits) and a follow-up query per scenario annotated with the *expected* memory IDs to surface.
- **Metric** — precision@5 (does the top-5 contain every expected memory ID?) and a qualitative check that decay scoring promotes recent / important memories over older near-duplicates.
- **Pass bar** — ≥ 80% precision@5 across the 10 scenarios.

### 16.3 Latency probe

- `evals/run_latency_probe.py` issues 50 small Qwen-Plus completions from the deployed ECS region and reports p50 / p95 TTFT and tokens/sec. This is the source of truth for the §5.1 budget; numbers updated in the TRD whenever the probe is re-run.

Evals are wired into a `make eval` target. CI integration (GitHub Actions) is explicitly out of scope for the hackathon submission — see §3 — and is post-hackathon work.
