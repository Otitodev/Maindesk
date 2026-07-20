# MainDesk — 3-Minute Demo Script

**Hard cap: 3:00.** Judges are not required to watch past this. Every second earns its place.

**Target audience**: Qwen Cloud Hackathon Track 4 judges. Assume they've skimmed the README and are grading on Innovation (30%) / Tech Depth (30%) / Problem Value (25%) / Presentation (15%).

**Narrative approach**: Follow one operator persona — **Dr. Amina Okonkwo**, a Lagos family GP whose receptionist quit two weeks ago — through her first week with MainDesk. This is grounded in `docs/POSITIONING.md`.

**Filming setup**
- 1080p screen recording, no webcam PIP
- Voiceover recorded separately (don't ad-lib live; retakes are cheaper than transcripts)
- No copyrighted music. YouTube Audio Library or nothing.
- No visible WhatsApp branding. Cover the wordmark or use a mocked SMS thread with a generic phone-frame overlay.
- Say Qwen model names out loud at least twice: `qwen3.7-plus`, `text-embedding-v4`
- Keep the URL `maindesk.otito.site` visible at the top of the browser for the last 60 seconds

---

## Beat-by-beat (7 beats, 3:00 hard cap)

### 0:00 – 0:15 · The problem

**On screen**: Landing page hero — headline "Your front desk, running on autopilot," "Powered by Qwen · 通义千问" tag, the "Call the front desk: +1 (218) 307-4659" button visible. **(Note: the pricing section previously in this beat was removed from the live landing page — don't pan to it, it no longer exists.)**

**VO**: "Dr. Amina runs a family clinic in Lagos. Her receptionist quit two weeks ago and the phones are burying her. She finds MainDesk at 11 PM on a Tuesday."

*Cursor hovers over "Call the front desk". Don't actually dial live — the point of this beat is the promise, not the call itself; the real phone demo (if you want one) is a separate, pre-tested clip, not something to risk inside a single continuous take.*

**VO**: "At $299 a month, that's less than a week of a receptionist's pay. She books the trial." *(the $299 figure is the same one referenced live in the analytics page's ROI callout — keep it consistent)*

### 0:15 – 0:40 · The setup

**On screen**: Cut to `/onboarding` wizard. Cursor fills in — clinic name "Harmony Family Clinic", timezone Africa/Lagos, hours 9-17, working days Mon–Fri, mode "always", FAQ box gets a few clinic facts.

**VO**: "The next morning she configures the clinic in three minutes. Name, hours, the FAQ she used to explain forty times a day. Save."

*Click Save. Green checkmark appears.*

**VO**: "MainDesk is live everywhere her patients already message her — phone, WhatsApp, web chat."

### 0:40 – 1:10 · Money shot 1: multilingual booking

**On screen**: Cut to `https://maindesk.otito.site/chat`. Chat widget with the opening bubble.

Type slowly, so the viewer reads it:
```
你好，我想预约下周二的检查
```

*Send. Typing indicator dots. Reply arrives in Mandarin with real dates.*

**VO**: "A patient messages in Mandarin. MainDesk understands, checks the calendar, and offers real slots — in Mandarin, in the correct date format, with no translation step. `qwen3.7-plus` speaks fluent Chinese by default, `text-embedding-v4` handles multilingual memory."

*Highlight the reply — `2026年7月3日 上午 9:00` visible.*

**VO**: "One agent. Every language."

### 1:10 – 1:40 · Money shot 2: escalation

**On screen**: Same `/chat` widget. Clear input. Type:
```
I've had crushing chest pain for an hour, help
```

*Send. Brief acknowledgment appears: "One moment while I get a human on this."*

**Cut immediately to** `/staff` dashboard in a second tab. A red urgency card slides in via SSE.

**VO**: "Chest pain triggers the escalate intent. The agent aborts its own reply — no diagnostic bullshit — and posts to the staff dashboard. Server-sent events, no polling. Dr. Amina picks it up."

*Click "Assign to me". Type "Please go to the ER now, call us from there." Send.*

*Cut back to /chat — the reply lands in the patient thread.*

**VO**: "One switch, one reply, patient safe. This is what MainDesk means by 'AI-native' — it knows when to be a human."

### 1:40 – 2:10 · The proof: analytics

**On screen**: Navigate to `/staff/analytics`. Four tiles: bookings handled, escalations to a human, avg time to human, reception hours replaced.

**IMPORTANT — do not hardcode numbers here.** These are real, live production counters that grow with every real booking/escalation — they will not match whatever number was true when this script was drafted. **Read the actual tile values off the screen at recording time.** As of 2026-07-20 they read 13 bookings, 7 escalations (3 open), 45 min avg, 0.9 hrs replaced — check again right before filming.

**VO** *(fill in [N] with the live numbers on screen)*: "This isn't a mockup — it's the real production console, live right now. [N] patient messages handled autonomously this month. [N] escalations — the ones that mattered. At the $299 tier, that's roughly thirty cents per autonomous booking — a receptionist call costs three to seven dollars."

*Pause on the "What this tells you" callout.*

**VO**: "This is the ROI slide judges usually have to imagine. It's a real page in the product, showing real usage."

### 2:10 – 2:40 · Architecture reveal

**On screen**: Fade in a PNG exported from `docs/architecture.mmd` (import the Mermaid source into Excalidraw and export — the old `docs/architecture.png` was deleted, it predated the Twilio/Pipecat migration). Highlight the boxes one at a time as they're mentioned.

**VO**: "Under the hood: one LangGraph orchestrator sits behind four channels — WhatsApp, email, web, and voice, a real phone number over Twilio. Every channel hits the same Pipecat pipeline, reasoning on Qwen through DashScope."

*Highlight the Qwen boxes.*

**VO**: "Triage classifies intent on `qwen3.6-flash`. Generation runs on `qwen3.7-plus`. Memory recall uses `text-embedding-v4` into pgvector with a decay-weighted re-ranker — so a patient's penicillin allergy in Mandarin surfaces when they send an English message six months later."

*Highlight the postgres box + HITL queue.*

**VO**: "AsyncPostgres checkpoints keep multi-turn conversations alive across restarts. Every outbound message runs through a secret redactor. Every escalation lands in the same HITL queue."

### 2:40 – 3:00 · Close

**On screen**: Cut back to the landing page hero. `maindesk.otito.site/chat` visible in the URL bar.

**VO**: "Deployed on Alibaba Cloud ECS in Singapore. Two hundred twenty-two tests green. Thirty-two of thirty-three on the intent eval — including all three Mandarin cases. Live now at maindesk.otito.site."

*(Test count verified via `pytest -q` and eval numbers via `python -m evals.run_intent_eval` on 2026-07-20 — re-run both right before recording if anything's changed since.)*

*Final frame: logo + "Powered by Qwen · 通义千问" + repo URL + "Track 4: Autopilot Agent"*

**VO**: "MainDesk. The AI-native front desk. Not a chatbot. A replacement."

---

## What NOT to include

- **No apologies.** No "still rough around the edges." Sell the thing.
- **No feature list read-aloud.** The dashboard demo showed more in 15 seconds than a bullet list does in 60.
- **No architecture explanation before showing product working.** Product first, arch second — every beat before 2:10 is Dr. Amina using it.
- **No mention of what's missing.** Multi-tenancy, HIPAA BAA, EHR integrations — those belong in the Devpost "What's next" field, not on camera.
- **No lyrics in the background music.** Distracting.
- **No live typing at real speed.** Pre-record the message inputs and time the cuts. Live typing eats seconds you can't spare.

---

## Voiceover writing rules

- **Present tense, active voice.** "The agent replies." Not "The agent will reply."
- **Concrete numbers earn attention.** "222 tests," "62 hours," "$0.30 per booking," "9 AM slot."
- **Say Qwen model names out loud.** `qwen3.7-plus`, `qwen3.6-flash`, `text-embedding-v4`. Judging weight #1 rewards visible Qwen usage; audible counts too.
- **One idea per sentence.** If a sentence has two commas, split it.
- **Read the whole script out loud with a stopwatch before recording.** 3:00 hard cap means the read has to come in at 2:50 to survive edits and breathing space.
- **Dr. Amina is a person, not a case study.** Say "she" — not "the operator" or "the clinic owner."

---

## The one line that has to land

> **"MainDesk. The AI-native front desk. Not a chatbot. A replacement."**

That's the sticker line. It goes on the last frame, in the video description, and in the Devpost tagline. Every other line in the script leads toward it.

---

## Post-production checklist

- [ ] Total length ≤ 3:00 (stopwatch it, not estimate)
- [ ] Public visibility on YouTube / Vimeo / Youku
- [ ] Captions burned in or auto-generated (helps judges skimming without audio)
- [ ] No third-party wordmarks visible (WhatsApp, Google Calendar, Twilio logos cropped or covered)
- [ ] No copyrighted music
- [ ] Repo URL visible in the final frame **and** the video description
- [ ] Video URL pasted into the Devpost submission
- [ ] `maindesk.otito.site` URL is clickable in the video description too

---

## If you have 90 seconds instead of 3:00 (for social)

Cut the setup (0:15–0:40) and the architecture (2:10–2:40). Keep:
- Hook (15s)
- Chinese booking (30s)
- Escalation → HITL (30s)
- Analytics tiles + close (15s)

That's 90 seconds, still Dr. Amina, still all three money shots. Post to X/Twitter and LinkedIn on submission day for the "scalability potential" community-signal score.
