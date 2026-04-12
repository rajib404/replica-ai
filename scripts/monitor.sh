#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────
# Replica AI — monitoring script
#
# Checks all services + disk space and alerts on failure via:
#   - Webhook (ALERT_WEBHOOK_URL)
#   - Email (ALERT_EMAIL, requires `mail` command)
#
# Designed to run from cron every 5 minutes:
#   */5 * * * * /opt/replica-ai/scripts/monitor.sh
#
# Exit codes:
#   0 = all healthy
#   1 = one or more services failed (alert sent)
#   2 = disk space critical
# ─────────────────────────────────────────────────────────

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
COMPOSE_FILE="$REPO_ROOT/docker-compose.prod.yml"
ENV_FILE="$REPO_ROOT/.env.production"

[[ -f "$ENV_FILE" ]] || { echo "ERROR: $ENV_FILE not found" >&2; exit 1; }

# shellcheck disable=SC1090
set -a; source "$ENV_FILE"; set +a

DISK_THRESHOLD="${DISK_ALERT_THRESHOLD:-80}"
ALERT_WEBHOOK_URL="${ALERT_WEBHOOK_URL:-}"
ALERT_EMAIL="${ALERT_EMAIL:-}"
HOSTNAME_=$(hostname -f 2>/dev/null || hostname)

failures=()

dc() {
    docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" "$@"
}

check() {
    local name="$1"
    shift
    if "$@" >/dev/null 2>&1; then
        return 0
    else
        failures+=("$name")
        return 1
    fi
}

# ─── Service checks ──────────────────────────────────────
check "nginx"     dc exec -T nginx     wget -q -O- http://localhost/healthz
check "web"       dc exec -T web       wget -q -O- http://localhost:3000/
check "api"       dc exec -T api       curl -fsS http://localhost:8000/health
check "ai"        dc exec -T ai        curl -fsS http://localhost:8100/health
check "postgres"  dc exec -T postgres  pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB"
check "redis"     dc exec -T redis     redis-cli -a "$REDIS_PASSWORD" ping
check "qdrant"    dc exec -T qdrant    sh -c 'wget -q -O- http://localhost:6333/healthz'
check "ollama"    dc exec -T ollama    sh -c 'ollama list'
check "pgbouncer" dc exec -T pgbouncer pg_isready -h localhost -p 6432

# ─── TLS certificate expiry ──────────────────────────────
if [[ -n "${DOMAIN:-}" ]]; then
    days_left=$(echo | openssl s_client -connect "$DOMAIN:443" -servername "$DOMAIN" 2>/dev/null \
        | openssl x509 -noout -enddate 2>/dev/null \
        | sed 's/notAfter=//' \
        | xargs -I{} date -d {} +%s 2>/dev/null \
        | awk -v now=$(date +%s) '{print int(($1 - now) / 86400)}')
    if [[ -n "$days_left" && "$days_left" -lt 14 ]]; then
        failures+=("tls_cert_expiring_in_${days_left}d")
    fi
fi

# ─── Disk space ──────────────────────────────────────────
disk_critical=0
disk_report=""
while read -r usage mount; do
    pct="${usage%\%}"
    if [[ "$pct" -ge "$DISK_THRESHOLD" ]]; then
        disk_report+="  - $mount at ${usage}\n"
        disk_critical=1
    fi
done < <(df -P / /var/lib/docker /var/backups 2>/dev/null | awk 'NR>1 {print $5, $6}')

if [[ $disk_critical -eq 1 ]]; then
    failures+=("disk_usage_above_${DISK_THRESHOLD}pct")
fi

# ─── Alert delivery ──────────────────────────────────────
if [[ ${#failures[@]} -eq 0 ]]; then
    echo "[monitor $(date -u +%FT%TZ)] all checks passed"
    exit 0
fi

timestamp=$(date -u +%FT%TZ)
subject="[Replica AI] $HOSTNAME_ — ${#failures[@]} check(s) failing"
body="Replica AI monitoring detected failures on $HOSTNAME_ at $timestamp:\n\n"
for f in "${failures[@]}"; do
    body+="  - $f\n"
done
if [[ -n "$disk_report" ]]; then
    body+="\nDisk usage:\n$disk_report"
fi

# Print to stderr (caught by cron mail or log)
printf "%b\n" "$body" >&2

# Webhook
if [[ -n "$ALERT_WEBHOOK_URL" ]]; then
    payload=$(printf '{"text":"%s","host":"%s","failures":%s}' \
        "$subject" "$HOSTNAME_" \
        "$(printf '%s\n' "${failures[@]}" | jq -R . | jq -s . 2>/dev/null || echo '[]')")
    curl -fsS -X POST -H 'Content-Type: application/json' \
        -d "$payload" \
        "$ALERT_WEBHOOK_URL" >/dev/null 2>&1 \
        || echo "[monitor] WARN: webhook delivery failed" >&2
fi

# Email
if [[ -n "$ALERT_EMAIL" ]] && command -v mail >/dev/null 2>&1; then
    printf "%b" "$body" | mail -s "$subject" "$ALERT_EMAIL"
fi

# Exit code: 2 if disk-only, 1 otherwise
if [[ $disk_critical -eq 1 && ${#failures[@]} -eq 1 ]]; then
    exit 2
fi
exit 1
