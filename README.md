# HealthDesk AI

Multi-channel autonomous front-desk agent for clinics — LiveKit voice, WhatsApp (Evolution API), web chat — backed by Qwen-Plus reasoning, Qwen-Turbo intent routing, LangGraph orchestration, and pgvector memory with decay-aware re-ranking.

Hackathon entry for Qwen Cloud Track 4. See `../Qwen_prd.md` and `../Qwen_trd.md`.

## Architecture (at a glance)

```
WhatsApp / Web / LiveKit voice
        │
        ▼
   FastAPI gateway  ──►  redact()  ──►  reply to platform
        │
        ▼
   LangGraph: triage → recall → tools → reasoner → writer
                                              │
                                              ▼
                                       Postgres + pgvector
```

- **Voice:** LiveKit Agents (Deepgram Nova-3 STT, Qwen-Plus, ElevenLabs Flash TTS)
- **Reasoning:** Qwen-Plus via DashScope OpenAI-compatible endpoint
- **Intent routing:** Qwen-Turbo classifier
- **Memory:** Qwen `text-embedding-v3` @ 1024d, pgvector ivfflat cosine, decay re-rank
- **Crons:** n8n hourly reminders + 6-hourly follow-ups
- **Deploy:** single container, gateway + voice worker under supervisord; Alibaba Cloud ECS (Singapore)

## Quick start

```bash
cp .env.example .env
# fill in QWEN_API_KEY at minimum
docker compose up --build
```

Then:
- Health: `curl localhost:8000/health`
- Web webhook: `POST localhost:8000/webhooks/web` with `{"session_id": "abc", "content": "Hi"}`
- WhatsApp webhook: `POST localhost:8000/webhooks/whatsapp` (Evolution API)
- n8n: open `localhost:5678` and import `n8n/*.json`

## Repo layout

```
app/
  main.py                  FastAPI entrypoint + lifespan
  config.py                Pydantic Settings
  gateway/
    schema.py              PatientMessage / PatientReply
    cache.py               TLRUCache session cache
    redact.py              Outbound secret redaction
    adapters/whatsapp.py   Evolution API webhook (HMAC or token+IP)
    adapters/web.py        Browser webhook
  agents/
    orchestrator.py        LangGraph wiring + AsyncPostgresSaver
    triage.py              Qwen-Turbo intent classifier
    recall.py              Memory recall node
    tools_node.py          Dispatches to app.tools.*
    reasoner.py            Qwen-Plus reply synthesis
    writer.py              Fire-and-forget memory write-back
    qwen_client.py         OpenAI-compatible DashScope client
    state.py               Shared LangGraph AgentState
  memory/
    db.py                  asyncpg pool
    score.py               decay-aware ranking
    recall.py              top-k×2 + re-rank pipeline
    write.py               summarise + insert + embed
    profile.py             patient profile resolve/upsert
  tools/
    appointments.py        slot suggestions, booking, lookup
    escalation.py          Slack webhook for hackathon demo
  voice/
    agent_worker.py        LiveKit Agents worker
supabase/migrations/
  0001_init.sql            pgvector(1024), patients, memories, appointments
n8n/
  reminder_cron.json       hourly reminders
  followup_cron.json       6-hourly post-visit follow-ups
evals/
  intent_cases.jsonl       30 labelled intent cases
  run_intent_eval.py       eval harness
  memory_recall_cases.json 10 scripted recall scenarios
deploy/
  supervisord.conf         gateway + voice supervisor
Dockerfile                 supervisord-based image
docker-compose.yml         app + postgres(pgvector) + n8n
```

## Notes

- **No real patient data.** Synthetic data only; PHI handling considered but HIPAA infrastructure is out of scope for the hackathon.
- **Secret redaction.** Every outbound reply is passed through `gateway.redact.redact()` before reaching the platform adapter.
- **Webhook auth.** WhatsApp webhooks support HMAC (`X-Hub-Signature-256`) or shared-secret token + IP allowlist, switched via `EVOLUTION_AUTH_MODE`.
- **Voice as a flag.** `HEALTHDESK_VOICE=false` keeps the WhatsApp + web build running standalone if LiveKit Cloud SIP is blocked (see PRD §11 Week-1 exit gate).
