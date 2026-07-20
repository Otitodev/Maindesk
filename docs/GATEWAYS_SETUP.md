# Gateway setup — bringing all 4 channels live

MainDesk has 4 patient-facing gateways. This doc is the operator's checklist for taking each one from "code deployed" to "actually answers patients." **Check readiness at `https://maindesk.otito.site/health/gateways`** — that endpoint reports which gateways have credentials wired.

---

## 1. Web `/chat` — ✅ Live by default

**Status**: no external service required. Live the moment the FastAPI container is up.

**Test**:
```bash
curl -X POST https://maindesk.otito.site/webhooks/web \
  -H 'content-type: application/json' \
  -d '{"session_id":"test","content":"what time do you close?"}'
```

Or open [https://maindesk.otito.site/chat](https://maindesk.otito.site/chat) in a browser.

**Optional**: set `WEB_API_KEY=<random>` in `.env` to require `X-API-Key` on every request. Leave empty for the demo so judges can hit it directly.

---

## 2. Voice — Pipecat + Twilio + Deepgram + ElevenLabs (~15 min)

Voice runs in-process as FastAPI routes (`app/voice/router.py` + `app/voice/bot.py`) — there is no separate worker process to start; it comes up automatically with the gateway container.

### 2a. Buy a Twilio number and point it at the app

1. [console.twilio.com](https://console.twilio.com/) → **Phone Numbers → Buy a number** (pick one that supports Voice).
2. Open the number → **Voice Configuration**:
   - "A call comes in" → **Webhook**
   - URL: `https://maindesk.otito.site/voice/twilio/incoming`
   - Method: `HTTP POST`
3. Save. That webhook returns TwiML that opens a Media Stream back to `wss://maindesk.otito.site/voice/twilio/media` — no static TwiML Bin needed, it's generated per-call so the caller's number rides along automatically.

### 2b. Fill the voice env vars

Locally in `.env`, or on the ECS box in `/opt/maindesk/.env`:

```env
TWILIO_ACCOUNT_SID=<from console.twilio.com -> Account -> API keys & tokens>
TWILIO_AUTH_TOKEN=<same page>
DEEPGRAM_API_KEY=<from console.deepgram.com -> API Keys>
ELEVENLABS_API_KEY=<from elevenlabs.io -> Profile -> API Keys>
ELEVENLABS_VOICE_ID=21m00Tcm4TlvDq8ikWAM   # or any other ElevenLabs voice id
HEALTHDESK_VOICE=true
HEALTHDESK_ENV=demo
```

### 2c. Bring the app up

**Locally** (for demo recording), then tunnel it so Twilio can reach your machine:
```powershell
cd C:\Users\DELL\Qwen_desk\healthdesk-ai
.venv\Scripts\uvicorn app.main:app --host 0.0.0.0 --port 8000
# in another terminal:
ngrok http 8000
```
Point the Twilio number's webhook at the ngrok HTTPS URL (`https://<subdomain>.ngrok.io/voice/twilio/incoming`) while testing locally.

**On the ECS box** (permanent):
```bash
# .env already has HEALTHDESK_VOICE=true
docker compose -f docker-compose.prod.yml up -d --build
```

No supervisord, no second process — `uvicorn app.main:app` is the only thing running in the container.

### 2d. Ring your Twilio number

Dial from any phone. Cost profile: Twilio's per-minute inbound rate (varies by number/country, typically ~$0.0085/min for a US number) + $0.0043/min Deepgram + ~$0.30 per 1k chars ElevenLabs. Under $5/day at demo volumes.

### 2e. Browser call widget — no phone number needed

There's a second voice entry point that customers reach without dialing anything: **`https://maindesk.otito.site/voice/web`**. It's a self-hosted WebRTC transport (Pipecat's `SmallWebRTCTransport`, backed by `aiortc`) — no Twilio, no third-party WebRTC vendor, no extra credentials beyond the `DEEPGRAM_API_KEY` / `ELEVENLABS_API_KEY` / `DASHSCOPE_API_KEY` already set above. It talks to the exact same agent pipeline (`app/voice/bot.py`) as the phone line.

Embed it on a clinic's site with an iframe, same pattern as `/chat`:
```html
<iframe src="https://maindesk.otito.site/voice/web" width="380" height="420" style="border:0"></iframe>
```

`/health/gateways` reports the phone and web voice paths separately (`voice.phone` / `voice.web`) since they have different credential requirements — the web widget can be `true` even with no Twilio account at all.

**Known limitation**: the widget only configures a public STUN server (no TURN relay), so a small fraction of visitors behind strict corporate/symmetric NATs won't be able to connect. Fine for a demo; worth adding a TURN server (e.g. via Twilio's own TURN service or a self-hosted `coturn`) before relying on it for real customer traffic at scale.

---

## 3. WhatsApp — Evolution API (~30 min)

**Status**: code + auth guards live. External service not yet configured.

MainDesk uses the [Evolution API](https://github.com/EvolutionAPI/evolution-api) — an open-source WhatsApp Business gateway. It runs your own WhatsApp Business number and posts inbound messages to `/webhooks/whatsapp`.

### 3a. Deploy Evolution API

Two paths:
- **Managed** — [evolutionapi.com](https://evolutionapi.com/) hosted plans start ~$10/mo. Fastest path.
- **Self-hosted** — Docker image, ~15 min to stand up next to MainDesk. See [Evolution's docker guide](https://doc.evolution-api.com/v2/en/install/docker).

For the hackathon: managed is faster.

### 3b. Configure the webhook

In the Evolution dashboard:
1. Create an instance for your WhatsApp Business number
2. Scan the QR code from the WhatsApp Business app to link
3. **Webhooks** → add:
   - URL: `https://maindesk.otito.site/webhooks/whatsapp`
   - Events: `MESSAGES_UPSERT`
   - Headers: `apikey: <YOUR_EVOLUTION_API_KEY>` (or configure HMAC)

### 3c. Fill env vars

```env
EVOLUTION_API_URL=https://api.your-evolution-host.com
EVOLUTION_API_KEY=<your evolution API key>
EVOLUTION_INSTANCE=<your instance name>
EVOLUTION_AUTH_MODE=token          # or "hmac" if you configured signing
EVOLUTION_WEBHOOK_SECRET=<random>  # only used with hmac mode
```

Or with HMAC:
```env
EVOLUTION_AUTH_MODE=hmac
EVOLUTION_WEBHOOK_SECRET=<random 32 chars>
```

Redeploy (auto or manual). `/health/gateways` should show `whatsapp.live: true`.

### 3d. Test

Send a WhatsApp message to your business number. MainDesk should reply within ~5s.

---

## 4. Email — Postmark-shaped provider (~15 min)

**Status**: code + webhook guard live. External service not configured.

MainDesk expects a Postmark-compatible inbound-parse webhook. [Postmark](https://postmarkapp.com/) is the default (~$10/mo starter, generous free tier for testing).

### 4a. Sign up + verify sender

1. [postmarkapp.com](https://postmarkapp.com/) → sign up (free tier)
2. Create a server → add a sender domain → verify DKIM/SPF records
3. Grab the **Server API Token** from Servers → API Tokens

### 4b. Configure inbound stream

1. Postmark → your server → **Inbound**
2. Note the **inbound email address** (e.g., `abc123@inbound.postmarkapp.com`) — this is what patients email
3. Set **Webhook URL** to `https://maindesk.otito.site/webhooks/email`
4. Add a shared secret header to the webhook config (Postmark supports custom headers)

### 4c. Fill env vars

```env
EMAIL_API_URL=https://api.postmarkapp.com
EMAIL_API_TOKEN=<your Postmark Server Token>
EMAIL_FROM=<your verified sender, e.g., hello@yourdomain.com>
EMAIL_WEBHOOK_SECRET=<matches the header you set in Postmark>
```

Redeploy. `/health/gateways` should show `email.live: true`.

### 4d. Test

Email `<your-inbound-address>@inbound.postmarkapp.com` with:
```
Subject: Hours?
Body: What time do you open?
```

MainDesk replies from `EMAIL_FROM` within ~10s.

---

## Readiness check — the single-source-of-truth

Every gateway's live/not-live state is reported at:

```
https://maindesk.otito.site/health/gateways
```

Example response when everything's wired:

```json
{
  "web":      { "endpoint": "POST /webhooks/web",       "live": true,  ... },
  "whatsapp": { "endpoint": "POST /webhooks/whatsapp",  "live": true,  ... },
  "email":    { "endpoint": "POST /webhooks/email",     "live": true,  ... },
  "voice":    { "endpoint": "WS /voice/twilio/media",   "live": true,  ... },
  "summary":  { "total": 4, "live": 4 }
}
```

When `summary.live == 4` and you can dial the number + send a WhatsApp + email the address + open `/chat` and all four talk to the same agent — **the goal is complete**.

---

## Priority for the hackathon (5 days)

If you can only wire two more gateways before July 9:

1. **Voice** — highest signal on judging. Real phone number = strongest demo moment. Also cheapest per minute for a demo (already almost done).
2. **WhatsApp** — the marquee channel in the pitch. But needs an external service you don't control. Time-risk high.

Skip:
- **Email** — least visual impact for a video demo, most external-service overhead. Punt to post-hackathon.

If time is tight: **voice only**. Ship with 2/4 gateways truly live (web + voice) and mention WhatsApp + email as configured but requiring per-clinic provisioning. That's an honest and defensible position for a Track 4 submission.
