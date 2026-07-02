#!/usr/bin/env bash
# Bootstrap a fresh Alibaba Cloud ECS (Ubuntu 22.04 LTS) for MainDesk.
# Idempotent: safe to re-run. Root or sudo required.
set -euo pipefail

REPO_URL="${REPO_URL:-https://github.com/Otitodev/healthdesk-ai.git}"
CLONE_DIR="${CLONE_DIR:-/opt/maindesk}"
BRANCH="${BRANCH:-main}"

log() { printf "\033[1;36m[bootstrap]\033[0m %s\n" "$*"; }

if [ "$(id -u)" -ne 0 ]; then
	log "Re-executing under sudo…"
	exec sudo -E bash "$0" "$@"
fi

# ---------- 1. system packages ----------
log "apt update + base tools"
apt-get update -y
apt-get install -y --no-install-recommends ca-certificates curl gnupg git ufw

# ---------- 2. Docker Engine + compose plugin ----------
if ! command -v docker >/dev/null 2>&1; then
	log "Installing Docker Engine"
	install -m 0755 -d /etc/apt/keyrings
	curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
	chmod a+r /etc/apt/keyrings/docker.asc
	echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
		> /etc/apt/sources.list.d/docker.list
	apt-get update -y
	apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
	systemctl enable --now docker
else
	log "Docker already installed — skipping"
fi

# ---------- 3. host firewall (defence in depth; Alibaba security group is authoritative) ----------
log "Configuring ufw (80/tcp, 443/tcp, 22/tcp)"
ufw --force reset >/dev/null
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable

# ---------- 4. clone repo ----------
if [ ! -d "$CLONE_DIR/.git" ]; then
	log "Cloning $REPO_URL → $CLONE_DIR"
	git clone --branch "$BRANCH" "$REPO_URL" "$CLONE_DIR"
else
	log "Updating existing clone at $CLONE_DIR"
	git -C "$CLONE_DIR" fetch --all --prune
	git -C "$CLONE_DIR" checkout "$BRANCH"
	git -C "$CLONE_DIR" pull --ff-only
fi

# ---------- 5. .env prep ----------
if [ ! -f "$CLONE_DIR/.env" ]; then
	log ".env missing — copying from .env.example. YOU MUST FILL IT IN NEXT."
	cp "$CLONE_DIR/.env.example" "$CLONE_DIR/.env"
	cat <<-'EOF'

	  ┌───────────────────────────────────────────────────────────────┐
	  │  ACTION REQUIRED:                                             │
	  │  Edit /opt/maindesk/.env with real values before running     │
	  │  the compose up step. Minimum required:                       │
	  │                                                               │
	  │    DASHSCOPE_API_KEY=<your Qwen key>                          │
	  │    POSTGRES_USER=healthdesk                                   │
	  │    POSTGRES_PASSWORD=<generated>                              │
	  │    POSTGRES_DB=healthdesk                                     │
	  │    DATABASE_URL=postgresql://healthdesk:<pw>@postgres:5432/healthdesk │
	  │    STAFF_DASHBOARD_KEY=<generated>                            │
	  │    GATEWAY_PROXY_KEY=<generated>                              │
	  │    HEALTHDESK_ENV=production                                  │
	  │    DOMAIN=<your domain, e.g. maindesk.ai>   # blank = IP-only │
	  │    ACME_EMAIL=<your email for Let's Encrypt>                  │
	  │                                                               │
	  │  Then re-run this script with STEP=up to bring the stack up.  │
	  └───────────────────────────────────────────────────────────────┘

	EOF
	exit 0
fi

# ---------- 6. compose up ----------
log "Bringing up the stack (docker compose -f docker-compose.prod.yml up -d --build)"
cd "$CLONE_DIR"
docker compose -f docker-compose.prod.yml up -d --build

# ---------- 7. verify ----------
log "Waiting for /health…"
for i in $(seq 1 30); do
	if curl -fsS http://localhost/health >/dev/null 2>&1; then
		log "OK — MainDesk is live."
		log "  http://$(curl -s ifconfig.me)/health  → 200"
		log "  http://$(curl -s ifconfig.me)/chat    → chat widget"
		exit 0
	fi
	sleep 2
done

log "!! Backend did not become healthy in 60s. Check logs:"
log "   docker compose -f $CLONE_DIR/docker-compose.prod.yml logs --tail=100"
exit 1
