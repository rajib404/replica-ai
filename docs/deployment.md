# Production Deployment Guide

This document covers deploying Replica AI to a production server (Ubuntu 22.04+),
secrets management, backup/restore, and monitoring.

---

## 1. Architecture Overview

```
                ┌──────────────────────────────────────┐
                │             Internet                  │
                └──────────────┬───────────────────────┘
                               │ 80, 443
                ┌──────────────▼───────────────────────┐
                │   nginx (only public service)         │
                │   TLS termination, rate limiting      │
                └──────────────┬───────────────────────┘
                               │
              ┌────────────────┼────────────────┐
              │                │                │
        ┌─────▼─────┐  ┌───────▼────────┐  ┌───▼──────┐
        │   web     │  │      api        │  │  /ws/*   │
        │ Next.js   │  │  FastAPI :8000  │  │ websocket│
        │  :3000    │  │  gunicorn x4    │  └──────────┘
        └───────────┘  └────────┬────────┘
                                │
        ┌───────────────────────┼───────────────────────────┐
        │                       │                           │
   ┌────▼─────┐    ┌────────────▼─────┐    ┌────────────────▼┐
   │ pgbouncer│    │  ai (FastAPI :8100│    │ redis  qdrant  │
   │   :6432  │    │  gunicorn x2)    │    │ ollama piper   │
   └────┬─────┘    └──────────────────┘    └────────────────┘
        │
   ┌────▼─────┐
   │ postgres │
   │  :5432   │
   └──────────┘
```

All services live on internal Docker networks. Only `nginx` is exposed (80, 443).

---

## 2. One-Click Deployment

On a fresh Ubuntu 22.04 server (recommended: 4 vCPU, 8 GB RAM, 80 GB disk):

```bash
# 1. SSH in as a sudo-capable user
ssh ubuntu@your-server.example.com

# 2. Clone the repo
sudo mkdir -p /opt && sudo chown $USER /opt
git clone https://github.com/yourorg/replica-ai.git /opt/replica-ai
cd /opt/replica-ai

# 3. Run the deploy script
sudo ./scripts/deploy.sh \
    --domain replica.example.com \
    --email  admin@example.com
```

The script will:
1. Install Docker + Compose plugin if missing
2. Generate `.env.production` with random secrets (saved to `/opt/replica-ai/.env.production`)
3. Build all images
4. Bring up the stack without TLS (HTTP only) so certbot can solve the challenge
5. Run certbot for the first cert
6. Reload nginx with the new cert
7. Run database migrations
8. Wait for all services to report healthy

Expected runtime: ~10 minutes (mostly Docker image builds and Ollama model pull).

---

## 3. Secrets Management

### 3.1 Required secrets

| Variable | Generate with | Notes |
|---|---|---|
| `POSTGRES_PASSWORD` | `openssl rand -base64 24` | 32 chars URL-safe |
| `REDIS_PASSWORD` | `openssl rand -base64 24` | |
| `JWT_SECRET_KEY` | `openssl rand -hex 32` | Legacy HS256 fallback |
| `ENCRYPTION_KEY` | `openssl rand -hex 16` | Fernet base key |
| `ENCRYPTION_MASTER_KEY` | `openssl rand -hex 32` | **Cannot be recovered if lost** |
| `QDRANT_API_KEY` | `openssl rand -hex 32` | Optional but recommended |

### 3.2 Storage rules

1. **Never commit `.env.production`** — it's in `.gitignore`. The example file is the only thing tracked.
2. **Back up `ENCRYPTION_MASTER_KEY`** in at least two places:
   - A reputable password manager (1Password, Bitwarden, etc.)
   - A printed copy in a sealed envelope, offsite
3. The master key is **never** stored in PostgreSQL. Losing it makes encrypted blobs (face/voice profiles, 2FA secrets, encrypted exports) permanently unrecoverable.
4. Rotate `JWT_SECRET_KEY` every 6 months. Active sessions will be invalidated.
5. Rotate `POSTGRES_PASSWORD` and `REDIS_PASSWORD` annually.

### 3.3 Optional: Docker secrets

For multi-host swarm/k8s deployments, mount secrets as files via Docker secrets and read from `/run/secrets/<name>`. The single-host compose file uses environment variables for simplicity.

### 3.4 Filesystem permissions

After deploy, ensure:
```bash
sudo chown root:root /opt/replica-ai/.env.production
sudo chmod 600       /opt/replica-ai/.env.production
```

---

## 4. PgBouncer Connection Pooling

PgBouncer sits between the FastAPI api service and PostgreSQL, providing connection
pooling so the api can use many short-lived async sessions without exhausting Postgres
connection slots.

**Pool mode**: `session` (not `transaction`).

We use session mode because the FastAPI api uses `asyncpg` via SQLAlchemy, which
relies on prepared statements. Transaction mode breaks prepared statements unless the
client disables its statement cache. Session mode is slightly less efficient but
zero-config.

**Tuning** (in `docker-compose.prod.yml`):

| Setting | Default | When to change |
|---|---|---|
| `MAX_CLIENT_CONN` | 200 | Increase if many concurrent users |
| `DEFAULT_POOL_SIZE` | 20 | Should be ≤ `max_connections / number_of_databases` |
| `MIN_POOL_SIZE` | 5 | |
| `RESERVE_POOL_SIZE` | 5 | Burst capacity |

To verify the pool is healthy:
```bash
docker compose -f docker-compose.prod.yml exec pgbouncer \
    psql -h localhost -p 6432 -U replica pgbouncer -c 'SHOW POOLS;'
```

---

## 5. Backups

### 5.1 What is backed up

| Source | Format | Location |
|---|---|---|
| PostgreSQL | `pg_dump` plain SQL, gzipped | `${BACKUP_DIR}/postgres/replica_ai_<ts>.sql.gz` |
| Qdrant | snapshot tarball | `${BACKUP_DIR}/qdrant/<collection>_<ts>.snapshot` |
| api storage | rsync mirror | `${BACKUP_DIR}/api_storage/<ts>/` |
| ai storage | rsync mirror | `${BACKUP_DIR}/ai_storage/<ts>/` |

### 5.2 Schedule

The backup script runs as a host cron job. Add this to root's crontab:

```cron
# Daily backup at 02:30 server time
30 2 * * * /opt/replica-ai/scripts/backup.sh >> /var/log/replica-ai-backup.log 2>&1
```

Backups older than `BACKUP_RETENTION_DAYS` (default 30) are pruned automatically.

### 5.3 Restore

```bash
# List available backups
ls -lh /var/backups/replica-ai/postgres/

# Restore a specific backup (will stop services, restore, restart)
sudo /opt/replica-ai/scripts/restore.sh 20260406-0230
```

Always test restores quarterly. A backup you've never restored is not a backup.

### 5.4 Offsite copies

Set `BACKUP_RCLONE_REMOTE=mybucket` in `.env.production` and configure rclone on the
host. The backup script will upload finished archives via `rclone copy`.

---

## 6. Monitoring

### 6.1 Health endpoints

| Service | URL | Expected |
|---|---|---|
| nginx | `https://<domain>/healthz` | `200 ok` |
| api   | `http://api:8000/health`   | `200 {"status":"ok"}` |
| ai    | `http://ai:8100/health`    | `200 {"status":"ok"}` |
| postgres | `pg_isready`            | exit 0 |
| redis | `redis-cli ping`           | `PONG` |
| qdrant | `http://qdrant:6333/healthz` | `200` |

### 6.2 Monitoring script

`scripts/monitor.sh` runs all checks and alerts via webhook + email when something
fails or disk usage exceeds 80%.

Add to root crontab:
```cron
*/5 * * * * /opt/replica-ai/scripts/monitor.sh >> /var/log/replica-ai-monitor.log 2>&1
```

### 6.3 Resource limits

Container memory and CPU limits are set in `docker-compose.prod.yml`. Defaults sized
for a 4 vCPU / 8 GB host:

| Service | Memory | CPU |
|---|---|---|
| nginx | 256 MB | 0.5 |
| web | 1 GB | 1.0 |
| api | 2 GB | 2.0 |
| ai | 4 GB | 2.0 |
| postgres | 2 GB | 2.0 |
| redis | 768 MB | 1.0 |
| qdrant | 2 GB | 2.0 |
| ollama | 8 GB | 4.0 |
| pgbouncer | 256 MB | 0.5 |
| piper | 1 GB | 1.0 |

Adjust upward for larger hosts.

---

## 7. Updates

```bash
sudo /opt/replica-ai/scripts/update.sh
```

The update script:
1. Pulls the latest code (`git pull`)
2. Rebuilds container images
3. Runs database migrations (Prisma)
4. Performs a rolling restart of services (web → api → ai), keeping the previous
   container alive until the new one reports healthy
5. Prunes dangling images

Downtime: ~5–10 seconds per service during the rolling restart.

---

## 8. Firewall

The deploy script does **not** configure ufw — do this manually:

```bash
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow OpenSSH
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
```

---

## 9. Troubleshooting

| Symptom | Check |
|---|---|
| 502 Bad Gateway | `docker compose -f docker-compose.prod.yml ps` — is `web`/`api` healthy? |
| 429 Too Many Requests | Rate limit hit. Check nginx access log for the offending IP. |
| Cert renewal failed | `docker compose -f docker-compose.prod.yml logs certbot` |
| Slow chat responses | `docker compose -f docker-compose.prod.yml logs ollama` — model still loading? |
| DB connection errors | `docker compose -f docker-compose.prod.yml exec pgbouncer pgbouncer -V` and `SHOW POOLS;` |
| OOM kills | Check `dmesg` and bump memory limits in `docker-compose.prod.yml` |

For deeper diagnostics:
```bash
docker compose -f docker-compose.prod.yml logs -f --tail=200 <service>
docker stats
```
