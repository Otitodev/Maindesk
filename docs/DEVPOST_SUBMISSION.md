# Devpost submission draft — copy into the submission form

Standard Devpost project fields. Fill in the video URL and repo URL once you have them; everything else is ready to paste as-is. Track: **Track 4 — Autopilot Agent.**

---

## Tagline

MainDesk is the AI-native front desk that answers every patient message — WhatsApp, email, web, and voice — books real appointments, and knows when to hand off to a human.

---

## Inspiration

Small clinics lose patients to voicemail. A solo GP or a 2–8 clinician practice pays $30–50k/year for a receptionist and still misses ~15% of after-hours contacts, because patients don't stay on one channel — they call, then WhatsApp, then email the same question. Every "AI receptionist" we looked at was either a single-channel chatbot, a voice-only IVR that still routes to a human, or a generic LLM wrapper with no clinic-specific grounding — it invents hours, invents insurance policies, and never knows when to stop and ask for help. We built MainDesk to be the thing that actually replaces the receptionist, not a demo of one.

## What it does

One LangGraph orchestrator sits behind every channel a patient might use — WhatsApp, email, the web chat widget, and voice (both a real phone number over Twilio and a self-hosted, no-download browser call widget) — so the same brain handles a booking request whether it arrives as a text message or a live phone call. It:

- **Books real appointments** — real slot-finding, real double-booking guards, real Google Calendar mirroring (falls back to a local Postgres scheduler if Calendar isn't configured).
- **Remembers patients across channels and sessions.** Decay-weighted pgvector recall means a preference mentioned over WhatsApp in May surfaces unprompted during a phone call in July.
- **Replies in the patient's own language**, detected per-message — not just prompted to, actually classified and routed.
- **Refuses to hallucinate clinic facts.** Hours, prices, doctor names — if it isn't in the clinic's configured knowledge base, the agent says "let me check" instead of inventing an answer.
- **Knows when to stop and ask a human.** Chest pain, an angry patient, anything ambiguous — it escalates to a live `/staff` dashboard (HTMX + server-sent events, no polling) instead of pretending to have an answer, and the staff reply routes back to the patient on whatever channel they used.
- **Configures in minutes, not a support ticket.** A self-serve `/onboarding` wizard sets clinic hours, persona, and FAQs, applied live with no restart.
- **Exposes the same tools to MCP clients** (Claude Desktop, Cursor) for staff who'd rather manage the schedule from their own AI assistant.

## How we built it

- **Reasoning**: Qwen-Plus (`qwen3.7-plus`) via DashScope's OpenAI-compatible endpoint for response generation; Qwen-Turbo (`qwen3.6-flash`) as a cheap intent + language classifier in front of it.
- **Orchestration**: LangGraph, checkpointed to Postgres via `AsyncPostgresSaver` so multi-turn conversations survive a restart.
- **Memory**: Qwen `text-embedding-v4` into pgvector (ivfflat, cosine), with a decay-weighted re-ranker so recent context outweighs old.
- **Voice**: Pipecat, running in-process as FastAPI routes — no separate worker process. Two transports share one pipeline: Twilio Media Streams for real phone calls, and a self-hosted WebRTC widget (`aiortc`, no third-party vendor) for browser calls. Deepgram Nova-3 for STT, ElevenLabs Flash v2.5 for TTS.
- **Gateway**: FastAPI, async single process, with HMAC/token webhook auth and outbound secret redaction on every reply.
- **Deployment**: Docker on Alibaba Cloud ECS (Singapore), behind Caddy for TLS, deployed via GitHub Actions on every push to `main`.

## Challenges we ran into

The voice channel was originally built on LiveKit Agents. We migrated it to Pipecat + Twilio mid-project — same STT/TTS/LLM providers, but a genuinely different frame-based pipeline architecture, and it forced us to also drop the separate voice worker process entirely (voice now runs in-process alongside the gateway, which simplified the whole deployment). Along the way we added a second, phone-free way into voice — a browser call widget — since once voice was decoupled from a specific telephony vendor, adding a WebRTC transport alongside Twilio was a small, natural extension rather than a rewrite.

We also learned not to trust "it's probably fine" about test infrastructure: partway through, we discovered our local Postgres volume predated two schema migrations (so dashboard/config features silently looked broken locally, for reasons that had nothing to do with the code), and that our own intent-eval script couldn't run on Windows because of a missing UTF-8 encoding flag — which meant the three Mandarin test cases had never actually been verified since they were added. Fixed both; the eval now genuinely re-runs and reports real numbers instead of a stale, unverifiable claim.

## Accomplishments that we're proud of

- Three of four patient-facing gateways verified live in production right now — including voice, twice over (phone **and** browser widget).
- 217 automated tests passing; 32/33 (97%) on the intent-classification eval, including all 3 Mandarin cases, against live Qwen — not a cached or synthetic result.
- A human-in-the-loop escalation that actually closes the loop: patient message → agent defers → staff dashboard updates via SSE in real time → staff reply routes back to the patient on their original channel.
- Cross-channel, cross-session memory that surfaces unprompted, not on request.
- A voice pipeline that's provider-agnostic enough that we swapped its entire telephony layer mid-project without touching the booking logic, the memory layer, or the escalation path.

## What we learned

That "channel-agnostic" only means something if the tool layer really is shared — the moment booking or escalation logic diverges between voice and text, the product stops being one front desk and becomes several bots wearing a trenchcoat. Keeping every channel behind the exact same LangGraph orchestrator and the exact same `app/tools/*` functions was the discipline that made the memory and escalation demos actually work the same way everywhere, instead of mostly.

## What's next

Multi-tenant self-serve signup (today it's one deployment per clinic), a signed HIPAA BAA for regulated US healthcare, EHR integrations (Epic/Cerner/Athena), and multi-location routing for clinic groups. On the Qwen Cloud side specifically: voice STT/TTS currently run on Deepgram/ElevenLabs — DashScope's own Paraformer (ASR) and CosyVoice (TTS) are on the roadmap to make the entire voice stack, not just the reasoning layer, fully Qwen-native.

---

## Submission checklist (fill in before hitting submit)

- [ ] Video URL (YouTube/Vimeo/Facebook, public): ___________
- [ ] Repo URL: https://github.com/Otitodev/healthdesk-ai
- [ ] Live demo URL: https://maindesk.otito.site
- [ ] Track: Track 4 — Autopilot Agent
- [ ] Proof of Alibaba Cloud deployment — link this doc's live URL above; consider attaching an ECS console screenshot as backup
- [ ] Architecture diagram — `docs/architecture.png` (re-export from `docs/architecture.mmd` before attaching — the committed PNG is stale)
