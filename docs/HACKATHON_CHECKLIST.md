# Qwen Cloud Hackathon — Remaining Checklist

**Track 4: Autopilot Agent** · Submission deadline: **July 9, 2026 @ 2:00 pm Pacific** (7 days)

Judging weights: Innovation & AI Creativity 30% · Technical Depth 30% · Problem Value 25% · Presentation 15%.

---

## 🔴 CRITICAL — hard requirements from the rules

Miss any of these and the submission fails Stage One or gets disqualified.

- [ ] **Deploy backend to Alibaba Cloud.** Rules: *"You must demonstrate that the backend is running on Alibaba Cloud."* Options in priority order:
  - **Function Compute (FC)** — cheapest, cold-start hit acceptable for demo
  - **ECS small instance** — always-warm, runs `docker-compose.yml` unchanged
  - **Serverless App Engine (SAE)** — middle ground
  - Point demo URL + landing page CTA at the deployed instance.
- [ ] **`LICENSE` file at repo root, visible on GitHub's repo header.** Current repo has MIT via commit `18e603c` — verify it's still there and detectable.
- [ ] **Track selection = Track 4 (Autopilot Agent)** in the Devpost form. Not automatic.
- [ ] **Architecture diagram linked from the Devpost submission** (not just the repo). Use `docs/architecture.png`.
- [ ] **Demo video ≤ 3:00**, uploaded to YouTube / Vimeo / Youku, public. See `DEMO_SCRIPT.md`.
- [ ] **Proof-of-Alibaba-Cloud file link** — pick a file that demonstrates Qwen Cloud / DashScope usage (e.g., `app/agents/qwen_client.py`) and paste that GitHub blob URL into the Devpost "proof of deployment" field.
- [ ] **Testing instructions** with credentials if any auth is enabled on the deployed backend. Simplest: leave `WEB_API_KEY` unset on the demo instance so `/chat` works for judges out of the box.
- [ ] **Purge or accept** `2340000000000` in git history. Recent commits already swapped to placeholder, but old history still carries it. Either:
  - `git filter-repo --replace-text expressions.txt` before submission, OR
  - Document the placeholder swap and accept the historical presence.

## 🟡 HIGH VALUE — score boosters within the 7-day window

Direct impact on the 30% Innovation and 15% Presentation weights.

- [ ] **Write and publish blog post** (~800 words on Dev.to or Medium) covering:
  - The LangGraph orchestrator + Postgres checkpoint architecture
  - Multilingual pgvector recall with decay re-ranking
  - Webhook auth modes + outbound secret redaction
  - Multi-channel parity (WhatsApp + email + web + voice + `/chat`)
  - Extra prize: **$500 + $500 credits** for Top 10 Blog Post Award.
  - Include the blog URL **inside the Devpost submission** (rules require it there, not just linked from the repo).
- [ ] **Draft Devpost submission text** — reuse `README.md` intro + Chinese lede. Cover:
  - What problem it solves (clinic front-desk load, after-hours coverage)
  - Why it matters (staff burnout, missed appointments, non-English patients)
  - Tech stack (Qwen-Plus, Qwen-Turbo, text-embedding-v3, all via DashScope)
  - Multi-channel architecture (five channels through one orchestrator)
  - What's next
- [ ] **Rerun `python -m evals.run_intent_eval`** with the 33 cases (30 English + 3 Chinese) and update README's stale `100% (30/30)` claim to whatever the new number is. Keep it honest.
- [ ] **Verify `hello@maindesk.ai` mailbox** actually exists or points somewhere. All landing CTAs go there.
- [ ] **Open the PR** at [github.com/Otitodev/healthdesk-ai/compare/main...claude/landing-page-review-r3qewf](https://github.com/Otitodev/healthdesk-ai/compare/main...claude/landing-page-review-r3qewf) and merge before submission so `main` reflects the current state.

## 🟢 NICE TO HAVE — only if the critical path is clear by July 5

Stretch. Skip without regret.

- [ ] **Expose tool layer as an MCP server** and mention it in the submission. Rules explicitly cite *"MCP integrations"* under Innovation.
- [ ] **Wire landing page "See it live →" CTA to `/chat`** — one-line edit in `index.html`.
- [ ] **Add `GET /chat/patients` helper + "Demo as..." dropdown** in the `/chat` widget so judges can trigger the memory-recall path from Adaeze or 李伟's context (~20 lines).
- [ ] **Second-language voice demo clip** — 20 sec of Mandarin voice roundtrip on the demo video.
- [ ] **Post launch on X and one relevant subreddit** — supports "scalability potential / community potential" on the 25% Problem Value axis.

---

## Submission-day final pass

Run this in order on July 9 morning.

1. `git status` — clean tree on `main`
2. `python -m pytest` — all green
3. `python -m evals.run_intent_eval` — record the number
4. Deployed backend `/health` returns 200
5. Deployed `/chat` sends a message and gets a reply
6. Deployed `/webhooks/web` accepts a Chinese message and replies in Chinese
7. Demo video plays end-to-end on Vimeo/YouTube (mobile browser + incognito)
8. Devpost form: all 6 mandatory fields filled, Track 4 selected, blog URL pasted, testing instructions include no-auth note
9. Screenshot the submitted state before the 2:00 pm PT lockout

---

## Post-submission

- Set inbox reminder for **early August 2026** — winner affidavit is required within **10 business days** of forms being sent, or the prize is forfeit.
- Prize delivery is **within 60 days** of returning the affidavit.
- W-9 (US) or W-8BEN (non-US) required for tax reporting.
