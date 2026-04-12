#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────
# Replica AI — restore script
#
# Usage: ./scripts/restore.sh <timestamp>
#   <timestamp> = YYYYMMDD-HHMM (matches a backup directory/file)
#
# Example: ./scripts/restore.sh 20260406-0230
#
# This will:
#   1. Stop api/ai/web (postgres + qdrant stay up)
#   2. Restore PostgreSQL from the .sql.gz dump
#   3. Restore Qdrant snapshots
#   4. Restore api/ai storage volumes via rsync
#   5. Restart all services
#
# THIS IS DESTRUCTIVE — current data will be replaced.
# ─────────────────────────────────────────────────────────

set -euo pipefail

if [[ $# -ne 1 ]]; then
    echo "Usage: $0 <timestamp>" >&2
    echo "Example: $0 20260406-0230" >&2
    exit 1
fi

TIMESTAMP="$1"
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
PG_DUMP="$BACKUP_DIR/postgres/${POSTGRES_DB}_${TIMESTAMP}.sql.gz"

log() { echo "[restore $TIMESTAMP] $*"; }
fail() { echo "[restore $TIMESTAMP] ERROR: $*" >&2; exit 1; }

dc() {
    docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" "$@"
}

# Sanity checks
if [[ ! -f "$PG_DUMP" ]]; then
    fail "PostgreSQL dump not found: $PG_DUMP"
fi

# ─── Confirmation ────────────────────────────────────────
echo
echo "  ╔═══════════════════════════════════════════════════════╗"
echo "  ║                   ⚠   WARNING                          ║"
echo "  ║                                                         ║"
echo "  ║   This will overwrite the current production data       ║"
echo "  ║   with the backup from $TIMESTAMP.                      ║"
echo "  ║                                                         ║"
echo "  ║   PostgreSQL, Qdrant, and storage volumes will all      ║"
echo "  ║   be replaced. This is NOT reversible.                  ║"
echo "  ╚═══════════════════════════════════════════════════════╝"
echo
read -p "Type 'RESTORE' to confirm: " confirm
[[ "$confirm" == "RESTORE" ]] || fail "Aborted"

# ─── 1. Stop application services ────────────────────────
log "Stopping api, ai, web…"
dc stop api ai web

# ─── 2. PostgreSQL restore ───────────────────────────────
log "Restoring PostgreSQL from $PG_DUMP…"
gunzip -c "$PG_DUMP" | dc exec -T -e PGPASSWORD="$POSTGRES_PASSWORD" postgres \
    psql --username="$POSTGRES_USER" --dbname="$POSTGRES_DB"
log "PostgreSQL restore complete."

# ─── 3. Qdrant restore ───────────────────────────────────
QDRANT_DIR="$BACKUP_DIR/qdrant"
SNAPSHOTS=$(find "$QDRANT_DIR" -name "*_${TIMESTAMP}.snapshot" 2>/dev/null || true)

if [[ -n "$SNAPSHOTS" ]]; then
    for snapshot in $SNAPSHOTS; do
        filename=$(basename "$snapshot")
        col="${filename%_${TIMESTAMP}.snapshot}"
        log "Restoring Qdrant collection: $col"

        # Copy snapshot into qdrant container
        TMP_NAME="restore_${TIMESTAMP}.snapshot"
        dc exec -T qdrant mkdir -p "/qdrant/snapshots/$col"
        cat "$snapshot" | dc exec -T qdrant tee "/qdrant/snapshots/$col/$TMP_NAME" > /dev/null

        # Trigger restore
        dc exec -T qdrant sh -c \
            "wget -q -O - --post-data='{\"location\":\"/qdrant/snapshots/$col/$TMP_NAME\",\"priority\":\"snapshot\"}' \
             --header='Content-Type: application/json' \
             http://localhost:6333/collections/$col/snapshots/recover" > /dev/null
    done
else
    log "No Qdrant snapshots found for $TIMESTAMP — skipping vector restore"
fi

# ─── 4. Storage volumes ──────────────────────────────────
restore_volume() {
    local volume_name="$1"
    local backup_root="$2"
    local src="$backup_root/$TIMESTAMP"

    if [[ ! -d "$src" ]]; then
        log "No backup directory at $src — skipping"
        return
    fi

    log "Restoring volume $volume_name from $src…"
    docker run --rm \
        -v "${volume_name}:/dst" \
        -v "$backup_root:/backup:ro" \
        alpine:3.19 \
        sh -c "apk add --quiet rsync >/dev/null && rsync -a --delete /backup/$TIMESTAMP/ /dst/"
}

restore_volume "replica-ai_api_storage" "$BACKUP_DIR/api_storage" || log "WARN: api_storage restore failed"
restore_volume "replica-ai_ai_storage"  "$BACKUP_DIR/ai_storage"  || log "WARN: ai_storage restore failed"

# ─── 5. Restart services ─────────────────────────────────
log "Restarting application services…"
dc up -d api ai web

log "Waiting for services to become healthy…"
sleep 10

dc ps

log "Restore complete."
