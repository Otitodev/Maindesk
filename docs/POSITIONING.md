# MainDesk Positioning

*One page. If you can't fit it here, it's not tight enough.*

---

## One-line pitch

**MainDesk is the AI-native front desk that answers every patient message, in every language, on every channel — so clinics stop losing patients to voicemail and stop paying $45k/year to route calls.**

---

## Target persona

**Dr. Amina Okonkwo** — solo GP / partner in a 2–8 clinician practice.

- Owns or partners in a family practice, dental office, physio clinic, or small specialty group
- 50–500 patient contacts per week across WhatsApp, phone, email, and web
- Currently pays a receptionist $30–50k/year plus benefits, plus loses ~15% of after-hours inquiries to voicemail
- Not "tech-forward" — she uses Google Calendar and WhatsApp Business but nothing more sophisticated
- Speaks English + one of {Spanish, Mandarin, Yoruba, Portuguese} depending on region
- Buys through referral, LinkedIn ads, or search intent like *"AI receptionist for medical clinic"*
- Signs personally, not through IT procurement — decision cycle is days, not months

**Not our persona (yet):** hospital systems, dental chains > 50 locations, insurance-first workflows, US HIPAA-regulated deployments requiring a signed BAA. Those come after series A.

---

## The wedge

Every other "AI receptionist" product is either:

1. **A chatbot bolted onto a single channel** (web only, or WhatsApp only). Patients don't stay on one channel. The receptionist replacement has to be *channel-agnostic.*
2. **A voice-only IVR upgrade** ("Press 1 for appointments"). Still routes to human. Doesn't book. Doesn't remember.
3. **A generic LLM wrapper** with no clinic context — hallucinates hours, invents insurance policies, no HITL.

**MainDesk's wedge**: one orchestrator, five channels, real appointment booking with real calendar writeback, real human handoff when confidence dips, real memory across sessions and channels.

That's what "replaces the receptionist" means. Not what any competitor is shipping today.

---

## Value prop — the three claims

1. **Zero missed contacts.** Voicemail-free. 24/7 across WhatsApp, email, web, voice, and browser chat. Every message gets an answer within seconds.
2. **Books real appointments.** Not a bot that says "please call to book." Real Google Calendar free/busy queries. Real writes. Real confirmations.
3. **Knows when to hand off.** Chest pain, angry patient, ambiguous request — the agent routes to a live clinician's dashboard instead of pretending. This is why doctors trust it.

Everything else is a feature. These three are the promises.

---

## The competitive line

| | MainDesk | Notion AI / ChatGPT bots | IVR "voice AI" | Human receptionist |
|---|:---:|:---:|:---:|:---:|
| Multi-channel | ✅ 5 channels | ❌ 1 | ❌ voice only | ⚠️ phone + walk-in |
| Real appointment booking | ✅ | ❌ | ⚠️ | ✅ |
| Multilingual (native) | ✅ EN + 中文 | ⚠️ prompted | ⚠️ scripted | ⚠️ if bilingual |
| Human handoff | ✅ HITL | ❌ | ⚠️ transfer | n/a |
| Persistent memory | ✅ | ❌ | ❌ | ⚠️ notes |
| Runs 24/7 | ✅ | ✅ | ✅ | ❌ |
| $/month | $299 | $20 | $500+ | $3,500+ |

---

## Voice & tone

- **Confident, not salesy.** We're the receptionist replacement, not a bolt-on. Say so.
- **Concrete numbers.** "Handled 89 messages last week" beats "high message volume."
- **Never use the word "cutting-edge."** Also banned: "revolutionary," "seamless," "leverage."
- **Say what it doesn't do.** MainDesk doesn't do diagnostic advice. Doesn't do billing. Doesn't pretend to be a human. Naming limits builds trust.
- **Speak to the operator, not the patient.** Landing page copy addresses Dr. Amina, not her patients.
- **Show working software over marketing.** The `/chat` widget on the landing page CTA is the pitch.

---

## What we say we don't do (for now)

Named explicitly on the site and in sales conversations. Prevents disappointment, builds trust.

- **HIPAA BAA** — not signed. US regulated healthcare should wait for our Q3 enterprise tier.
- **Multi-tenant self-serve signup** — currently white-glove per deployment. Get early access via the site.
- **Custom voice cloning** — the voice channel uses ElevenLabs stock voices for v1.
- **EHR integrations** — no Epic, Cerner, or Athena integration yet.
- **Multi-location routing** — one MainDesk deployment = one clinic. Multi-site is on the roadmap.

---

## Pricing philosophy

Three-tier land-and-expand SaaS. Anchored on the receptionist salary comparison ($3–5k/mo human vs. $299–2999/mo MainDesk).

- **Starter — $299/mo** — one channel, one clinic, up to 500 monthly patient contacts. For solo GPs testing the water.
- **Practice — $799/mo** — all five channels, up to 2,500 contacts, live HITL dashboard, priority support. The main tier — this is where 80% of clinics land.
- **Enterprise — talk to us** — unlimited contacts, custom voice, dedicated onboarding, SLA. For multi-location groups.

First 100 clinics get 50% off for the first year. Creates urgency without dishonesty.

---

## Positioning statement (for the pitch deck / About page)

> **For the small-clinic operator drowning in patient messages, MainDesk is the AI-native front desk that answers every WhatsApp, email, web chat, and voice call — books real appointments, escalates the ones that need a human, and remembers every patient across every channel. Unlike single-channel chatbots or generic LLM wrappers, MainDesk is one orchestrator behind every channel, so patients get one consistent front desk no matter how they reach you. And you get your reception hours back.**

---

## Repo alignment (so the code tells the same story)

- README's Chinese lede + "multi-channel autonomous front-desk AI assistant" phrasing → matches the positioning statement
- Landing page hero: "Powered by Qwen · 通义千问" — signals we lean into the tech stack rather than hiding it
- `/onboarding` wizard exists — proves the "operator sets up in minutes" claim
- `/staff` HITL dashboard exists — proves the "knows when to hand off" claim
- `/chat` widget is live at maindesk.otito.site — proves the demo, not just the pitch

Every piece of the positioning has a corresponding artifact in the repo. No smoke. That's the moat.
