# Devpost submission draft. Copy into the submission form.

Fill in the video URL and repo URL once you have them. Track: Track 4, Autopilot Agent.

---

## Tagline

MainDesk is the AI native front desk that answers every patient message across WhatsApp, email, web, and voice, books real appointments, and knows when to hand off to a human.

---

## Project story

### Inspiration

Small clinics lose patients to voicemail. A solo GP running a small practice pays tens of thousands a year for a receptionist and still misses a chunk of after hours messages, because patients don't stick to one channel. They call, then WhatsApp, then email the same question. Every "AI receptionist" we looked at was a single channel chatbot, a voice only IVR that still hands off to a human, or a generic LLM wrapper that invents clinic facts and never knows when to stop. We wanted to build the thing that actually replaces the receptionist, not a demo of one.

### What it does

One LangGraph orchestrator sits behind every channel a patient might use: WhatsApp, email, the web chat widget, and voice, both a real phone number over Twilio and a browser call widget we host ourselves. Same brain every time. It books real appointments against Google Calendar, remembers patients across channels and sessions, replies in whatever language the patient used, refuses to invent clinic facts it doesn't actually know, and hands off to a live staff dashboard the moment something looks medical or uncertain. Staff reply once and it routes straight back to the patient on whatever channel they used. The same tools are also exposed over MCP, so staff can manage the schedule from Claude Desktop or Cursor if they'd rather.

### How we built it

Qwen Plus handles reasoning, Qwen Turbo classifies intent and language cheaply up front. LangGraph runs the orchestration, checkpointed to Postgres so conversations survive a restart. Memory is pgvector with a recency weighted reranker so recent context outweighs old. Voice runs on Pipecat, in process as FastAPI routes rather than a separate worker, sharing one pipeline across Twilio and a browser widget we host ourselves, with Deepgram for speech to text and ElevenLabs for text to speech. The whole thing runs on Alibaba Cloud ECS in Singapore behind Caddy, deployed on every push through GitHub Actions.

### Challenges we ran into

Voice originally ran on LiveKit. We rebuilt it on Pipecat and Twilio partway through the project, same providers underneath but a genuinely different pipeline, and it let us drop the separate voice worker process entirely. That opened the door to adding a second way into voice, a browser widget, almost for free once voice wasn't tied to one telephony vendor anymore.

We also learned not to trust "it's probably fine" about test infrastructure. Partway through we found our local database had quietly been missing two schema migrations, and that our own evaluation script had never actually run on Windows because of a missing encoding flag, which meant three Mandarin test cases had never really been checked. Fixed both. The eval now reports real numbers instead of a stale claim nobody had verified.

### Accomplishments we're proud of

Three of four patient facing gateways verified live in production right now, including voice, twice over: phone and browser widget. 217 automated tests passing, and 32 of 33 on the intent classification eval against live Qwen, including all three Mandarin cases, not a cached result. A human in the loop escalation that actually closes the loop end to end, and cross channel memory that surfaces on its own instead of on request.

### What we learned

Channel agnostic only means something if the tool layer is actually shared. The moment booking or escalation logic diverges between voice and text, you don't have one front desk anymore, you have several bots wearing the same name. Keeping every channel behind the same orchestrator and the same tools is what made memory and escalation work the same way everywhere instead of mostly everywhere.

### What's next

Self serve signup for multiple clinics instead of one deployment each, a signed HIPAA agreement for regulated US healthcare, EHR integrations, and routing for clinics with multiple locations. On the Qwen side specifically, voice speech to text and text to speech still run on Deepgram and ElevenLabs. DashScope's own Paraformer and CosyVoice models are on the roadmap to make the whole voice stack Qwen native, not just the reasoning layer.

---

## Submission checklist

- [ ] Video URL (YouTube, Vimeo, or Facebook, public): ___________
- [ ] Repo URL: https://github.com/Otitodev/healthdesk-ai
- [ ] Live demo URL: https://maindesk.otito.site
- [ ] Track: Track 4, Autopilot Agent
- [ ] Proof of Alibaba Cloud deployment: link the live URL above, consider attaching an ECS console screenshot as backup
- [ ] Architecture diagram: `docs/architecture.png` (re export from `docs/architecture.mmd` first, the committed PNG is stale)
