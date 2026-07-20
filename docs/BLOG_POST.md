---
title: "One agent, five channels: notes from building on Qwen Cloud"
published: false
tags: qwen, langgraph, hackathon, ai
canonical_url: https://dev.to/otito/one-agent-five-channels
description: What I learned building a multilingual clinic front-desk agent for the Qwen Cloud hackathon — the gotchas, the design bet, the demo that works.
---

A patient sent us a WhatsApp message at 8:47 PM:

> "Ive had crushing chest pain for an hour what do I do"

Two things happened in about 400 milliseconds. The agent — a LangGraph state machine running behind FastAPI, hitting `qwen3.7-plus` through DashScope's OpenAI-compatible endpoint — classified the intent as `escalate`, cut off its own reply generation, and posted a red card to a human-in-the-loop queue at `/staff`. The patient got a short "One moment while I get a human on this" acknowledgment. The clinician on-call picked up the card, typed "Please go to the ER now, call us from there," and it landed in the same WhatsApp thread inside a second.

That's the demo I've spent the last week building for the [Qwen Cloud Hackathon](https://qwencloud-hackathon.devpost.com/) Track 4. This post is the *interesting* bits — not the boilerplate.

## What MainDesk actually is

A clinic's autonomous front desk that answers on **every channel a patient might use** — WhatsApp, email, web chat, browser voice, and a dedicated `/chat` widget — in English or Mandarin, all day. Books appointments against real Google Calendar free/busy. Escalates to a human dashboard when the model's confidence dips below `0.45` or the intent looks medical-urgent.

The whole thing runs on a **$32/month Alibaba Cloud ECS box** in Singapore, with TLS via Let's Encrypt at [maindesk.otito.site](https://maindesk.otito.site/chat). Try `你好，我想预约下周二的检查` in the widget — it works, and it comes back in Mandarin with real appointment slots.

Code: [github.com/Otitodev/healthdesk-ai](https://github.com/Otitodev/healthdesk-ai).

Now, the interesting bits.

## The Qwen Cloud gotcha that cost me an hour

Every DashScope tutorial on the internet shows the same snippet:

```python
client = OpenAI(
    api_key=os.getenv("DASHSCOPE_API_KEY"),
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1"
)
```

Two things are wrong for a Qwen Cloud workspace (as opposed to legacy Model Studio):

1. **Endpoint**: it's `dashscope-intl.aliyuncs.com`, not `dashscope`. The mainland endpoint returns `401 invalid_api_key` on international workspace keys with a confusingly-worded error. Took me 20 minutes to catch the `-intl` in the actual docs.
2. **Model IDs**: `qwen-plus` and `qwen-turbo` still work as legacy aliases, but the current-generation family the docs actively promote are `qwen3.7-plus` (balanced), `qwen3.7-max` (heavy reasoning), and `qwen3.6-flash` (fast + cheap). Embedding bumped from `text-embedding-v3` → `text-embedding-v4` too, which quietly added new supported dimensions (128, 256, 1536, 2048).

If you're building on Qwen Cloud right now, the config that actually works:

```python
# app/config.py
dashscope_api_key: str = ""
qwen_api_base: str = "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
qwen_model_plus:  str = "qwen3.7-plus"
qwen_model_turbo: str = "qwen3.6-flash"
qwen_embed_model: str = "text-embedding-v4"
qwen_embed_dim:   int = 1024
```

Yes, the env var is `DASHSCOPE_API_KEY` — the *platform* is called Qwen Cloud but the auth header inherits the DashScope name. I named my pydantic field `dashscope_api_key` to match the docs' convention, and the code started reading like it was written **for** Qwen Cloud rather than adapted to it. Small thing, matters when judges read your repo.

## One orchestrator, five gateways

The design bet was: **all five channels go through the same LangGraph orchestrator, the same tool layer, the same pgvector memory, the same secret redactor.** No per-channel business logic beyond parsing.

WhatsApp adapter, email adapter, web adapter, voice adapter — each is ~30 lines. They normalize their inbound payload into a `{session_id, content, phone}` triple and shove it into:

```python
result = await graph.ainvoke(
    {"messages": [HumanMessage(content=text)], "session_id": sid, "phone": phone},
    config={"configurable": {"thread_id": sid}},
)
```

Everything after that — triage, memory recall, tool calls, response generation, outbound secret redaction — runs identically across channels. The Chinese message that just booked an appointment in the web widget exercises exactly the same code path as a Nigerian patient's voice call — whether they dialed the clinic's number or clicked to call from a browser tab.

**The parity is not aesthetic; it's the point.** It means the HITL escalation works the same way for every channel. It means recall of "this patient is allergic to penicillin" surfaces whether they're on voice or email. It means when I ship a new tool — say, a "reschedule" — it works everywhere at once.

The `AsyncPostgresSaver` checkpointer sits behind it all so multi-turn conversations survive process restarts. When the container crash-loops (which it did for real during my Alibaba deployment adventures — long story, in `docs/DEPLOY_ALIBABA_ECS.md`), no conversation state is lost.

## The multilingual recall thing

pgvector, `text-embedding-v4` at 1024 dimensions, with a decay-weighted re-ranker:

```sql
SELECT content, importance,
       (1 - (embedding <=> $1)) AS similarity,
       importance * exp(-0.05 * days_old) AS recency_weight
FROM memories
WHERE patient_id = $2
ORDER BY (similarity * recency_weight) DESC
LIMIT 5;
```

The multilingual part is free — the embedding model handles it. `患者对青霉素过敏` (patient is allergic to penicillin) and `Patient is penicillin-allergic` land in the same vector neighborhood, so a Mandarin patient's memory retrieved for an English message just... works. Zero language routing, zero translation step.

## What surprised me

- **`qwen3.7-plus` speaks fluent Mandarin without a single locale prompt.** The demo booking flow returns properly formatted Chinese dates (`2026年7月3日 上午 9:00`) unprompted. I have exactly zero Chinese in the system prompt.
- **The full booking round-trip is two LLM calls, not one.** Triage → recall → tool → generate. Cold-start ~8s, warm ~5–6s. If you want sub-3-second replies, you have to route triage to the Flash model.
- **Alibaba Cloud CLI's `--output json` flag is table-only.** JSON is the default. I lost 15 minutes to `bad flag format --output with field cols= required`. Every CLI on Earth has `--output json`; this one has it *inverted*. Log this in your muscle memory.

## The stack, if you're grepping

- **Orchestrator**: LangGraph 1.2 + `AsyncPostgresSaver` checkpoints
- **LLM**: `qwen3.7-plus` for generation, `qwen3.6-flash` for classification, via DashScope OpenAI-compatible endpoint
- **Embeddings**: `text-embedding-v4` at 1024 dims into pgvector on Postgres 16
- **Voice**: Pipecat (Twilio phone + a self-hosted browser call widget) with `qwen3.7-plus` LLM + Deepgram STT + ElevenLabs TTS
- **Ingress**: FastAPI + slowapi rate limiter + Caddy 2 TLS reverse proxy
- **Deployment**: Docker Compose on Alibaba Cloud ECS `ecs.e-c1m2.large` in Singapore
- **Human-in-loop**: FastAPI + HTMX + SSE dashboard at `/staff`
- **Tests**: 215 passing, plus a 33-case intent eval that includes three Mandarin cases

Six containers of complexity, ~7,200 lines of Python, one weekend's worth of Alibaba Cloud console clicks, and a small amount of yelling at PowerShell's argument parser.

## If you're building on Qwen Cloud too

Two things I'd tell past-me:

1. **Read `docs.qwencloud.com/developer-guides/getting-started/introduction` first.** That one page has the endpoint, the env var, and the model IDs. My code originally had all three wrong because I'd read old DashScope tutorials that predated the Qwen Cloud rebrand.
2. **Don't roll your own agent loop.** LangGraph + the OpenAI SDK do 90% of it out of the box. The interesting engineering is in the *tools* (the calendar, the memory, the redactor) and the *escape hatches* (HITL, confidence thresholds), not in re-implementing what LangGraph already ships.

That's the build.

- Repo: [github.com/Otitodev/healthdesk-ai](https://github.com/Otitodev/healthdesk-ai)
- Live demo: [maindesk.otito.site/chat](https://maindesk.otito.site/chat)
- Docs: [DEPLOY_ALIBABA_ECS.md](https://github.com/Otitodev/healthdesk-ai/blob/main/docs/DEPLOY_ALIBABA_ECS.md), [DEMO_SCRIPT.md](https://github.com/Otitodev/healthdesk-ai/blob/main/docs/DEMO_SCRIPT.md)

Questions in the comments. If you're grinding on the hackathon too, good luck — submissions close July 9.
