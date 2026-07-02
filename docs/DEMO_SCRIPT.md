# MainDesk — 3-Minute Demo Script

**Hard cap: 3:00.** Judges are not required to watch past this. Every second must earn its place.

**Target audience**: Qwen Cloud Hackathon Track 4 judges. Assume they've read the README, know what LangGraph is, and are grading against Innovation (30%) / Tech Depth (30%) / Problem Value (25%) / Presentation (15%).

**Filming setup**
- 1080p screencap, no webcam PIP
- Voiceover recorded separately (don't record live commentary — audio drops kill the vibe)
- No copyrighted music. Use YouTube Audio Library or nothing.
- No visible WhatsApp branding on the WhatsApp segment — narrate over a terminal `curl` view or a screenshot with the wordmark cropped.
- Show real Qwen model names on screen at least twice (`qwen-plus`, `qwen-turbo`, `text-embedding-v3`).

---

## Beat-by-beat script

### 0:00 – 0:15 · Hook

**On screen**: Landing page hero — "MainDesk" logo, "Powered by Qwen · 通义千问" tag visible.

**VO**: "Every clinic runs into the same wall — after 5 PM the phones go to voicemail, patient questions pile up, staff burn out. MainDesk is an autonomous front desk that answers on every channel, in any language, all day."

### 0:15 – 0:45 · WhatsApp channel — the escalation path

**On screen**: Split view — left: an SMS-style transcript (WhatsApp branding cropped or a mock UI); right: staff dashboard `/staff` empty state.

**VO**: "A patient messages the clinic on WhatsApp asking to book a checkup. MainDesk answers in real time — checks the calendar, offers slots, confirms."

**Show**: Patient types "book me for Tuesday morning" → agent replies with 2 available slots → patient picks one → confirmation message.

**VO** (over the next message): "Then this happens."

**Show**: Patient types "I've had crushing chest pain for an hour, what do I do?"

**Show on right side**: Dashboard populates with a new HITL card — red urgency badge, transcript, "Assign to me" button.

**VO**: "Chest pain triggers the escalate intent. The agent hands off to a human — instantly — instead of pretending to diagnose."

### 0:45 – 1:15 · HITL resolve on the staff dashboard

**On screen**: `/staff` dashboard, HTMX+SSE live update.

**VO**: "The staff dashboard is a live queue. Server-sent events, no polling. A clinician picks up the card, sees the transcript with context, and replies once."

**Show**: Click "Assign to me" → type "Please go to the ER now, call us from there" → send.

**Show**: Reply appears in the patient's WhatsApp thread within a second.

**VO**: "One reply, one channel switch, patient safe."

### 1:15 – 1:45 · `/chat` widget + Chinese roundtrip

**On screen**: Browser at `/chat`, MainDesk widget, light theme matching landing page.

**VO**: "Same orchestrator, different channel. The web widget hits `/webhooks/web` — no separate code path, no separate memory."

**Show**: Type "你好，我想预约下周二的检查" → agent responds in Chinese, offers slots.

**VO**: "The Qwen models handle Mandarin natively. Same LangGraph, same pgvector memory, same tools — the language just flows through."

### 1:45 – 2:30 · Voice + architecture reveal

**On screen**: Split — left: LiveKit voice agent on a phone browser talking (waveform visible); right: `docs/architecture.png` fading in.

**VO**: "Voice is the fifth channel — LiveKit for the transport, Qwen for ASR, LLM, and TTS. All three runtimes on DashScope."

**Cut to**: Full architecture diagram.

**VO**: "One LangGraph orchestrator sits behind five channels — WhatsApp, email, web, `/chat`, and voice. It talks to a Postgres checkpoint store, a pgvector recall layer with multilingual decay-weighted re-ranking, a tool layer that reaches Google Calendar and the clinic's FAQ store, and a human-in-the-loop queue."

**On screen**: Highlight the Qwen boxes one at a time — Qwen-Plus (orchestrator LLM), Qwen-Turbo (guardrails and classification), text-embedding-v3 (memory).

**VO**: "Three Qwen models. One cloud. Every reply passes through outbound secret redaction before it leaves the process."

### 2:30 – 3:00 · Close

**On screen**: `pytest` output — 218 passed. Then cut to intent eval results — 33/33.

**VO**: "218 tests green, 33 out of 33 on the intent evaluation, including three Mandarin cases. Multi-channel parity. Human-in-the-loop when it matters. Deployed on Alibaba Cloud, submitted to Track 4 — Autopilot Agent."

**Final frame**: MainDesk logo + "Powered by Qwen · 通义千问" + repo URL.

---

## What NOT to include

- No apologies ("still rough around the edges"). Judges hear this constantly. Sell the thing.
- No feature list read-aloud. The dashboard demo shows more in 15 seconds than a bullet list does in 60.
- No architecture explanation before showing the product working. Product first, arch second.
- No mention of what's missing or future roadmap. That's for the README.
- No music with lyrics. Distracting.

---

## Voiceover writing rules

- Present tense, active voice. "The agent replies" not "The agent will reply."
- Numbers earn attention: "218 tests," "33 out of 33," "sub-second."
- Say the Qwen model names out loud at least once each. Judging weight #1 rewards visible Qwen usage.
- One idea per sentence. If a sentence has two commas, split it.
- Read the script out loud with a stopwatch before recording. 3:00 hard cap means the read has to come in at 2:50 to survive edits.

---

## Post-production checklist

- [ ] Total length ≤ 3:00 (stopwatch it)
- [ ] Public visibility on YouTube / Vimeo / Youku
- [ ] Captions burned in or auto-generated (helps judges skimming without audio)
- [ ] No third-party wordmarks visible (WhatsApp, Google Calendar, LiveKit logos cropped or covered)
- [ ] No copyrighted music
- [ ] Repo URL visible in the final frame **and** in the video description
- [ ] Video URL pasted into the Devpost submission
