# HealthDesk AI — Hackathon Improvement Plan

Targeted improvements to maximise the score across the QwenCloud Hackathon
judging criteria before the **July 8, 2026** submission deadline.

Judging weights: Technical Depth & Engineering 30% · Innovation & AI Creativity 30% · Problem Value & Impact 25% · Presentation & Documentation 15%

---

## Tier 1 — Directly Addresses Judging Criteria

### 1. Custom MCP Server
The hackathon rules explicitly name *"custom skills, MCP integrations"* as an
example of Technical Depth. A HealthDesk MCP server that exposes clinic tools
to any MCP-compatible client (Claude Desktop, Cursor, etc.) is a direct
checkbox for the 30% Technical Depth criterion.

**Tools to expose:**
- `suggest_slots` — next available 30-min slots in clinic timezone
- `book_appointment` — insert a booking with double-booking guard
- `lookup_patient` — resolve patient profile by phone
- `get_appointment_history` — upcoming and past appointments
- `escalate_to_staff` — page on-call staff with reason + context

**Files to create:**
```
app/mcp/
  server.py      FastMCP server wiring all five tools
  __init__.py
```

**Why it wins points:** Makes the project composable, open-sourceable in a
meaningful way, and directly satisfies the MCP integration criterion that
judges are explicitly told to look for.

---

### 2. Human-in-the-Loop Staff Dashboard
Track 4's exact brief: *"incorporating human-in-the-loop checkpoints at
critical decision points."* Currently escalation fires a Slack webhook and
disappears. A minimal FastAPI-served dashboard closes the loop.

**Features:**
- Live escalation queue with patient name, session channel, reason, and message preview
- Pending bookings awaiting staff confirmation (high-stakes slots)
- One-click: Approve / Redirect to doctor / Close with note
- WebSocket or SSE push so the page updates without polling

**Files to create:**
```
app/dashboard/
  router.py      FastAPI router mounted at /staff
  templates/
    index.html   HTMX-powered single-page dashboard
```

**Why it wins points:** Directly proves the human-in-the-loop requirement.
Most competitors will claim it; this one demonstrates it.

---

### 3. Multilingual Support
Qwen is Alibaba's model and is exceptionally strong at Arabic, Mandarin,
Malay, French, Yoruba, and other non-English languages. Auto-detecting the
patient's language and replying in kind:

- Is on-brand for an Alibaba hackathon
- Demonstrates global-market thinking (clinics serving immigrant communities)
- Differentiates from almost every other Track 4 entry

**Implementation:**
- Add a `language` field to `AgentState`
- In `triage_node`, ask Qwen-Turbo to detect language alongside intent
  (`{"intent": "...", "confidence": 0.9, "language": "ar"}`)
- Pass detected language to `reasoner_node` via system prompt:
  *"Respond in Arabic."*
- Voice agent: pass language hint to ElevenLabs TTS voice selection

**Files to change:** `app/agents/triage.py`, `app/agents/state.py`,
`app/agents/reasoner.py`, `app/voice/agent_worker.py`

---

### 4. Published Eval Results
The eval harness (`evals/run_intent_eval.py`) exists but results are not
committed. Judges evaluating Technical Depth want evidence, not claims.

**Target table to add to README:**

| Component | Metric | Result |
|---|---|---|
| Qwen-Turbo intent classifier | Accuracy on 30 labelled cases | TBD |
| End-to-end booking flow | Success rate | TBD |
| Memory recall | Precision@3 on 10 scenarios | TBD |
| Triage latency | p50 / p95 | TBD |

**Files to update:** `evals/run_intent_eval.py` (fix any issues, add timing),
`evals/results/intent_eval_results.json` (committed output), `README.md`
(results table).

---

## Tier 2 — Required Before Submission (Blockers)

These are quick to add but will cause disqualification if missing.

| Item | Status | Action |
|---|---|---|
| `LICENSE` file | ❌ Missing | Add MIT license — two minutes |
| Architecture diagram | ✅ Mermaid in README (channels → shared tool layer → data/calendar) | — |
| Alibaba Cloud deployment proof | ⚠️ Mentioned in README, no URL/screenshot | Deploy to ECS + commit evidence to `docs/deploy/` |
| PRD / TRD in repo | ❌ Referenced as `../Qwen_prd.md` (outside repo) | Move into `docs/` |
| Public repo | ✓ Branch pushed | Ensure repo visibility is public before submission |

---

## Tier 3 — Strengthens the Narrative

### Real Calendar Backend
Swap the Postgres stub in `app/tools/appointments.py` for a Google Calendar
API adapter behind the same `suggest_slots` / `book` / `find_existing`
interface. The rest of the agent doesn't change. Makes the demo credible and
signals production readiness to judges evaluating Problem Value.

### Proactive Agent Behavior
The n8n reminder/follow-up crons exist but are disconnected from the agent.
If the agent can proactively initiate a conversation — *"Your appointment is
tomorrow at 2pm, do you need to reschedule?"* — and handle the reply in the
same LangGraph loop, that's a demo moment most competitors won't have.

**Files to change:** `app/gateway/adapters/whatsapp.py` (add outbound-
initiated session), `app/agents/orchestrator.py` (proactive state entry),
n8n workflow to POST a trigger payload.

### Memory Showcase Seed Script
The decay-aware pgvector memory is the most technically novel component but
is invisible in a cold demo. Add `evals/seed_demo.py` that inserts 3–4 past
interactions for a demo patient, then show the agent surfacing context
without being prompted:

> *"I see from your last visit you prefer afternoon slots — shall I look for
> something after 2pm?"*

That one moment wins the Innovation score more than any architecture diagram.

---

## Demo Video Script (All 4 Criteria in One Take)

A single 3-minute video covering:

1. **Web chat** — patient asks to book, agent surfaces memory from a previous
   visit, suggests slots in clinic timezone, confirms booking (30 sec)
2. **WhatsApp** — same patient reschedules via WhatsApp, agent remembers
   preference from the web session (cross-channel memory) (45 sec)
3. **Voice** — caller asks about symptoms, agent refuses to give medical
   advice and escalates to staff with filler speech (30 sec)
4. **Staff dashboard** — escalation appears in real time, staff member clicks
   Approve (15 sec)
5. **MCP client** — Claude Desktop books an appointment via the MCP server
   without touching the web UI (30 sec)
6. **Multilingual** — patient sends a message in Arabic, agent replies in
   Arabic (15 sec)

---

## Build Order

```
Week 1 (now)   LICENSE · architecture diagram · deploy to ECS
               · commit eval results · move PRD/TRD into docs/

Week 2         Human-in-the-loop staff dashboard
               · multilingual triage + reasoner

Week 3         MCP server
               · memory showcase seed script + demo patient setup

Week 4         Record demo video (all channels + HiL + MCP + multilingual)
               · polish README · write Devpost submission description
               · final submission July 8
```

---

## Notes

- **Voice infrastructure cost:** ElevenLabs TTS is expensive for a live demo.
  Consider pre-recording the voice segment of the demo video rather than
  running it live; judges will not run it themselves regardless.
- **Track choice:** Track 4 (Autopilot Agent) is the stated track and the
  right fit. Track 1 (MemoryAgent) is also defensible given the decay-aware
  memory system — worth mentioning in the Devpost description even if not
  entered there.
- **No real patient data.** All demo data is synthetic. PHI handling is
  considered but HIPAA infrastructure is out of scope for the hackathon.
