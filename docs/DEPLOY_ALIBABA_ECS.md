# Deploy MainDesk to Alibaba Cloud ECS

Target audience: you, right now, with the **$40 coupon applied and account ready**. Goal: a public, HTTPS-optional demo URL that judges can hit, satisfying the Qwen Cloud Hackathon requirement *"backend is running on Alibaba Cloud."*

Estimated time: **45 – 90 minutes**, most of that waiting for the instance to provision and Docker to build.

---

## 0 · Decisions made for you

| Question | Choice | Why |
|---|---|---|
| Region | **Singapore (`ap-southeast-1`)** | No ICP filing required (mainland-only rule), low latency from most of the world, judges in APAC and US both reach it fine. Hong Kong is a viable alternative. **Avoid mainland China regions** — they require ICP filing for public web serving. |
| OS | **Ubuntu 22.04 LTS 64-bit** | The `deploy/bootstrap.sh` script targets it directly. |
| Instance family | **ecs.e-c1m2.large** (2 vCPU / 4 GB) or **ecs.u1-c1m2.large** (universal) | Cheapest always-on families that comfortably run FastAPI + Postgres+pgvector + Caddy. `t6` burstable is even cheaper but throttles under load — not worth the risk during the judging window. |
| Disk | **40 GB ESSD Entry** | Docker layers + pgvector data + Caddy state fit in ~10 GB; 40 GB gives headroom. |
| Network | **Assign a public IPv4** with **pay-by-traffic**, 5 Mbps peak | Pay-by-traffic is cheaper than fixed bandwidth for demo-scale traffic. |
| Billing | **Pay-as-you-go** | The $40 voucher covers ~1–2 months of this shape. Subscription locks you in longer. |
| Domain | **Optional.** Skip it and use `http://<ecs-ip>/chat` for the demo. | A custom domain adds DNS + ICP considerations and buys you very little for a 3-min demo. |

---

## 1 · Create the ECS instance (Console)

**Console path**: [ecs.console.aliyun.com](https://ecs.console.aliyun.com) → Overview → *Create Instance*.

Wizard steps:

1. **Region** → *Singapore (ap-southeast-1)*, zone A or B (whichever quota is available).
2. **Instance type** → filter by *2 vCPU, 4 GiB*, pick `ecs.e-c1m2.large` (fallback: `ecs.u1-c1m2.large`). Pay-as-you-go.
3. **Image** → Public Image → Ubuntu → **Ubuntu 22.04 64-bit**.
4. **Storage** → System disk 40 GB, ESSD Entry (cheapest). No data disk needed.
5. **Bandwidth & security group**:
   - *Assign public IPv4 address* ✅
   - *Bandwidth billing method* → **Pay-by-traffic**
   - *Peak bandwidth* → 5 Mbps
   - *Security group* → **Create a new one**, allow inbound: **TCP 22 (from your IP only)**, **TCP 80 (0.0.0.0/0)**, **TCP 443 (0.0.0.0/0)**. Nothing else.
6. **Logon credentials** → **Key Pair**. Create one, download the `.pem`. Save to `~/.ssh/maindesk-ecs.pem`, `chmod 400` it.
7. **Instance name** → `maindesk-prod`. Hostname same.
8. Confirm order. Voucher applies at checkout.

Wait ~60 seconds for the instance to reach **Running**. Note the **public IP**.

---

## 2 · Bootstrap the box (5 min)

From your laptop:

```bash
# Copy your Qwen/DashScope key and other secrets to a local .env first.
# The bootstrap script will show you the required keys after first run.
ssh -i ~/.ssh/maindesk-ecs.pem root@<ecs-public-ip>
```

On the ECS box:

```bash
curl -fsSL https://raw.githubusercontent.com/Otitodev/healthdesk-ai/main/deploy/bootstrap.sh -o bootstrap.sh
chmod +x bootstrap.sh
sudo ./bootstrap.sh
```

The first run:
- Installs Docker + Compose plugin
- Configures `ufw` (defence-in-depth alongside the Alibaba security group)
- Clones the repo to `/opt/maindesk`
- Copies `.env.example` → `.env` **and stops.** You must fill in real values.

Edit `/opt/maindesk/.env`:

```bash
sudo nano /opt/maindesk/.env
```

Minimum required keys (the script also prints this list):

```env
DASHSCOPE_API_KEY=sk-...            # Your Qwen Cloud key
POSTGRES_USER=healthdesk
POSTGRES_PASSWORD=<openssl rand -hex 24>
POSTGRES_DB=healthdesk
DATABASE_URL=postgresql://healthdesk:<pw>@postgres:5432/healthdesk
STAFF_DASHBOARD_KEY=<openssl rand -hex 24>
GATEWAY_PROXY_KEY=<openssl rand -hex 24>
HEALTHDESK_ENV=production
HEALTHDESK_DEMO_PATIENT_PHONE=2340000000000
DOMAIN=                              # leave blank → IP-only, HTTP
ACME_EMAIL=hello@maindesk.ai         # only used if DOMAIN is set
# WEB_API_KEY intentionally left unset so /chat works for judges out of the box
```

Then re-run:

```bash
sudo /opt/maindesk/deploy/bootstrap.sh
```

Second run brings the stack up (`docker compose -f docker-compose.prod.yml up -d --build`) and waits for `/health` to return 200.

---

## 3 · Verify

From your laptop:

```bash
curl -sS http://<ecs-public-ip>/health       # → {"status":"ok"}
open  http://<ecs-public-ip>/chat            # → chat widget loads
```

Send a Chinese message through the widget:

```
你好，我想预约下周二的检查
```

You should get a Chinese reply within ~2 seconds, confirming the DashScope roundtrip works from the ECS instance.

---

## 4 · Point the landing page at the deployment

Two options:

**A. Static hosting stays where it is** (Vercel / Netlify / GitHub Pages) and only the API calls go to Alibaba Cloud. Edit the `/chat` widget or landing CTAs to point at `http://<ecs-ip>/chat`. Simplest.

**B. Serve the landing page from the ECS instance too.** Copy `landingpage/index.html` (and its assets) into the container as a static route. More work, no judging benefit.

Recommend A. Update the landing page's "See it live →" button `href` to `http://<ecs-ip>/chat` (or your domain if you set one) and redeploy the static site.

---

## 5 · Submit the "Proof of Alibaba Cloud" artifact

Rules require: *"a link to a code file in their code repo that demonstrates use of Alibaba Cloud services and APIs."*

Use: **`app/agents/qwen_client.py`** — it holds all DashScope API calls (Qwen-Plus, Qwen-Turbo, text-embedding-v3).

Paste this URL into the Devpost field:

```
https://github.com/Otitodev/healthdesk-ai/blob/main/app/agents/qwen_client.py
```

Add a screenshot of the running ECS instance from the console (Instance detail → Overview tab) to the Devpost images section. Judges will see the region, instance ID, public IP, and running state — undeniable proof.

---

## 6 · Cost expectations against the $40 voucher

Rough numbers (Singapore region, pay-as-you-go, June 2026):

| Line item | Approx. USD |
|---|---|
| `ecs.e-c1m2.large` compute | ~$0.03 / hr → ~$22 / month |
| 40 GB ESSD Entry | ~$4 / month |
| Public IPv4 reservation | ~$3 / month |
| Bandwidth pay-by-traffic @ ~1 GB/day demo load | ~$3 / month |
| **Total** | **~$32 / month** |

**Voucher runway: ~5 weeks.** Enough to cover submission (July 9), judging window (through July 31), and winner announcement (August 7) with margin.

Exact prices vary — verify with the [Alibaba Cloud pricing calculator](https://www.alibabacloud.com/en/pricing-calculator) before finalising, and check the [ECS pricing list](https://www.alibabacloud.com/en/product/ecs-pricing-list/en) for your specific SKU and region.

**When the voucher runs out**: pay-as-you-go bills to your card. Set a Billing → Budgets alert at $30 to avoid surprise.

---

## 7 · If you set a custom domain (optional)

1. Point an `A` record at the ECS public IP.
2. Set `DOMAIN=your.domain` and `ACME_EMAIL=you@example.com` in `.env`.
3. `docker compose -f docker-compose.prod.yml restart caddy`
4. Caddy provisions Let's Encrypt automatically. Watch the logs: `docker logs -f healthdesk-caddy`.

**Do not** point the domain at an IP in a mainland China region — you'll need ICP filing (weeks of paperwork). Singapore, Hong Kong, and US regions have no ICP requirement.

---

## 8 · Common failure modes

| Symptom | Likely cause | Fix |
|---|---|---|
| SSH connection refused | Security group missing TCP 22 rule, or you set source to a stale IP | Console → Security Group → Add inbound rule TCP/22 from your current IP |
| `bootstrap.sh` hangs on Docker install | apt sources unreachable from Singapore mirror | Add a mirror: `sudo sed -i 's|archive.ubuntu.com|mirrors.aliyun.com|g' /etc/apt/sources.list` and re-run |
| `/health` returns nothing but curl succeeds locally on the box | Security group missing TCP 80 rule | Add inbound TCP/80 from 0.0.0.0/0 |
| `/webhooks/web` returns 401 | You set `WEB_API_KEY` — the demo chat widget doesn't send it | Comment it out for the demo, or add credentials to the Devpost testing instructions |
| DashScope calls time out | `DASHSCOPE_API_KEY` wrong, or Qwen Cloud region-blocked from Singapore | Verify the key locally with `curl` first; if blocked, move to Alibaba Cloud's **Hong Kong** region (`cn-hongkong`) which has direct DashScope routing |
| Caddy fails to get cert | Domain DNS not pointing to the ECS IP yet, or TCP 80/443 not open | Wait for DNS propagation (`dig your.domain`), verify security group |

---

## 9 · Post-submission cleanup

After winner announcement (August 7) or when you're done demoing:

1. Console → ECS → Instances → select `maindesk-prod` → **Stop** (billing stops for compute; disk still bills).
2. To fully stop billing: **Release** the instance and the public IP.
3. Voucher-based charges do not refund but future charges stop.

---

## Files added by this deploy

- `docker-compose.prod.yml` — prod overlay: Caddy TLS proxy, private Postgres port, no n8n by default
- `deploy/Caddyfile` — Let's Encrypt-ready reverse proxy config with IP-only fallback
- `deploy/bootstrap.sh` — idempotent server bootstrap script
- `docs/DEPLOY_ALIBABA_ECS.md` — this file

Everything is in the repo — the ECS box only needs to `curl` the bootstrap script and go.
