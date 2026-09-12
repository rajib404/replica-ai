#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────
# Replica AI — one-click deployment
#
# Bootstraps a fresh Ubuntu 22.04 server:
#   - Installs Docker + Compose plugin
#   - Generates .env.production with random secrets
#   - Builds images
#   - Brings up the stack with HTTP first
#   - Runs certbot to obtain TLS cert
#   - Reloads nginx with HTTPS enabled
#   - Runs initial database migrations
#
# Usage:
#   sudo ./scripts/deploy.sh --domain replica.example.com --email admin@example.com
#
# Idempotent: re-running will skip steps that are already done.
# ─────────────────────────────────────────────────────────

set -euo pipefail

DOMAIN=""
EMAIL=""
NON_INTERACTIVE=0

usage() {
    cat <<EOF
Usage: $0 --domain <domain> --email <email> [--non-interactive]

  --domain DOMAIN          Public hostname (e.g. replica.example.com)
  --email  EMAIL           Email address for Let's Encrypt registration
  --non-interactive        Don't prompt for confirmation
  -h, --help               Show this help message
EOF
    exit 1
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --domain)         DOMAIN="$2"; shift 2 ;;
        --email)          EMAIL="$2"; shift 2 ;;
        --non-interactive) NON_INTERACTIVE=1; shift ;;
        -h|--help)        usage ;;
        *) echo "Unknown argument: $1" >&2; usage ;;
    esac
done

[[ -n "$DOMAIN" && -n "$EMAIL" ]] || usage

if [[ $EUID -ne 0 ]]; then
    echo "ERROR: must run as root (use sudo)" >&2
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
COMPOSE_FILE="$REPO_ROOT/docker-compose.prod.yml"
SMALL_COMPOSE_FILE="$REPO_ROOT/docker-compose.prod.small.yml"
ENV_FILE="$REPO_ROOT/.env.production"
ENV_TEMPLATE="$REPO_ROOT/.env.production.example"
NGINX_CONF="$REPO_ROOT/nginx/conf.d/replica-ai.conf"
HTTPS_TEMPLATE="$REPO_ROOT/nginx/https.conf.template"

log()  { echo "[deploy] $*"; }
warn() { echo "[deploy] WARN: $*" >&2; }
fail() { echo "[deploy] ERROR: $*" >&2; exit 1; }

# Below this, the default per-service memory caps in docker-compose.prod.yml
# (sized for the recommended 8GB+ host) would sum past the box's real RAM —
# layer on tightened caps instead of letting every container reach for its
# default ceiling at once. See docker-compose.prod.small.yml for details.
TOTAL_RAM_MB=$(awk '/MemTotal/ {print int($2/1024)}' /proc/meminfo)
if [[ $TOTAL_RAM_MB -lt 6000 ]]; then
    log "Detected ${TOTAL_RAM_MB}MB RAM — applying docker-compose.prod.small.yml resource caps"
    COMPOSE_ARGS=(-f "$COMPOSE_FILE" -f "$SMALL_COMPOSE_FILE")
else
    COMPOSE_ARGS=(-f "$COMPOSE_FILE")
fi
dc() { docker compose "${COMPOSE_ARGS[@]}" --env-file "$ENV_FILE" "$@"; }

confirm() {
    [[ $NON_INTERACTIVE -eq 1 ]] && return 0
    read -p "$1 [y/N] " answer
    [[ "$answer" =~ ^[Yy]$ ]] || fail "Aborted"
}

# ─── 0. Pre-flight ───────────────────────────────────────
log "Domain: $DOMAIN"
log "Email:  $EMAIL"
log "Repo:   $REPO_ROOT"

if ! grep -qi 'ubuntu' /etc/os-release; then
    warn "Not running on Ubuntu — proceeding anyway"
fi

confirm "Begin deployment?"

# ─── 1. Install Docker + Compose plugin ──────────────────
if command -v docker >/dev/null 2>&1; then
    log "Docker already installed: $(docker --version)"
else
    log "Installing Docker…"
    apt-get update -qq
    apt-get install -y -qq ca-certificates curl gnupg lsb-release
    install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
        | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    chmod a+r /etc/apt/keyrings/docker.gpg
    echo \
        "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
        https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" \
        > /etc/apt/sources.list.d/docker.list
    apt-get update -qq
    apt-get install -y -qq docker-ce docker-ce-cli containerd.io \
        docker-buildx-plugin docker-compose-plugin
    systemctl enable --now docker
    log "Docker installed: $(docker --version)"
fi

# ─── 2. Generate .env.production ─────────────────────────
gen_secret() { openssl rand -hex 32; }
gen_password() { openssl rand -base64 24 | tr -d '\n=+/' | head -c 24; }

if [[ -f "$ENV_FILE" ]]; then
    log ".env.production already exists — leaving in place"
else
    log "Generating .env.production…"
    [[ -f "$ENV_TEMPLATE" ]] || fail "Template not found: $ENV_TEMPLATE"

    cp "$ENV_TEMPLATE" "$ENV_FILE"

    POSTGRES_PASSWORD=$(gen_password)
    REDIS_PASSWORD=$(gen_password)
    JWT_SECRET=$(gen_secret)
    ENCRYPTION_KEY=$(openssl rand -hex 16)
    ENCRYPTION_MASTER=$(gen_secret)
    QDRANT_API_KEY=$(gen_secret)

    sed -i \
        -e "s|^DOMAIN=.*|DOMAIN=$DOMAIN|" \
        -e "s|^PUBLIC_BASE_URL=.*|PUBLIC_BASE_URL=https://$DOMAIN|" \
        -e "s|^LETSENCRYPT_EMAIL=.*|LETSENCRYPT_EMAIL=$EMAIL|" \
        -e "s|^NEXT_PUBLIC_API_URL=.*|NEXT_PUBLIC_API_URL=https://$DOMAIN|" \
        -e "s|^POSTGRES_PASSWORD=.*|POSTGRES_PASSWORD=$POSTGRES_PASSWORD|" \
        -e "s|^REDIS_PASSWORD=.*|REDIS_PASSWORD=$REDIS_PASSWORD|" \
        -e "s|^JWT_SECRET_KEY=.*|JWT_SECRET_KEY=$JWT_SECRET|" \
        -e "s|^ENCRYPTION_KEY=.*|ENCRYPTION_KEY=$ENCRYPTION_KEY|" \
        -e "s|^ENCRYPTION_MASTER_KEY=.*|ENCRYPTION_MASTER_KEY=$ENCRYPTION_MASTER|" \
        -e "s|^QDRANT_API_KEY=.*|QDRANT_API_KEY=$QDRANT_API_KEY|" \
        "$ENV_FILE"

    chown root:root "$ENV_FILE"
    chmod 600 "$ENV_FILE"
    log "Wrote $ENV_FILE (mode 600, root-owned)"

    # ── Pick an Ollama default model based on host RAM ──
    # (TOTAL_RAM_MB was already computed above, for the compose-caps decision)
    if   [[ $TOTAL_RAM_MB -ge 16000 ]]; then OLLAMA_MODEL="mistral:7b-instruct"
    elif [[ $TOTAL_RAM_MB -ge 12000 ]]; then OLLAMA_MODEL="qwen2.5:3b"
    elif [[ $TOTAL_RAM_MB -ge 6000  ]]; then OLLAMA_MODEL="gemma2:2b"
    else                                     OLLAMA_MODEL="qwen2.5:1.5b"
    fi
    log "Detected ${TOTAL_RAM_MB}MB RAM → OLLAMA_DEFAULT_MODEL=$OLLAMA_MODEL"
    sed -i "s|^OLLAMA_DEFAULT_MODEL=.*|OLLAMA_DEFAULT_MODEL=$OLLAMA_MODEL|" "$ENV_FILE"

    # ── Trim gunicorn worker counts on small hosts ──
    # api imports several heavy ML libraries at startup (resemblyzer →
    # torch, face_recognition → dlib, faster-whisper → ctranslate2);
    # each extra worker duplicates that whole import footprint, and the
    # small-host memory caps in docker-compose.prod.small.yml assume a
    # single worker. Same threshold as the compose-file selection above.
    if [[ $TOTAL_RAM_MB -lt 6000 ]]; then
        log "Small host detected — setting GUNICORN_WORKERS=1, AI_GUNICORN_WORKERS=1"
        sed -i \
            -e "s|^GUNICORN_WORKERS=.*|GUNICORN_WORKERS=1|" \
            -e "s|^AI_GUNICORN_WORKERS=.*|AI_GUNICORN_WORKERS=1|" \
            "$ENV_FILE"
    fi

    cat <<EOF

  ╔═══════════════════════════════════════════════════════════╗
  ║         IMPORTANT — BACK UP THESE SECRETS NOW              ║
  ║                                                             ║
  ║   ENCRYPTION_MASTER_KEY: $ENCRYPTION_MASTER
  ║                                                             ║
  ║   If you lose this key, all encrypted data is gone.         ║
  ║   Save it in a password manager AND a sealed envelope.      ║
  ╚═══════════════════════════════════════════════════════════╝

EOF
    confirm "Have you saved the master key?"
fi

# Symlink .env -> .env.production so plain `docker compose` commands
# (without --env-file) also pick up the production environment.
if [[ ! -L "$REPO_ROOT/.env" || "$(readlink "$REPO_ROOT/.env")" != ".env.production" ]]; then
    log "Creating .env symlink → .env.production"
    rm -f "$REPO_ROOT/.env"
    ln -s .env.production "$REPO_ROOT/.env"
fi

# Source for use below
# shellcheck disable=SC1090
set -a; source "$ENV_FILE"; set +a

# ─── 3. Render nginx config with the real domain ─────────
log "Rendering nginx config for $DOMAIN…"
sed -i.bak "s|{{DOMAIN}}|$DOMAIN|g" "$NGINX_CONF"
rm -f "${NGINX_CONF}.bak"

# ─── 4. Initial bring-up (HTTP only, for ACME challenge) ─
log "Building images (this may take several minutes)…"
dc build

log "Starting infrastructure services…"
dc up -d \
    postgres redis qdrant ollama piper pgbouncer

log "Waiting for postgres to become healthy…"
for i in {1..30}; do
    if dc exec -T postgres \
        pg_isready -U "$POSTGRES_USER" >/dev/null 2>&1; then
        break
    fi
    sleep 2
done

# ─── 5. Run database migrations ──────────────────────────
log "Running Prisma migrations…"
if [[ -d "$REPO_ROOT/packages/db" ]]; then
    docker run --rm \
        --network "$(basename "$REPO_ROOT")_replica_internal" \
        -v "$REPO_ROOT:/workspace" \
        -w /workspace/packages/db \
        -e DATABASE_URL="postgresql://${POSTGRES_USER}:${POSTGRES_PASSWORD}@postgres:5432/${POSTGRES_DB}" \
        node:20-alpine \
        sh -c "npx --yes prisma@latest migrate deploy" \
        || warn "Prisma migrations failed — review and rerun manually"
fi

# ─── 6. Bring up app services + nginx (HTTP only) ────────
log "Starting application services and nginx (HTTP)…"
dc up -d ai api web

# Temporarily start nginx with HTTP-only listener so certbot can answer challenge
log "Starting nginx with HTTP listener…"
dc up -d nginx

log "Waiting for nginx to accept connections on port 80…"
NGINX_READY=0
for i in {1..30}; do
    if curl -fsS "http://localhost/healthz" >/dev/null 2>&1; then
        NGINX_READY=1
        break
    fi
    sleep 1
done
[[ $NGINX_READY -eq 1 ]] || fail "nginx never answered on port 80 — check: docker compose -f $COMPOSE_FILE logs nginx"

# ─── 7. Obtain TLS certificate ───────────────────────────
CERT_PATH="/etc/letsencrypt/live/$DOMAIN/fullchain.pem"

# Renders nginx/https.conf.template (kept out of conf.d/ so nginx never
# loads it before a cert exists — see the file's header comment) with
# {{DOMAIN}} substituted. Written to the HOST path, not via `dc exec` —
# nginx/conf.d is bind-mounted `:ro` into the container, so the container
# can't write there; the host copy is what the mount actually serves, and
# it persists across restarts/updates same as replica-ai.conf already does.
# Safe to call only once CERT_PATH is confirmed present.
enable_https_vhost() {
    log "Enabling HTTPS vhost for $DOMAIN…"
    sed "s|{{DOMAIN}}|$DOMAIN|g" "$HTTPS_TEMPLATE" \
        > "$REPO_ROOT/nginx/conf.d/replica-ai-ssl.conf"
    dc exec -T nginx nginx -t \
        || fail "generated HTTPS nginx config is invalid — check nginx/https.conf.template"
    dc exec -T nginx nginx -s reload
}

if dc exec -T certbot \
        test -f "$CERT_PATH" 2>/dev/null; then
    log "TLS certificate already exists for $DOMAIN — skipping certbot"
    enable_https_vhost
else
    log "Requesting Let's Encrypt certificate for $DOMAIN and www.$DOMAIN…"
    if dc run --rm \
        --entrypoint "" certbot \
        certbot certonly \
            --webroot --webroot-path=/var/www/certbot \
            --email "$EMAIL" \
            --agree-tos --no-eff-email \
            -d "$DOMAIN" -d "www.$DOMAIN"; then
        :
    else
        # A cert request naming multiple hosts fails as a whole if any one
        # of them doesn't resolve to this server yet — retry bare-domain-only
        # rather than blocking the entire deploy on a missing www DNS record.
        warn "certbot failed for $DOMAIN + www.$DOMAIN — retrying with $DOMAIN only (add a DNS record for www.$DOMAIN and rerun to cover it)"
        dc run --rm \
            --entrypoint "" certbot \
            certbot certonly \
                --webroot --webroot-path=/var/www/certbot \
                --email "$EMAIL" \
                --agree-tos --no-eff-email \
                -d "$DOMAIN" \
            || fail "certbot failed — DNS for $DOMAIN must point to this server"
    fi

    enable_https_vhost
fi

# ─── 8. Start certbot renewal loop ───────────────────────
dc up -d certbot

# ─── 8b. Pull the default Ollama model ───────────────────
log "Pulling Ollama model: $OLLAMA_DEFAULT_MODEL (this can take several minutes)…"
dc exec -T ollama \
    ollama pull "$OLLAMA_DEFAULT_MODEL" \
    || warn "Ollama model pull failed — run manually: docker compose exec ollama ollama pull $OLLAMA_DEFAULT_MODEL"

# ─── 9. Health check ─────────────────────────────────────
log "Waiting for services to settle…"
sleep 10

dc ps

# Check the API's detailed health endpoint and warn on degraded services
log "Checking detailed health…"
HEALTH=$(dc exec -T api \
    curl -fsS http://localhost:8000/api/health/detailed 2>/dev/null || echo '{}')
echo "$HEALTH" | grep -q '"status":"ok"' \
    && log "✓ All services healthy" \
    || warn "Some services degraded — see /api/health/detailed"

cat <<EOF

  ╔═══════════════════════════════════════════════════════════╗
  ║                  ✓  Deployment complete                    ║
  ║                                                             ║
  ║   Site:       https://$DOMAIN
  ║   API:        https://$DOMAIN/api/health
  ║   Logs:       docker compose -f $COMPOSE_FILE logs -f
  ║   Backups:    add scripts/backup.sh to root crontab        ║
  ║   Monitoring: add scripts/monitor.sh to root crontab       ║
  ║                                                             ║
  ║   Don't forget to:                                          ║
  ║     - Point DNS A record for $DOMAIN
  ║       to this server's public IP                            ║
  ║     - sudo ufw enable (allow 80/tcp, 443/tcp, OpenSSH)     ║
  ╚═══════════════════════════════════════════════════════════╝

EOF
