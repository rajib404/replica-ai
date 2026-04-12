#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────
# Replica AI — backup script
#
# Backs up:
#   - PostgreSQL via pg_dump (compressed, in postgres container)
#   - Qdrant via snapshot API
#   - api/ai storage volumes via rsync
#
# Retention: BACKUP_RETENTION_DAYS (default 30) days, then pruned.
# Optional: rclone copy to BACKUP_RCLONE_REMOTE if set.
#
# Usage: ./scripts/backup.sh
#   Reads .env.production from the script's parent directory.
#   Intended to run as root via cron.
# ─────────────────────────────────────────────────────────

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
COMPOSE_FILE="$REPO_ROOT/docker-compose.prod.yml"
ENV_FILE="$REPO_ROOT/.env.production"

if [[ ! -f "$ENV_FILE" ]]; then
    echo "ERROR: $ENV_FILE not found" >&2
    exit 1
fi

# shellcheck disable=SC1090
set -a; source "$ENV_FILE"; set +a

BACKUP_DIR="${BACKUP_DIR:-/var/backups/replica-ai}"
RETENTION="${BACKUP_RETENTION_DAYS:-30}"
TIMESTAMP="$(date -u +%Y%m%d-%H%M)"
RCLONE_REMOTE="${BACKUP_RCLONE_REMOTE:-}"

PG_DIR="$BACKUP_DIR/postgres"
QDRANT_DIR="$BACKUP_DIR/qdrant"
API_STORAGE_DIR="$BACKUP_DIR/api_storage"
AI_STORAGE_DIR="$BACKUP_DIR/ai_storage"
LOG_PREFIX="[backup $TIMESTAMP]"

mkdir -p "$PG_DIR" "$QDRANT_DIR" "$API_STORAGE_DIR" "$AI_STORAGE_DIR"

log() { echo "$LOG_PREFIX $*"; }
fail() { echo "$LOG_PREFIX ERROR: $*" >&2; exit 1; }

dc() {
    docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" "$@"
}

# ─── 1. PostgreSQL ───────────────────────────────────────
log "Starting PostgreSQL dump…"
PG_DUMP_FILE="$PG_DIR/${POSTGRES_DB}_${TIMESTAMP}.sql.gz"

dc exec -T -e PGPASSWORD="$POSTGRES_PASSWORD" postgres \
    pg_dump \
        --username="$POSTGRES_USER" \
        --dbname="$POSTGRES_DB" \
        --no-owner \
        --no-acl \
        --clean \
        --if-exists \
        --format=plain \
    | gzip -9 > "$PG_DUMP_FILE.tmp"

mv "$PG_DUMP_FILE.tmp" "$PG_DUMP_FILE"
PG_SIZE=$(du -h "$PG_DUMP_FILE" | cut -f1)
log "PostgreSQL dump complete: $PG_DUMP_FILE ($PG_SIZE)"

# ─── 2. Qdrant ───────────────────────────────────────────
log "Starting Qdrant snapshots…"
COLLECTIONS=$(dc exec -T qdrant \
    sh -c 'wget -q -O - http://localhost:6333/collections' \
    | grep -o '"name":"[^"]*"' \
    | cut -d'"' -f4 || true)

if [[ -z "$COLLECTIONS" ]]; then
    log "No Qdrant collections to back up"
else
    for col in $COLLECTIONS; do
        log "Snapshotting Qdrant collection: $col"
        SNAPSHOT_NAME=$(dc exec -T qdrant \
            sh -c "wget -q -O - --post-data='' http://localhost:6333/collections/$col/snapshots" \
            | grep -o '"name":"[^"]*"' | head -1 | cut -d'"' -f4)
        if [[ -n "$SNAPSHOT_NAME" ]]; then
            DST="$QDRANT_DIR/${col}_${TIMESTAMP}.snapshot"
            dc exec -T qdrant cat "/qdrant/snapshots/$col/$SNAPSHOT_NAME" > "$DST.tmp"
            mv "$DST.tmp" "$DST"
            QSIZE=$(du -h "$DST" | cut -f1)
            log "Saved $DST ($QSIZE)"
        fi
    done
fi

# ─── 3. Storage volumes (rsync) ──────────────────────────
log "Syncing storage volumes…"

# Create timestamped rsync directory using --link-dest for hardlinked snapshots
sync_volume() {
    local volume_name="$1"
    local dst_root="$2"
    local prev_link
    prev_link="$(ls -1dt "$dst_root"/*/ 2>/dev/null | head -1 || true)"
    local target="$dst_root/$TIMESTAMP"
    mkdir -p "$target"

    # Use a temporary alpine container to read from the named volume
    docker run --rm \
        -v "${volume_name}:/src:ro" \
        -v "$dst_root:/dst" \
        alpine:3.19 \
        sh -c "apk add --quiet rsync >/dev/null && rsync -a --delete \
            ${prev_link:+--link-dest=/dst/$(basename "$prev_link")} \
            /src/ /dst/$TIMESTAMP/"
}

# Map service name → volume name (must match docker-compose.prod.yml)
sync_volume "replica-ai_api_storage" "$API_STORAGE_DIR" || log "WARN: api_storage rsync failed"
sync_volume "replica-ai_ai_storage"  "$AI_STORAGE_DIR"  || log "WARN: ai_storage rsync failed"

# ─── 4. Retention ────────────────────────────────────────
log "Pruning backups older than $RETENTION days…"
find "$PG_DIR"     -type f -name '*.sql.gz'    -mtime "+$RETENTION" -print -delete || true
find "$QDRANT_DIR" -type f -name '*.snapshot'  -mtime "+$RETENTION" -print -delete || true
find "$API_STORAGE_DIR" -mindepth 1 -maxdepth 1 -type d -mtime "+$RETENTION" -print -exec rm -rf {} + || true
find "$AI_STORAGE_DIR"  -mindepth 1 -maxdepth 1 -type d -mtime "+$RETENTION" -print -exec rm -rf {} + || true

# ─── 5. Offsite copy (optional) ──────────────────────────
if [[ -n "$RCLONE_REMOTE" ]]; then
    if command -v rclone >/dev/null 2>&1; then
        log "Uploading to rclone remote: $RCLONE_REMOTE"
        rclone copy "$BACKUP_DIR" "$RCLONE_REMOTE:replica-ai-backups/" \
            --quiet --transfers 4 --checkers 8 || log "WARN: rclone copy failed"
    else
        log "WARN: BACKUP_RCLONE_REMOTE is set but rclone is not installed"
    fi
fi

log "Backup complete."
