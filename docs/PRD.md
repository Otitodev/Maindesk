# Product Requirements Document — HealthDesk AI

**Version:** 2.0  
**Date:** June 9, 2026  
**Author:** Otito Ogene  
**Submission:** Global AI Hackathon Series with Qwen Cloud — Track 4: Autopilot Agent

> **Post-submission update:** the voice layer described below (LiveKit Agents + native SIP) was replaced with **Pipecat + Twilio Media Streams**. See `docs/GATEWAYS_SETUP.md` §2 for current setup steps. The rest of this document still reflects the live system.

---

## 1. Overview

HealthDesk AI is a production-grade, multi-channel autonomous front desk agent for healthcare clinics. It handles patient intake, appointment scheduling, post-visit follow-up, and FAQ resolution across voice, WhatsApp, and web — without human intervention at each step. The system remembers patients across sessions, personalises each interaction based on prior history, and escalates to staff only when genuinely necessary.

The voice channel is powered by LiveKit Agents v1.5.x — an open-source WebRTC framework that gives full control over the STT → LLM → TTS pipeline, targeting sub-500ms time-to-first-spoken-word with preemptive generation enabled by default. All LLM inference runs on Qwen via Alibaba Cloud, satisfying the hackathon's mandatory deployment requirement.

The core thesis: the average healthcare clinic wastes 2–4 staff hours per day on repetitive front desk tasks — booking confirmations, reminders, repeat FAQs, and insurance queries. HealthDesk AI automates this end-to-end. The build is designed with PHI handling in mind (TLS in transit, secret redaction, no real patient data in the demo); production HIPAA infrastructure (BAAs, audit logging, encryption-at-rest controls) is explicitly out of scope for the hackathon submission.

---

## 2. Problem Statement

Healthcare front desks operate the same way they did 20 years ago: a phone rings, a staff member answers, asks the patient the same questions they answered last time, books an appointment in a calendar, and sends a manual reminder the day before. This is:

- **Expensive** — front desk staff cost $15–22/hr and spend the majority of their time on tasks that do not require human judgment
- **Error-prone** — double bookings, missed reminders, and incorrect intake information are common
- **Inaccessible** — patients outside business hours get voicemail; WhatsApp and web chat go unanswered
- **Amnesiac** — every interaction starts from zero; the system remembers nothing about the patient

HealthDesk AI solves all four with a single deployed agent that remembers, reasons, and acts.

---

## 3. Target Users

| User | Description |
|---|---|
| Clinic administrator | Configures the agent, sets business hours, manages escalation rules |
| Front desk staff | Receives escalations, reviews agent activity dashboard |
| Patient | Interacts via voice call, WhatsApp, or web chat |

**Primary hackathon demo persona:** a returning patient calling to reschedule an appointment. The agent recognises them, recalls their last visit, confirms their preference for morning slots, and books without asking questions they've already answered.

---

## 4. Goals

### Must have (MVP — hackathon submission)

- Multi-channel entry: voice (LiveKit + SIP), WhatsApp (Evolution API), web chat webhook
- Sub-500ms voice latency with LiveKit preemptive generation + Deepgram STT + ElevenLabs Flash TTS
- Persistent patient memory: semantic recall across sessions using pgvector + decay scoring
- Four specialist agents: intake, scheduler, follow-up, FAQ/compliance
- LangGraph orchestration with stateful checkpointing
- Post-booking reminder sequence via n8n (T-24hr + T-2hr)
- Human escalation path with holding message to patient
- Full deployment on Alibaba Cloud ECS (Qwen Cloud infrastructure)
- Architecture diagram, demo video, open-source repository with MIT licence

### Should have

- Pre-synthesised greeting audio cached at agent startup (eliminates TTS latency on first contact)
- Memory recall during STT streaming (not after end-of-turn)
- Two-model intent routing (Qwen-Turbo for classification, Qwen-Plus for reasoning)
- Patient preference profile (channel preference, language, appointment history)
- Answering Machine Detection (AMD) on outbound calls
- Secret redaction before all platform replies

### Will not have (post-hackathon)

- EHR / EMR integration
- Insurance verification API
- HIPAA Business Associate Agreement infrastructure
- Multi-clinic / multi-tenant deployment
- Billing and payment handling

---

## 5. Voice Channel — LiveKit vs VAPI Decision

The original design used VAPI. This has been updated to LiveKit Agents for the following reasons:

**Latency control** — VAPI is a managed black box with no pipeline visibility. LiveKit exposes each stage (STT, LLM, TTS) as a configurable plugin. With preemptive generation, dynamic endpointing, and co-located infrastructure, target latency drops from 1.1–2.3s (VAPI) to 300–500ms (LiveKit).

**Qwen-native integration** — LiveKit's OpenAI plugin accepts a custom `base_url`, pointing directly at Qwen Cloud's OpenAI-compatible endpoint. The entire pipeline — STT (Deepgram), LLM (Qwen-Plus), TTS (ElevenLabs Flash) — runs through LiveKit with Qwen as the reasoning core.

**Judging alignment** — the judges score "sophisticated use of QwenCloud APIs" and "engineering innovation." A custom LiveKit voice pipeline wired to Qwen Cloud scores significantly higher on technical depth than a VAPI webhook configuration.

**Native SIP telephony** — LiveKit shipped native SIP and phone number management in 2025, removing the need for a Twilio bridge for inbound calls.

**Fallback position** — if LiveKit integration runs long in Week 1, the demo uses WhatsApp (Evolution API) which is already production-proven from Whaply. The TRD documents LiveKit as the full production architecture regardless.

---

## 6. User Journeys

### Journey 1 — New patient, first contact via WhatsApp

1. Patient sends "Hi, I'd like to book an appointment"
2. Evolution API delivers webhook to FastAPI
3. LRU cache misses → new LangGraph session created
4. Orchestrator classifies intent → routes to intake agent
5. Intake agent collects: name, DOB, reason for visit, preferred channel
6. Scheduler agent checks availability and confirms booking
7. Confirmation sent back via WhatsApp
8. n8n triggers 24hr reminder workflow
9. Interaction + preferences written to patient memory store

### Journey 2 — Returning patient, voice call (primary demo scenario)

1. Patient calls clinic SIP number
2. LiveKit SIP trunk routes call into a room; agent worker spawns
3. AMD confirms human caller; pre-synthesised greeting plays instantly
4. Phone number resolves to a household record. If exactly one patient is registered on that line → use them. If multiple (family plan) → agent asks "Who am I speaking with — [Name A] or [Name B]?" before any personalised recall is read aloud, so we never leak one family member's history to another.
5. Memory recalled for the confirmed patient (last visit, preferences).
6. Agent: "Hi [Name], I see you came in for a check-up in April — is this a follow-up?"
7. Patient requests morning slot; scheduler books
8. Confirmation sent via patient's preferred channel (from preference profile)
9. Memory updated: new appointment, any new preferences mentioned

### Journey 3 — After-hours FAQ via web

1. Patient submits: "Do you accept Aetna insurance?"
2. FAQ agent searches clinic knowledge base (vector similarity)
3. High confidence match → answer returned directly
4. Low confidence or complex query (prior auth, complaints) → escalation flagged
5. Patient receives: "A staff member will follow up by next business day"
6. Interaction logged; no appointment created

### Journey 4 — Post-visit follow-up

1. n8n cron fires at 09:00 day after appointment
2. Follow-up agent triggers: satisfaction check + refill prompt + rebooking nudge
3. Patient responses written back to memory
4. `followup_sent = true` set on appointment record

---

## 7. Non-Functional Requirements

| Requirement | Target |
|---|---|
| Voice time-to-first-spoken-word | ~500ms median / ~800ms p95 (with preemptive generation; pending Week-1 Qwen TTFT measurement) |
| WhatsApp response time | < 3s |
| Memory recall latency | < 50ms (warm pgvector connection) |
| Agent cache size | 128 concurrent sessions (time-aware LRU, 1hr idle TTL) |
| Uptime target (demo period) | 99% |
| Concurrent voice calls | 5–15 per ecs.c7.large; scale by upsizing the instance (each LiveKit worker holds a persistent asyncio task with bidirectional audio + streaming STT/LLM/TTS) |

---

## 8. Success Metrics (demo)

| Metric | Target |
|---|---|
| Returning patient recognised without re-asking details | 100% of demo scenarios |
| Booking completed end-to-end without human touch | < 60 seconds on voice |
| Voice agent responds within 500ms | Demonstrated with LiveKit latency metrics |
| Correct escalation on ambiguous input | Demonstrated in at least 1 scenario |
| Reminder sequence triggered post-booking | Visible in n8n execution log |
| Memory write-back after interaction | Verifiable in Supabase dashboard |

---

## 9. Out of Scope

- Real patient data — all demo data is synthetic
- Production HIPAA compliance infrastructure
- Live calendar system integration (demo uses mock calendar tool)
- Mobile application

---

## 10. Risks

| Risk | Mitigation |
|---|---|
| LiveKit SIP setup takes longer than estimated | Fall back to WhatsApp-only demo; document voice as production architecture |
| Qwen-Plus TTFT spikes under load | Route complex turns to Qwen-Plus, simple intent classification to Qwen-Turbo; cache common responses |
| pgvector recall returns stale context | Decay scoring + 0.75 similarity threshold filters low-quality memories |
| WhatsApp session drops mid-conversation | Evolution API handles reconnection; LangGraph checkpoint preserves state |
| Alibaba Cloud deployment unfamiliar | Docker container is cloud-agnostic; same image used locally and on ECS |

---

## 11. Timeline

| Week | Milestone | Exit gate |
|---|---|---|
| Week 1 | Evolution API WhatsApp webhook + FastAPI gateway + unified `PatientMessage` schema + Qwen-Plus loop end-to-end (text only). **In parallel:** LiveKit Cloud + DashScope region verification, SIP trunk feasibility, real Qwen-Plus TTFT measurement from chosen region. | End-of-week decision gate: **voice in or out?** A working WhatsApp loop must demo before voice work continues. If LiveKit/SIP/region/TTFT verification is incomplete or measured TTFT > 600ms p50, commit to WhatsApp-only as the primary demo and document voice as future architecture. **Do not revisit this decision in weeks 2–4.** |
| Week 2 | LangGraph orchestrator, four specialist agents, two-model intent routing, tool registry. If voice is in: LiveKit agent worker + greeting cache. | All four agents callable from a single WhatsApp test session; intent routing measured on a small labelled eval set (see §16 of TRD). |
| Week 3 | Memory layer (pgvector, decay re-rank, write-back, preference profile, recall-during-STT), n8n reminder sequence + follow-up cron. | Returning-patient recognition demo works end-to-end on WhatsApp; reminder fires in n8n execution log. |
| Week 4 | Alibaba Cloud ECS deployment, latency tuning, demo recording (returning patient scenario), README, architecture diagram, submission. | Submitted ≥ 24h before the deadline. |

**Submission deadline:** July 9, 2026
