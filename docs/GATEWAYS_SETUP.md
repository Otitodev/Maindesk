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

## 2. Voice — LiveKit + Deepgram + ElevenLabs (~15 min)

**Status**: number bought (`+1 484 270 7025`), dispatch rule created (`SDR_2eGJxpC4xohv`). Two things left:

### 2a. Attach the dispatch rule to the number

CLI is blocked by a "catch-all rule" safety check. Use the console instead:

1. [cloud.livekit.io](https://cloud.livekit.io) → **Telephony → Phone Numbers**
2. Click **+1 484 270 7025**
3. **Dispatch Rule** → pick `MainDesk inbound`
4. Save

Verify: `lk number list` shows `SDR_2eGJxpC4xohv` in the "SIP Dispatch Rules" column.

### 2b. Fill the 5 voice env vars

Locally in `.env`, or on the ECS box in `/opt/maindesk/.env`:

```env
LIVEKIT_URL=wss://qwen-hackathon-3o35vwom.livekit.cloud
LIVEKIT_API_KEY=APIszEksEqodD8j...
LIVEKIT_API_SECRET=<from LiveKit console -> Settings -> Keys>
DEEPGRAM_API_KEY=<from console.deepgram.com -> API Keys>
ELEVENLABS_API_KEY=<from elevenlabs.io -> Profile -> API Keys>
HEALTHDESK_VOICE=true
HEALTHDESK_ENV=demo
```

### 2c. Start the worker

**Locally** (for demo recording):
```powershell
cd C:\Users\DELL\Qwen_desk\healthdesk-ai
.venv\Scripts\python -m app.voice.agent_worker start
```

Watch for `registered worker id=... agent_name=healthdesk`.

**On the ECS box** (permanent):
```bash
# .env already has HEALTHDESK_VOICE=true
docker compose -f docker-compose.prod.yml up -d --build
```

The supervisord config runs the worker alongside the API in the same container.

### 2d. Ring **+1 484 270 7025**

Dial from any phone. Cost: $0 to caller carrier + LiveKit's free 50 inbound minutes.

**Cost profile after free tier**: ~$0.03/min inbound (US number, LiveKit) + $0.0043/min Deepgram + ~$0.30 per 1k chars ElevenLabs. Under $5/day at demo volumes.

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
  "voice":    { "endpoint": "LiveKit worker",           "live": true,  ... },
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
