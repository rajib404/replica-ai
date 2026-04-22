#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────
# Replica AI — update script
#
# Pulls latest code, rebuilds containers, runs migrations,
# and performs a rolling restart of application services.
#
# Usage: sudo ./scripts/update.sh [--branch main]
# ─────────────────────────────────────────────────────────

set -euo pipefail

BRANCH="main"
SKIP_PULL=0
SKIP_MIGRATE=0

while [[ $# -gt 0 ]]; do
    case "$1" in
        --branch)        BRANCH="$2"; shift 2 ;;
        --skip-pull)     SKIP_PULL=1; shift ;;
        --skip-migrate)  SKIP_MIGRATE=1; shift ;;
        -h|--help)
            echo "Usage: $0 [--branch BRANCH] [--skip-pull] [--skip-migrate]"
            exit 0
            ;;
        *) echo "Unknown argument: $1" >&2; exit 1 ;;
    esac
done

if [[ $EUID -ne 0 ]]; then
    echo "ERROR: must run as root (use sudo)" >&2
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
COMPOSE_FILE="$REPO_ROOT/docker-compose.prod.yml"
ENV_FILE="$REPO_ROOT/.env.production"

log()  { echo "[update] $*"; }
warn() { echo "[update] WARN: $*" >&2; }
fail() { echo "[update] ERROR: $*" >&2; exit 1; }

[[ -f "$ENV_FILE" ]] || fail ".env.production not found — run deploy.sh first"

# shellcheck disable=SC1090
set -a; source "$ENV_FILE"; set +a

dc() {
    docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" "$@"
}

# ─── 1. Pull latest code ─────────────────────────────────
if [[ $SKIP_PULL -eq 0 ]]; then
    log "Fetching latest code on branch $BRANCH…"
    cd "$REPO_ROOT"
    git fetch origin "$BRANCH"
    PREV=$(git rev-parse HEAD)
    git checkout "$BRANCH"
    git pull --ff-only origin "$BRANCH"
    NEW=$(git rev-parse HEAD)

    if [[ "$PREV" == "$NEW" ]]; then
        log "Already up-to-date ($NEW)"
    else
        log "Updated: $PREV → $NEW"
    fi
fi

# ─── 2. Rebuild images ───────────────────────────────────
log "Rebuilding images…"
dc build --pull web api ai

# ─── 3. Run migrations ───────────────────────────────────
if [[ $SKIP_MIGRATE -eq 0 ]]; then
    log "Running database migrations…"
    if [[ -d "$REPO_ROOT/packages/db" ]]; then
        NET_PREFIX="$(basename "$REPO_ROOT")"
        MIGRATE_CID=$(docker create \
            -v "$REPO_ROOT:/workspace" \
            -w /workspace/packages/db \
            -e DATABASE_URL="postgresql://${POSTGRES_USER}:${POSTGRES_PASSWORD}@postgres:5432/${POSTGRES_DB}" \
            node:20-alpine \
            sh -c "npx --yes prisma@5 migrate deploy")
        docker network connect "${NET_PREFIX}_replica_internal" "$MIGRATE_CID"
        docker network connect "${NET_PREFIX}_replica_egress"   "$MIGRATE_CID"
        docker start -a "$MIGRATE_CID"
        MIGRATE_EXIT=$?
        docker rm "$MIGRATE_CID" >/dev/null 2>&1
        [[ $MIGRATE_EXIT -eq 0 ]] || fail "Migrations failed — aborting update"
    fi
fi

# ─── 4. Rolling restart ──────────────────────────────────
# Strategy: --no-deps + scale up the new container, wait for healthy,
# then docker compose up -d which gracefully replaces the old one.
rolling_restart() {
    local svc="$1"
    log "Rolling restart: $svc"

    # `up -d --force-recreate` recreates the container, but compose's
    # default behavior is start-then-stop which gives near-zero downtime
    # for stateless services like web/api/ai because nginx will retry
    # on the next health check.
    dc up -d --no-deps --force-recreate --remove-orphans "$svc"

    # Wait for the new container to become healthy
    log "Waiting for $svc to become healthy…"
    for i in {1..30}; do
        STATUS=$(dc ps --format json "$svc" 2>/dev/null | grep -o '"Health":"[^"]*"' | head -1 | cut -d'"' -f4 || echo "")
        if [[ "$STATUS" == "healthy" || "$STATUS" == "" ]]; then
            # Empty status means no healthcheck — assume OK
            log "$svc is up"
            return 0
        fi
        sleep 2
    done
    warn "$svc did not report healthy after 60s — check logs"
}

# Order: ai → api → web (downstream first)
rolling_restart ai
rolling_restart api
rolling_restart web

# Reload nginx config (in case it changed)
log "Reloading nginx…"
dc exec -T nginx nginx -t && dc exec -T nginx nginx -s reload || warn "nginx reload failed"

# ─── 5. Cleanup ──────────────────────────────────────────
log "Pruning dangling images…"
docker image prune -f >/dev/null

log "Update complete."
dc ps
