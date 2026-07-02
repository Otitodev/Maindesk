# CI/CD setup — auto-deploy to Alibaba Cloud ECS

**One-time setup, then every merge to `main` deploys automatically.** Workflow lives at `.github/workflows/deploy.yml`.

## What it does

On every push to `main` (or manual trigger from the Actions tab):

1. SSHs to the ECS box as `root`
2. `git pull` on `/opt/maindesk`
3. `docker compose -f docker-compose.prod.yml up -d --build`
4. Polls `http://localhost/health` for 90 seconds
5. On success: prints container status and exits 0
6. On failure: dumps the last 80 log lines and exits 1 (deploy shows red in GitHub UI)

Concurrency: if a second push lands while a deploy is in flight, the newer run queues and the older one finishes first. No `docker compose up` races.

---

## One-time setup (~10 min)

### 1. Generate a deploy-only SSH key pair

**On your laptop** — separate from your personal `maindesk-key-*.pem` so you can revoke it independently:

```powershell
ssh-keygen -t ed25519 -N '""' -f "$HOME\.ssh\maindesk-deploy" -C "github-actions-deploy@maindesk"
```

That creates two files:
- `~/.ssh/maindesk-deploy` (private key — goes into GitHub secret)
- `~/.ssh/maindesk-deploy.pub` (public key — goes onto the server)

### 2. Authorize the deploy key on the ECS box

Copy the **public** key contents:

```powershell
Get-Content "$HOME\.ssh\maindesk-deploy.pub" | Set-Clipboard
```

SSH into the box and append it:

```bash
ssh -i C:\Users\DELL\.ssh\maindesk-key-20260702182156.pem root@8.219.246.88
```

On the ECS box:
```bash
mkdir -p /root/.ssh
chmod 700 /root/.ssh
echo "PASTE_THE_PUBLIC_KEY_HERE" >> /root/.ssh/authorized_keys
chmod 600 /root/.ssh/authorized_keys
```

Verify: log out, then test from your laptop with the deploy key:
```powershell
ssh -i "$HOME\.ssh\maindesk-deploy" root@8.219.246.88 "hostname && date"
```

If that succeeds, the deploy key works.

### 3. Open port 22 to the world (for GitHub Actions runners)

GitHub-hosted runners use a large, rotating pool of IPs — impractical to allowlist. Standard practice is to open port 22 to `0.0.0.0/0` and rely on key-only SSH auth (which is the default on this box; password auth was never enabled).

```powershell
aliyun ecs AuthorizeSecurityGroup --RegionId ap-southeast-1 --SecurityGroupId sg-t4n8b7kbgfoy3afwm6u6 --IpProtocol tcp --PortRange 22/22 --SourceCidrIp 0.0.0.0/0
```

**Security note**: with password auth disabled, the practical risk is log noise from brute-force attempts, not compromise. For extra defense-in-depth later, install `fail2ban`:
```bash
apt-get install -y fail2ban && systemctl enable --now fail2ban
```

### 4. Add the secrets to GitHub

Go to the repo's **Settings → Secrets and variables → Actions → New repository secret**. Add these two:

| Secret name | Value |
|---|---|
| `ECS_HOST` | `8.219.246.88` |
| `ECS_SSH_KEY` | Full contents of `~/.ssh/maindesk-deploy` (including `-----BEGIN OPENSSH PRIVATE KEY-----` and `-----END OPENSSH PRIVATE KEY-----` lines) |

Copy the private key with:
```powershell
Get-Content "$HOME\.ssh\maindesk-deploy" -Raw | Set-Clipboard
```

Paste directly into the GitHub secret input.

### 5. First deploy

Push any change to `main` (or hit **Actions → Deploy to ECS → Run workflow** for a dry run). Watch the deploy in the Actions tab.

Expected: green checkmark within ~2 minutes. First run is slower because Docker layers rebuild from scratch.

---

## Verifying it works

**GitHub side:**
1. Repo → **Actions** tab
2. Latest "Deploy to ECS" run should be green
3. Click into it → expand the SSH step → see the last few log lines from the box

**Server side:**
```bash
docker compose -f docker-compose.prod.yml ps
git -C /opt/maindesk log --oneline -3
```

Should show all containers `Up (healthy)` and the latest commit SHA matching `main`.

**Live check:**
```powershell
curl.exe https://maindesk.otito.site/health
```

---

## Manual redeploy (if you need it)

Two ways to redeploy without a code change:

**From GitHub** (recommended):
- Repo → Actions → "Deploy to ECS" → **Run workflow** → main → Run

**From the box** (if GitHub Actions is down):
```bash
cd /opt/maindesk
git pull
docker compose -f docker-compose.prod.yml up -d --build
```

---

## Rollback

The workflow deploys whatever `main` currently points at. To roll back:

```bash
# On your laptop
git revert <bad-commit-sha>
git push origin main
```

Deploy triggers automatically on the revert. Full round-trip is under 3 minutes.

For a fast-and-dirty rollback (skip the revert commit):
```bash
# On the ECS box
cd /opt/maindesk
git reset --hard <last-known-good-sha>
docker compose -f docker-compose.prod.yml up -d --build
```

But that leaves `main` and the deployed code out of sync — the next deploy from GitHub will bring back the bad code. Always prefer the git-revert path.

---

## Cost

**Free.** GitHub Actions gives 2,000 minutes/month for private repos on the free plan; each deploy takes ~2 min. You'd need 1,000 deploys/month to hit the cap.

---

## What's deliberately not here

- **Tests before deploy** — could add a `test` job that runs `pytest` and blocks the deploy on failure. Fine for post-hackathon; the tests are already run locally before push, and adding it here doubles the deploy time. If we add it, the workflow becomes:
  ```yaml
  jobs:
    test:  # new job — pytest + eval
    deploy:
      needs: test  # only runs if tests pass
  ```
- **Docker image cache** — the workflow rebuilds the image every deploy. For a 3-service compose file this is ~90 seconds. Post-hackathon: push to Alibaba Container Registry and pull instead of build.
- **Multi-environment** (staging/prod split) — single ECS box, single main branch, single deploy target. Fine for the hackathon.
